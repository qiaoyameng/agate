from copy import copy

from agate.exceptions import UnitError
from agate.rows import Row
from agate.units import Unit


def convert(self, column_units):
    """
    Explicitly convert one or more unitized columns to other
    :class:`.Unit` instances.

    Column values are physically converted; the returned table stores the new
    units. This is the supported way to unify columns measured in different
    units before :meth:`.Table.merge` or other combination.

    :param column_units:
        A dictionary mapping column names to :class:`.Unit` instances, or a
        single :code:`(column_name, unit)` tuple. Columns not listed keep
        their values and units unchanged.
    :returns:
        A new :class:`.Table`.
    """
    if isinstance(column_units, tuple) and len(column_units) == 2 and isinstance(column_units[1], Unit):
        column_units = {column_units[0]: column_units[1]}
    elif not isinstance(column_units, dict):
        raise ValueError('column_units must be a dict of column names to Unit instances, or a (name, unit) tuple.')

    new_units = list(copy(self._column_units))
    converted_values = {}

    for column_name, target_unit in column_units.items():
        if not isinstance(target_unit, Unit):
            raise ValueError('Conversion targets must be Unit instances.')

        index = self._column_names.index(column_name)
        source_unit = self._column_units[index]

        if source_unit is None:
            raise UnitError('Column "%s" has no unit to convert from.' % column_name)

        if not source_unit.is_compatible(target_unit):
            raise UnitError(
                'Column "%s" has unit "%s" (dimension "%s") and can not be converted to "%s" (dimension "%s").'
                % (column_name, source_unit.name, source_unit.dimension,
                   target_unit.name, target_unit.dimension)
            )

        new_units[index] = target_unit
        converted_values[index] = [
            source_unit.convert(value, target_unit) if value is not None else None
            for value in self._columns[index].values()
        ]

    new_rows = []

    for row_index, row in enumerate(self._rows):
        values = list(row.values())

        for index, converted in converted_values.items():
            values[index] = converted[row_index]

        new_rows.append(Row(values, self._column_names))

    return self._fork(new_rows, column_units=new_units)
