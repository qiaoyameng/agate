from agate.aggregations.has_nulls import HasNulls
from agate.computations.base import Computation
from agate.data_types import Date, DateTime, Number, TimeDelta
from agate.exceptions import DataTypeError, UnitError
from agate.units import reference_unit
from agate.warns import warn_null_calculation


class Change(Computation):
    """
    Calculate the difference between two columns.

    This calculation can be applied to :class:`.Number` columns to calculate
    numbers. It can also be applied to :class:`.Date`, :class:`.DateTime`, and
    :class:`.TimeDelta` columns to calculate time deltas.

    :param before_column_name:
        The name of a column containing the "before" values.
    :param after_column_name:
        The name of a column containing the "after" values.
    """
    def __init__(self, before_column_name, after_column_name):
        self._before_column_name = before_column_name
        self._after_column_name = after_column_name

    def get_computed_data_type(self, table):
        before_column = table.columns[self._before_column_name]

        if isinstance(before_column.data_type, (Date, DateTime, TimeDelta)):
            return TimeDelta()
        if isinstance(before_column.data_type, Number):
            return Number()

    def get_computed_unit(self, table):
        before_column = table.columns[self._before_column_name]

        if isinstance(before_column.data_type, Number) and before_column.unit is not None:
            return before_column.unit.delta_unit()

        return None

    def validate(self, table):
        before_column = table.columns[self._before_column_name]
        after_column = table.columns[self._after_column_name]

        before_unit = before_column.unit
        after_unit = after_column.unit

        if isinstance(before_column.data_type, Number) and (before_unit is not None or after_unit is not None):
            if before_unit is None or after_unit is None:
                raise UnitError(
                    'Change can not combine unitized column "%s" with ununitized column "%s".'
                    % (self._before_column_name, self._after_column_name)
                )

            if not before_unit.is_compatible(after_unit):
                raise UnitError(
                    'Change can not combine units of different dimensions: "%s" (%s) and "%s" (%s).'
                    % (
                        self._before_column_name, before_unit.dimension,
                        self._after_column_name, after_unit.dimension,
                    )
                )

        for data_type in (Number, Date, DateTime, TimeDelta):
            if isinstance(before_column.data_type, data_type):
                if not isinstance(after_column.data_type, data_type):
                    raise DataTypeError('Specified columns must be of the same type')

                if HasNulls(self._before_column_name).run(table):
                    warn_null_calculation(self, before_column)

                if HasNulls(self._after_column_name).run(table):
                    warn_null_calculation(self, after_column)

                return

        raise DataTypeError('Change before and after columns must both contain data that is one of: '
                            'Number, Date, DateTime or TimeDelta.')

    def run(self, table):
        new_column = []
        before_column = table.columns[self._before_column_name]
        after_column = table.columns[self._after_column_name]

        before_unit = before_column.unit
        after_unit = after_column.unit

        use_units = isinstance(before_column.data_type, Number) and before_unit is not None

        if use_units:
            target_unit = reference_unit(before_unit.delta_unit())

        for row in table.rows:
            before = row[self._before_column_name]
            after = row[self._after_column_name]

            if before is not None and after is not None:
                if use_units:
                    before = before_unit.to_reference(before)
                    after = after_unit.to_reference(after)

                new_column.append(after - before)
            else:
                new_column.append(None)

        return new_column
