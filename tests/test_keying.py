import datetime
from decimal import Decimal

import agate
from agate import KeyStrategy, Table
from agate.data_types import Boolean, DataType, Date, DateTime, Number, Text, TimeDelta
from agate.exceptions import KeyStrategyError
from agate.testcase import AgateTestCase


class Point:
    def __init__(self, x, y):
        self.x = x
        self.y = y


class PointType(DataType):
    def cast(self, d):
        if d is None or isinstance(d, Point):
            return d

        raise ValueError('Can not parse value as Point.')


class TestKeyStrategyEncoding(AgateTestCase):
    def setUp(self):
        self.strategy = KeyStrategy()

    def test_boolean_distinct_from_numbers(self):
        self.assertNotEqual(self.strategy.encode(True), self.strategy.encode(1))
        self.assertNotEqual(self.strategy.encode(False), self.strategy.encode(0))
        self.assertEqual(self.strategy.encode(True), self.strategy.encode(True))

    def test_finite_decimals_match_by_numeric_value(self):
        self.assertEqual(
            self.strategy.encode(Decimal('1.0')),
            self.strategy.encode(Decimal('1.00'))
        )
        self.assertEqual(self.strategy.encode(1), self.strategy.encode(Decimal('1')))
        self.assertNotEqual(self.strategy.encode(1), self.strategy.encode(Decimal('2')))

    def test_nan_is_single_missing_class(self):
        nan_tokens = [
            self.strategy.encode(Decimal('NaN')),
            self.strategy.encode(Decimal('NaN')),
            self.strategy.encode(float('nan'))
        ]

        self.assertEqual(len(set(nan_tokens)), 1)
        self.assertNotEqual(nan_tokens[0], self.strategy.encode(None))
        self.assertNotEqual(nan_tokens[0], self.strategy.encode(Decimal('1')))

    def test_null_configuration(self):
        self.assertEqual(self.strategy.encode(None), self.strategy.encode(None))

        mismatch = KeyStrategy(null_matches_null=False)
        self.assertNotEqual(mismatch.encode(None), mismatch.encode(None))

    def test_strings_are_not_coerced_to_numbers(self):
        self.assertNotEqual(self.strategy.encode('1'), self.strategy.encode(1))
        self.assertEqual(self.strategy.encode('a'), self.strategy.encode('a'))

    def test_date_and_datetime_are_separate(self):
        the_date = datetime.date(2020, 1, 1)
        the_datetime = datetime.datetime(2020, 1, 1)

        self.assertNotEqual(self.strategy.encode(the_date), self.strategy.encode(the_datetime))
        self.assertEqual(self.strategy.encode(the_date), self.strategy.encode(the_date))

    def test_timedelta_supported(self):
        value = datetime.timedelta(days=1)
        self.assertEqual(self.strategy.encode(value), self.strategy.encode(value))

    def test_unsupported_value_requires_adapter(self):
        with self.assertRaises(KeyStrategyError):
            self.strategy.encode([1, 2])

    def test_adapter_provides_stable_token(self):
        strategy = KeyStrategy(adapter=lambda value: ('list', tuple(value)))

        self.assertEqual(strategy.encode([1, 2]), strategy.encode([1, 2]))

    def test_adapter_must_return_hashable_token(self):
        def unhashable_adapter(value):
            return [value]

        strategy = KeyStrategy(adapter=unhashable_adapter)

        with self.assertRaises(KeyStrategyError):
            strategy.encode(Point(1, 2))

    def test_composite_encoding(self):
        token = self.strategy.encode_composite((Decimal('1'), 'a', None))

        self.assertEqual(token, self.strategy.encode_composite((Decimal('1.0'), 'a', None)))
        self.assertNotEqual(token, self.strategy.encode_composite((Decimal('2'), 'a', None)))


class TestDistinctKeyStrategy(AgateTestCase):
    def setUp(self):
        self.number_type = Number()
        self.text_type = Text()
        self.strategy = KeyStrategy()

    def test_nan_values_collapse(self):
        table = Table(
            ((Decimal('1'),), (Decimal('NaN'),), (Decimal('NaN'),), (Decimal('2'),)),
            ['n'],
            [self.number_type]
        )

        distinct = table.distinct('n', key_strategy=self.strategy)

        self.assertColumnNames(distinct, ['n'])
        self.assertColumnTypes(distinct, [Number])
        values = distinct.columns['n'].values()
        self.assertEqual(len(values), 3)
        self.assertEqual(values[0], Decimal('1'))
        self.assertTrue(values[1].is_nan())
        self.assertEqual(values[2], Decimal('2'))

    def test_null_matches_null_by_default(self):
        table = Table(((None,), (None,), (1,)), ['n'], [self.number_type])

        distinct = table.distinct('n', key_strategy=self.strategy)

        self.assertEqual(len(distinct.rows), 2)

    def test_null_never_matches_when_configured(self):
        table = Table(((None,), (None,), (1,)), ['n'], [self.number_type])

        distinct = table.distinct('n', key_strategy=KeyStrategy(null_matches_null=False))

        self.assertEqual(len(distinct.rows), 3)

    def test_composite_distinct(self):
        table = Table(
            ((1, 'a'), (1, 'a'), (1, 'b'), (2, 'a')),
            ['x', 'y'],
            [self.number_type, self.text_type]
        )

        distinct = table.distinct(['x', 'y'], key_strategy=self.strategy)

        self.assertEqual(len(distinct.rows), 3)

    def test_unsupported_value_raises(self):
        table = Table((('a',), ('a',)), ['s'], [self.text_type])

        with self.assertRaises(KeyStrategyError):
            table.distinct(lambda row: [row['s']], key_strategy=self.strategy)


class TestGroupByKeyStrategy(AgateTestCase):
    def setUp(self):
        self.number_type = Number()
        self.text_type = Text()
        self.strategy = KeyStrategy()

    def test_nan_group_uses_original_display_value(self):
        table = Table(
            ((Decimal('NaN'), 'a'), (Decimal('NaN'), 'b'), (Decimal('1'), 'c')),
            ['n', 's'],
            [self.number_type, self.text_type]
        )

        tableset = table.group_by('n', key_strategy=self.strategy)

        self.assertEqual(len(tableset), 2)

        nan_keys = [key for key in tableset.keys() if isinstance(key, Decimal) and key.is_nan()]
        self.assertEqual(len(nan_keys), 1)
        self.assertEqual(len(tableset[nan_keys[0]].rows), 2)

    def test_null_mismatch_creates_separate_groups(self):
        table = Table(((None, 'a'), (None, 'b'), (1, 'c')), ['n', 's'],
                      [self.number_type, self.text_type])

        tableset = table.group_by('n', key_strategy=KeyStrategy(null_matches_null=False))

        self.assertEqual(len(tableset), 3)
        self.assertEqual([len(group.rows) for group in tableset], [1, 1, 1])

    def test_composite_group_keys_are_native_tuples(self):
        table = Table(
            ((1, 'a'), (1, 'a'), (2, 'a')),
            ['x', 'y'],
            [self.number_type, self.text_type]
        )

        tableset = table.group_by(['x', 'y'], key_strategy=self.strategy)

        self.assertEqual(list(tableset.keys()), [(Decimal('1'), 'a'), (Decimal('2'), 'a')])


class TestJoinKeyStrategy(AgateTestCase):
    def setUp(self):
        self.number_type = Number()
        self.text_type = Text()
        self.boolean_type = Boolean()
        self.strategy = KeyStrategy()

        self.left = Table(
            ((Decimal('1'), 'a'), (Decimal('NaN'), 'b'), (None, 'c')),
            ['k', 'left_value'],
            [self.number_type, self.text_type]
        )
        self.right = Table(
            ((Decimal('1'), 'x'), (Decimal('NaN'), 'y'), (None, 'z')),
            ['k', 'right_value'],
            [self.number_type, self.text_type]
        )

    def test_nan_and_numeric_matches_inner_join(self):
        joined = self.left.join(self.right, 'k', 'k', inner=True, key_strategy=self.strategy)

        self.assertEqual(len(joined.rows), 3)
        self.assertEqual(joined.rows[0].values(), (Decimal('1'), 'a', 'x'))
        nan_row = joined.rows[1].values()
        self.assertTrue(nan_row[0].is_nan())
        self.assertEqual(nan_row[1:], ('b', 'y'))
        self.assertEqual(joined.rows[2].values(), (None, 'c', 'z'))

    def test_null_matches_null_by_default(self):
        joined = self.left.join(self.right, 'k', 'k', inner=True, key_strategy=self.strategy)

        # Numeric, NaN and null all find their match under the defaults.
        self.assertEqual(len(joined.rows), 3)

        null_rows = [row for row in joined.rows if row['k'] is None]
        self.assertEqual(len(null_rows), 1)
        self.assertEqual(null_rows[0]['right_value'], 'z')

    def test_null_mismatch_preserves_right_rows_in_full_outer(self):
        strategy = KeyStrategy(null_matches_null=False)

        joined = self.left.join(self.right, 'k', 'k', full_outer=True, key_strategy=strategy)

        # Numeric and NaN rows match; the two null rows are unmatched and both
        # survive as dangling left and right rows.
        self.assertEqual(len(joined.rows), 4)

        dangling_right = [row for row in joined.rows if row['left_value'] is None]
        self.assertEqual(len(dangling_right), 1)
        self.assertEqual(dangling_right[0]['right_value'], 'z')

        dangling_left = [row for row in joined.rows if row['right_value'] is None and row['k'] is None]
        self.assertEqual(len(dangling_left), 1)

    def test_null_mismatch_inner_join_drops_both_nulls(self):
        strategy = KeyStrategy(null_matches_null=False)

        joined = self.left.join(self.right, 'k', 'k', inner=True, key_strategy=strategy)

        self.assertEqual(len(joined.rows), 2)
        self.assertNotIn(None, [row['k'] for row in joined.rows])

    def test_incompatible_column_types_name_both_sides(self):
        text_left = Table((('1',),), ['k'], [self.text_type])
        number_right = Table(((1,),), ['k'], [self.number_type])

        with self.assertRaises(KeyStrategyError) as context:
            text_left.join(number_right, 'k', 'k', key_strategy=self.strategy)

        message = str(context.exception)
        self.assertIn('k', message)
        self.assertIn('Text', message)
        self.assertIn('Number', message)

    def test_boolean_and_number_columns_are_incompatible(self):
        boolean_left = Table(((True,),), ['k'], [self.boolean_type])
        number_right = Table(((1,),), ['k'], [self.number_type])

        with self.assertRaises(KeyStrategyError):
            boolean_left.join(number_right, 'k', 'k', key_strategy=self.strategy)

    def test_date_and_datetime_columns_are_incompatible(self):
        date_left = Table(((datetime.date(2020, 1, 1),),), ['k'], [Date()])
        datetime_right = Table(((datetime.datetime(2020, 1, 1),),), ['k'], [DateTime()])

        with self.assertRaises(KeyStrategyError):
            date_left.join(datetime_right, 'k', 'k', key_strategy=self.strategy)

    def test_composite_full_outer_null_mismatch(self):
        left = Table(
            ((None, 'a', 'L'),),
            ['x', 'y', 'value'],
            [self.number_type, self.text_type, self.text_type]
        )
        right = Table(
            ((None, 'a', 'R'),),
            ['x', 'y', 'value'],
            [self.number_type, self.text_type, self.text_type]
        )

        joined = left.join(
            right,
            ['x', 'y'],
            ['x', 'y'],
            full_outer=True,
            key_strategy=KeyStrategy(null_matches_null=False)
        )

        self.assertEqual(len(joined.rows), 2)

    def test_custom_data_type_requires_adapter_naming_both_columns(self):
        point_type = PointType()
        left = Table(((Point(1, 2),),), ['p'], [point_type])
        right = Table(((Point(1, 2),),), ['q'], [point_type])

        with self.assertRaises(KeyStrategyError) as context:
            left.join(right, 'p', 'q', key_strategy=self.strategy)

        message = str(context.exception)
        self.assertIn('p', message)
        self.assertIn('q', message)

        adapter = KeyStrategy(adapter=lambda point: (point.x, point.y))
        joined = left.join(right, 'p', 'q', key_strategy=adapter)

        self.assertEqual(len(joined.rows), 1)


class TestDefaultBehaviorUnchanged(AgateTestCase):
    def test_distinct_without_strategy_uses_native_identity(self):
        table = Table(
            ((Decimal('NaN'),), (Decimal('NaN'),)),
            ['n'],
            [Number()]
        )

        # Native Decimal NaN identity means two NaNs are not equal.
        self.assertEqual(len(table.distinct('n').rows), 2)

    def test_join_without_strategy_uses_native_equality(self):
        left = Table(((1, 'a'),), ['k', 'v'], [Number(), Text()])
        right = Table(((1, 'b'),), ['k', 'v'], [Number(), Text()])

        joined = left.join(right, 'k', 'k')

        self.assertEqual(len(joined.rows), 1)
