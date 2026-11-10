import unittest
from decimal import Decimal

from agate import Change, Computation, Formula, Mean, Number, Sum, Table, TableSet, Text
from agate.aggregations import Aggregation, MAD, IQR, Max, Min, StDev, Summary
from agate.exceptions import UnitError
from agate.units import CELSIUS, CENTIMETER, KELVIN, KELVIN_DELTA, METER, MILLISECOND, SECOND


class TestUnitComputations(unittest.TestCase):
    def test_change_converts_same_dimension_lengths(self):
        table = Table(
            ((Decimal('1'), Decimal('100')), (Decimal('2'), Decimal('300'))),
            ['meters', 'centimeters'],
            [Number(), Number()],
            column_units=[METER, CENTIMETER],
        )

        result = table.compute([('difference', Change('meters', 'centimeters'))])

        self.assertEqual(result.columns['difference'].unit, METER)
        self.assertEqual(result.rows[0]['difference'], Decimal('0.00'))
        self.assertEqual(result.rows[1]['difference'], Decimal('1.00'))

    def test_change_converts_same_dimension_time(self):
        table = Table(
            ((Decimal('1'), Decimal('2000')),),
            ['seconds', 'milliseconds'],
            [Number(), Number()],
            column_units=[SECOND, MILLISECOND],
        )

        result = table.compute([('difference', Change('seconds', 'milliseconds'))])

        self.assertEqual(result.columns['difference'].unit, SECOND)
        self.assertEqual(result.rows[0]['difference'], Decimal('1.000'))

    def test_change_between_celsius_values_is_offset_free_delta(self):
        table = Table(
            ((Decimal('0'), Decimal('100')), (Decimal('10'), Decimal('-10'))),
            ['before', 'after'],
            [Number(), Number()],
            column_units=[CELSIUS, CELSIUS],
        )

        result = table.compute([('difference', Change('before', 'after'))])

        self.assertEqual(result.columns['difference'].unit, KELVIN_DELTA)
        self.assertEqual(result.rows[0]['difference'], Decimal('100'))
        self.assertEqual(result.rows[1]['difference'], Decimal('-20'))

    def test_change_rejects_cross_dimension(self):
        table = Table(
            ((Decimal('1'), Decimal('0')),),
            ['length', 'temperature'],
            [Number(), Number()],
            column_units=[METER, CELSIUS],
        )

        with self.assertRaises(UnitError):
            table.compute([('bad', Change('length', 'temperature'))])

    def test_change_rejects_mixed_unit_and_plain_column(self):
        table = Table(
            ((Decimal('1'), Decimal('2')),),
            ['unitized', 'plain'],
            [Number(), Number()],
            column_units=[METER, None],
        )

        with self.assertRaises(UnitError):
            table.compute([('bad', Change('unitized', 'plain'))])

    def test_plain_change_is_unchanged(self):
        table = Table(((1, 3), (2, 5)), ['before', 'after'], [Number(), Number()])

        result = table.compute([('difference', Change('before', 'after'))])

        self.assertIsNone(result.columns['difference'].unit)
        self.assertEqual(result.rows[0]['difference'], Decimal('2'))

    def test_formula_requires_explicit_unit(self):
        table = Table(
            ((Decimal('1'),),),
            ['meters'],
            [Number()],
            column_units=[METER],
        )

        implicit = table.compute([('doubled', Formula(Number(), lambda row: row['meters'] * 2))])
        self.assertIsNone(implicit.columns['doubled'].unit)

        explicit = table.compute([
            ('doubled', Formula(Number(), lambda row: row['meters'] * 2, unit=METER))
        ])
        self.assertEqual(explicit.columns['doubled'].unit, METER)

    def test_custom_computation_defaults_to_undetermined_unit(self):
        class Doubled(Computation):
            def get_computed_data_type(self, table):
                return Number()

            def run(self, table):
                return [value * 2 for value in table.columns['meters'].values()]

        table = Table(
            ((Decimal('1'),),),
            ['meters'],
            [Number()],
            column_units=[METER],
        )

        result = table.compute([('doubled', Doubled())])

        self.assertIsNone(result.columns['doubled'].unit)


class TestUnitAggregations(unittest.TestCase):
    def setUp(self):
        self.celsius = Table(
            ((Decimal('0'),), (Decimal('100'),), (Decimal('50'),)),
            ['temperature'],
            [Number()],
            column_units=[CELSIUS],
        )
        self.lengths = Table(
            ((Decimal('100'),), (Decimal('300'),)),
            ['centimeters'],
            [Number()],
            column_units=[CENTIMETER],
        )

    def test_mean_accepts_absolute_temperature_and_uses_reference_unit(self):
        self.assertEqual(self.celsius.aggregate(Mean('temperature')), Decimal('323.15'))
        self.assertEqual(Mean('temperature').get_aggregate_unit(self.celsius), KELVIN)

    def test_mean_converts_before_averaging(self):
        self.assertEqual(self.lengths.aggregate(Mean('centimeters')), Decimal('2.00'))
        self.assertEqual(Mean('centimeters').get_aggregate_unit(self.lengths), METER)

    def test_sum_rejects_absolute_temperature(self):
        with self.assertRaises(UnitError):
            self.celsius.aggregate(Sum('temperature'))

    def test_sum_sums_in_reference_unit(self):
        self.assertEqual(self.lengths.aggregate(Sum('centimeters')), Decimal('4.00'))
        self.assertEqual(Sum('centimeters').get_aggregate_unit(self.lengths), METER)

    def test_sum_accepts_temperature_difference(self):
        deltas = Table(
            ((Decimal('10'),), (Decimal('20'),)),
            ['delta'],
            [Number()],
            column_units=[KELVIN_DELTA],
        )

        self.assertEqual(deltas.aggregate(Sum('delta')), Decimal('30'))
        self.assertEqual(Sum('delta').get_aggregate_unit(deltas), KELVIN_DELTA)

    def test_min_max_keep_original_unit(self):
        self.assertEqual(self.celsius.aggregate(Min('temperature')), Decimal('0'))
        self.assertEqual(Min('temperature').get_aggregate_unit(self.celsius), CELSIUS)
        self.assertEqual(Max('temperature').get_aggregate_unit(self.celsius), CELSIUS)

    def test_spread_aggregations_use_delta_units(self):
        self.assertEqual(IQR('centimeters').get_aggregate_unit(self.lengths), METER)
        self.assertEqual(MAD('centimeters').get_aggregate_unit(self.lengths), METER)
        self.assertEqual(StDev('centimeters').get_aggregate_unit(self.lengths), METER)

    def test_tableset_aggregate_carries_units(self):
        table = Table(
            (('a', Decimal('100')), ('a', Decimal('300')), ('b', Decimal('500'))),
            ['group', 'centimeters'],
            [Text(), Number()],
            column_units=[None, CENTIMETER],
        )

        groups = table.group_by('group')
        aggregated = groups.aggregate([
            ('average', Mean('centimeters')),
            ('total', Sum('centimeters')),
        ])

        self.assertEqual(aggregated.column_units, (None, METER, METER))
        self.assertEqual(aggregated.rows[0]['average'], Decimal('2.00'))
        self.assertEqual(aggregated.rows[0]['total'], Decimal('4.00'))

    def test_custom_aggregation_defaults_to_undetermined_unit(self):
        class DoubledSum(Aggregation):
            def __init__(self, column_name):
                self._column_name = column_name

            def get_aggregate_data_type(self, table):
                return Number()

            def run(self, table):
                return table.columns[self._column_name].values()[0] * 2

        self.assertIsNone(DoubledSum('centimeters').get_aggregate_unit(self.lengths))

    def test_summary_requires_explicit_unit(self):
        implicit = Summary('centimeters', Number(), lambda column: column.values()[0])
        explicit = Summary('centimeters', Number(), lambda column: column.values()[0], unit=METER)

        self.assertIsNone(implicit.get_aggregate_unit(self.lengths))
        self.assertEqual(explicit.get_aggregate_unit(self.lengths), METER)


if __name__ == '__main__':
    unittest.main()
