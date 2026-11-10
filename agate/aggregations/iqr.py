import math

from agate.aggregations.base import Aggregation
from agate.aggregations.has_nulls import HasNulls
from agate.aggregations.percentiles import Percentiles
from agate.data_types import Number, TimeDelta
from agate.exceptions import DataTypeError
from agate.units import reference_unit
from agate.warns import warn_null_calculation


class IQR(Aggregation):
    """
    Calculate the interquartile range of a column.

    :param column_name:
        The name of a column containing :class:`.Number` or :class:`.TimeDelta` data.
    """
    def __init__(self, column_name):
        self._column_name = column_name
        self._percentiles = Percentiles(column_name)

    def get_aggregate_data_type(self, table):
        column = table.columns[self._column_name]

        if isinstance(column.data_type, (Number, TimeDelta)):
            return column.data_type

    def get_aggregate_unit(self, table):
        column = table.columns[self._column_name]

        if isinstance(column.data_type, Number) and column.unit is not None:
            return reference_unit(column.unit.delta_unit())

        return None

    def validate(self, table):
        column = table.columns[self._column_name]

        if not isinstance(column.data_type, (Number, TimeDelta)):
            raise DataTypeError('IQR can only be applied to columns containing Number or TimeDelta data.')

        has_nulls = HasNulls(self._column_name).run(table)

        if has_nulls:
            warn_null_calculation(self, column)

    def run(self, table):
        column = table.columns[self._column_name]

        if isinstance(column.data_type, Number) and column.unit is not None:
            values = tuple(column.unit.to_reference(v) for v in column.values_without_nulls_sorted())

            def percentile(p):
                k = len(values) * (float(p) / 100)
                low = max(1, int(math.ceil(k)))
                high = min(len(values), int(math.floor(k + 1)))

                if low == high:
                    return values[low - 1]

                return (values[low - 1] + values[high - 1]) / 2

            return percentile(75) - percentile(25)

        percentiles = self._percentiles.run(table)

        if percentiles[75] is not None and percentiles[25] is not None:
            return percentiles[75] - percentiles[25]
