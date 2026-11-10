"""
Implementation of the :class:`.Unit` class and the built-in units.
"""

from decimal import Decimal

from agate.exceptions import UnitError

#: Dimension name for lengths.
LENGTH = 'length'

#: Dimension name for elapsed time.
TIME = 'time'

#: Dimension name for absolute temperatures.
TEMPERATURE = 'temperature'

#: Dimension name for differences between temperatures.
TEMPERATURE_DELTA = 'temperature_delta'


class Unit:
    """
    A linear unit of measurement.

    Values expressed in the unit are converted to the dimension's reference
    unit using::

        reference_value = scale * value + offset

    Both :code:`scale` and :code:`offset` are stored as
    :class:`decimal.Decimal` so that relationships such as the Celsius
    offset (273.15) never lose precision.

    :param name:
        A short, human-readable name for the unit, for example :code:`'m'`.
    :param dimension:
        A string identifying the physical dimension, for example
        :code:`'length'`. Units may only be combined with other units of the
        same dimension.
    :param scale:
        Multiplicative factor converting a value in this unit to the
        dimension's reference unit.
    :param offset:
        Additive offset, in the reference unit, applied after scaling. Only
        absolute point scales (such as Celsius) need a non-zero offset.
    :param absolute:
        Set to :code:`False` for difference units, which may be summed and
        never carry an offset. Defaults to :code:`True`.
    """
    def __init__(self, name, dimension, scale=Decimal(1), offset=Decimal(0), absolute=True):
        self.name = name
        self.dimension = dimension
        self.scale = Decimal(scale)
        self.offset = Decimal(offset)
        self.absolute = absolute

        if not absolute and self.offset != 0:
            raise ValueError('Difference units can not define an offset.')

    def __repr__(self):
        return "<Unit: %s>" % self.name

    def __eq__(self, other):
        if not isinstance(other, Unit):
            return NotImplemented

        return (
            self.name == other.name
            and self.dimension == other.dimension
            and self.scale == other.scale
            and self.offset == other.offset
            and self.absolute == other.absolute
        )

    def __hash__(self):
        return hash((self.name, self.dimension, self.scale, self.offset, self.absolute))

    def to_reference(self, value):
        """
        Convert a single :class:`decimal.Decimal` value from this unit to the
        reference unit of its dimension.
        """
        if value is None:
            return None

        return self.scale * value + self.offset

    def from_reference(self, value):
        """
        Convert a single :class:`decimal.Decimal` value from the reference
        unit of this unit's dimension into this unit.
        """
        if value is None:
            return None

        return (value - self.offset) / self.scale

    def convert(self, value, target):
        """
        Convert a single value from this unit into the :class:`.Unit`
        :code:`target`.
        """
        self._check_compatible(target)

        return target.from_reference(self.to_reference(value))

    def is_compatible(self, other):
        """
        Return :code:`True` if this unit and :code:`other` describe the same
        dimension and the same kind (absolute point or difference).
        """
        if other is None:
            return False

        return self.dimension == other.dimension and self.absolute == other.absolute

    def _check_compatible(self, other):
        if not isinstance(other, Unit):
            raise UnitError('Can only convert to another Unit instance.')

        if not self.is_compatible(other):
            raise UnitError(
                'Unit "%s" (dimension "%s") can not be converted to unit "%s" (dimension "%s").'
                % (self.name, self.dimension, other.name, other.dimension)
            )

    def delta_unit(self):
        """
        Return the offset-free unit used for differences between values in
        this unit's dimension.
        """
        if not self.absolute:
            return self

        return reference_unit(Unit(
            self.name, _delta_dimension(self.dimension), Decimal(1), Decimal(0), absolute=False
        ))


# Reference (canonical) unit for each dimension.
_reference_units = {}


def _reference(unit):
    _reference_units[unit.dimension] = unit

    return unit


#: The meter, reference unit for length.
METER = _reference(Unit('m', LENGTH))

#: The centimeter (1 cm = 0.01 m).
CENTIMETER = Unit('cm', LENGTH, scale=Decimal('0.01'))

#: The second, reference unit for elapsed time.
SECOND = _reference(Unit('s', TIME))

#: The millisecond (1 ms = 0.001 s).
MILLISECOND = Unit('ms', TIME, scale=Decimal('0.001'))

#: The kelvin, reference unit for absolute temperature.
KELVIN = _reference(Unit('K', TEMPERATURE))

#: Degrees Celsius (K = C + 273.15).
CELSIUS = Unit('C', TEMPERATURE, offset=Decimal('273.15'))


def _delta_dimension(dimension):
    if dimension == TEMPERATURE:
        return TEMPERATURE_DELTA

    return dimension


#: Difference in kelvin, reference unit for temperature differences.
KELVIN_DELTA = _reference(Unit('K', TEMPERATURE_DELTA, absolute=False))

#: Difference in degrees Celsius, numerically equal to a difference in kelvin.
CELSIUS_DELTA = Unit('C', TEMPERATURE_DELTA, absolute=False)


def reference_unit(unit):
    """
    Return the reference unit for :code:`unit`'s dimension.

    For dimensions without a registered reference unit a synthetic unit with
    a scale of one and no offset is returned.
    """
    if unit in _reference_units.values():
        return unit

    registered = _reference_units.get(unit.dimension)

    if registered is not None:
        return registered

    return Unit(unit.name, unit.dimension, Decimal(1), Decimal(0), absolute=unit.absolute)


def get_unit(value):
    """
    Return :code:`value` if it is a :class:`.Unit`, otherwise :code:`None`.

    This accepts the "unit or nothing" values used throughout agate so that
    plain tables without unit metadata behave exactly as before.
    """
    if isinstance(value, Unit):
        return value

    return None


def convert_value(value, source, target):
    """
    Convert :code:`value` from the :class:`.Unit` :code:`source` to
    :code:`target`.

    A :code:`None` value passes through unchanged. If the units do not match
    and exactly one of them is :code:`None` a :class:`.UnitError` is raised.
    """
    if value is None:
        return None

    if source is None or target is None:
        if source is target:
            return value

        raise UnitError('Can not convert between a unit and an ununitized value.')

    return source.convert(value, target)
