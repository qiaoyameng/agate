"""
Units describe how the :class:`decimal.Decimal` values in a
:class:`.Number` column should be interpreted. A unit is not a label
attached to formatted output: it stores the linear relationship
:code:`value_in_reference_unit = scale * value + offset` so that values from
different units can be converted before they are compared or combined.

A first set of units is built in:

* Length: :data:`.METER`, :data:`.CENTIMETER`
* Time: :data:`.SECOND`, :data:`.MILLISECOND`
* Absolute temperature: :data:`.KELVIN`, :data:`.CELSIUS`
* Temperature differences: :data:`.KELVIN_DELTA`, :data:`.CELSIUS_DELTA`

Custom units can be created by instantiating :class:`.Unit` directly.
"""

from agate.units.unit import (
    CELSIUS,
    CELSIUS_DELTA,
    CENTIMETER,
    KELVIN,
    KELVIN_DELTA,
    LENGTH,
    METER,
    MILLISECOND,
    SECOND,
    TEMPERATURE,
    TEMPERATURE_DELTA,
    TIME,
    Unit,
    convert_value,
    get_unit,
    reference_unit,
)

__all__ = [
    'Unit',
    'METER',
    'CENTIMETER',
    'SECOND',
    'MILLISECOND',
    'KELVIN',
    'CELSIUS',
    'KELVIN_DELTA',
    'CELSIUS_DELTA',
    'LENGTH',
    'TIME',
    'TEMPERATURE',
    'TEMPERATURE_DELTA',
    'convert_value',
    'get_unit',
    'reference_unit',
]
