import datetime

from agate.aggregations.base import Aggregation
from agate.data_types import Number, TimeDelta
from agate.exceptions import DataTypeError, UnitError
from agate.units import TEMPERATURE, reference_unit


class Sum(Aggregation):
    """
    Calculate the sum of a column.

    :param column_name:
        The name of a column containing :class:`.Number` data.
    """
    def __init__(self, column_name):
        self._column_name = column_name

    def get_aggregate_data_type(self, table):
        column = table.columns[self._column_name]

        if isinstance(column.data_type, (Number, TimeDelta)):
            return column.data_type

    def get_aggregate_unit(self, table):
        column = table.columns[self._column_name]

        if isinstance(column.data_type, Number) and column.unit is not None:
            return reference_unit(column.unit)

        return None

    def validate(self, table):
        column = table.columns[self._column_name]

        if not isinstance(column.data_type, (Number, TimeDelta)):
            raise DataTypeError('Sum can only be applied to columns containing Number or TimeDelta data.')

        if (isinstance(column.data_type, Number) and column.unit is not None and column.unit.absolute
                and column.unit.dimension == TEMPERATURE):
            raise UnitError(
                'Sum can not add absolute temperatures. Convert the column to a temperature difference '
                '(for example with the Change computation) first.'
            )

    def run(self, table):
        column = table.columns[self._column_name]

        start = 0
        if isinstance(column.data_type, TimeDelta):
            start = datetime.timedelta()

        values = column.values_without_nulls()

        if isinstance(column.data_type, Number) and column.unit is not None:
            values = (column.unit.to_reference(value) for value in values)

        return sum(values, start)
