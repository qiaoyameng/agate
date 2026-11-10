import copy
from decimal import Decimal

from agate import Table
from agate.data_types import DataType, Number, Text
from agate.exceptions import ReshapeConflictError, ReshapeMissingError
from agate.table.reshape import register_data_type
from agate.testcase import AgateTestCase


class CustomText(DataType):
    def cast(self, d):
        if d is None:
            return d

        return str(d)


class TestReshape(AgateTestCase):
    def setUp(self):
        self.rows = (
            ('Jane', 24, Decimal('1.5')),
            ('Jack', 35, Decimal('1.7')),
            ('Joe', 28, Decimal('1.6'))
        )

        self.column_names = ['name', 'age', 'height']
        self.column_types = [Text(), Number(), Number()]
        self.row_names = ['a', 'b', 'c']

    def make_table(self):
        return Table(self.rows, self.column_names, self.column_types, row_names=self.row_names)

    def test_round_trip(self):
        table = self.make_table()

        long_table, spec = table.normalize_with_spec(key='name')

        self.assertColumnNames(
            long_table,
            ['name', 'row_position', 'column_position', 'property', 'value']
        )
        self.assertColumnTypes(long_table, [Text, Number, Number, Text, Number])
        self.assertEqual(len(long_table.rows), 6)

        restored = long_table.denormalize_with_spec(spec)

        self.assertRows(restored, self.rows)
        self.assertColumnNames(restored, self.column_names)
        self.assertColumnTypes(restored, [Text, Number, Number])
        self.assertRowNames(restored, self.row_names)

    def test_round_trip_no_key(self):
        table = Table(self.rows, self.column_names, self.column_types)

        long_table, spec = table.normalize_with_spec()

        self.assertColumnNames(
            long_table,
            ['row_position', 'column_position', 'property', 'value']
        )
        self.assertEqual(len(long_table.rows), 9)

        restored = long_table.denormalize_with_spec(spec)

        self.assertRows(restored, self.rows)
        self.assertColumnNames(restored, self.column_names)
        self.assertIsNone(restored.row_names)

    def test_round_trip_preserves_column_order(self):
        table = self.make_table()

        long_table, spec = table.normalize_with_spec(key='height', properties=['name', 'age'])

        restored = long_table.denormalize_with_spec(spec)

        self.assertColumnNames(restored, self.column_names)
        self.assertRows(restored, self.rows)

    def test_properties_must_cover_all_columns(self):
        table = self.make_table()

        with self.assertRaises(ValueError):
            table.normalize_with_spec(key='name', properties=['age'])

    def test_round_trip_duplicate_property_labels(self):
        table = self.make_table()

        long_table, spec = table.normalize_with_spec(
            key='name',
            property_labels=['metric', 'metric']
        )

        labels = [row['property'] for row in long_table.rows]

        self.assertEqual(labels, ['metric', 'metric'] * 3)

        restored = long_table.denormalize_with_spec(spec)

        self.assertRows(restored, self.rows)
        self.assertColumnNames(restored, self.column_names)
        self.assertColumnTypes(restored, [Text, Number, Number])

    def test_round_trip_mixed_type_property_labels(self):
        table = self.make_table()

        long_table, spec = table.normalize_with_spec(
            key='name',
            property_labels=[1, '1']
        )

        restored = long_table.denormalize_with_spec(spec)

        self.assertRows(restored, self.rows)
        self.assertColumnNames(restored, self.column_names)

    def test_round_trip_with_nulls(self):
        rows = (
            ('Jane', None, Decimal('1.5')),
            ('Jack', 35, None),
            ('Joe', 28, Decimal('1.6'))
        )

        table = Table(rows, self.column_names, self.column_types, row_names=self.row_names)

        long_table, spec = table.normalize_with_spec(key='name')

        self.assertIn([0, 1], spec['null_cells'])
        self.assertIn([1, 2], spec['null_cells'])
        self.assertEqual(len(spec['null_cells']), 2)

        restored = long_table.denormalize_with_spec(spec)

        self.assertRows(restored, rows)
        self.assertIsNone(restored.rows[0]['age'])
        self.assertIsNone(restored.rows[1]['height'])

    def test_round_trip_empty_table(self):
        table = Table([], self.column_names, self.column_types)

        long_table, spec = table.normalize_with_spec(key='name')

        self.assertEqual(len(long_table.rows), 0)
        self.assertColumnNames(
            long_table,
            ['name', 'row_position', 'column_position', 'property', 'value']
        )

        restored = long_table.denormalize_with_spec(spec)

        self.assertEqual(len(restored.rows), 0)
        self.assertColumnNames(restored, self.column_names)
        self.assertColumnTypes(restored, [Text, Number, Number])

    def test_missing_position_reported(self):
        rows = (
            ('Jane', None, Decimal('1.5')),
            ('Jack', 35, Decimal('1.7')),
            ('Joe', 28, Decimal('1.6'))
        )

        table = Table(rows, self.column_names, self.column_types)

        long_table, spec = table.normalize_with_spec(key='name')

        # Manually delete the record for row 1, column 'height' (position 2)
        pruned = long_table.where(
            lambda row: not (row['row_position'] == 1 and row['column_position'] == 2)
        )

        with self.assertRaises(ReshapeMissingError) as context:
            pruned.denormalize_with_spec(spec)

        self.assertEqual(context.exception.missing_positions, [(1, 'height')])
        self.assertEqual(context.exception.null_positions, [(0, 'age')])

    def test_missing_position_filled(self):
        table = self.make_table()

        long_table, spec = table.normalize_with_spec(key='name')

        pruned = long_table.where(
            lambda row: not (row['row_position'] == 1 and row['column_position'] == 2)
        )

        restored = pruned.denormalize_with_spec(spec, fill_missing=Decimal(0))

        self.assertEqual(restored.rows[1]['height'], Decimal(0))
        self.assertEqual(restored.rows[0]['height'], Decimal('1.5'))

    def test_missing_position_filled_with_none(self):
        table = self.make_table()

        long_table, spec = table.normalize_with_spec(key='name')

        pruned = long_table.where(
            lambda row: not (row['row_position'] == 2 and row['column_position'] == 1)
        )

        restored = pruned.denormalize_with_spec(spec, fill_missing=None)

        self.assertIsNone(restored.rows[2]['age'])

    def test_conflicting_positions_error(self):
        table = self.make_table()

        long_table, spec = table.normalize_with_spec(key='name')

        duplicate = long_table.rows[0]
        rows = list(long_table.rows) + [duplicate]
        doubled = Table(rows, long_table.column_names, long_table.column_types, _is_fork=True)

        with self.assertRaises(ReshapeConflictError) as context:
            doubled.denormalize_with_spec(spec)

        self.assertIn((0, 'age'), context.exception.conflicts)

    def test_conflicting_positions_first_and_last(self):
        table = self.make_table()

        long_table, spec = table.normalize_with_spec(key='name')

        original = long_table.rows[0]
        replacement = list(original)
        replacement[-1] = Decimal(99)

        from agate.rows import Row
        extra = Row(tuple(replacement), long_table.column_names)

        doubled = Table(list(long_table.rows) + [extra], long_table.column_names,
                        long_table.column_types, _is_fork=True)

        restored_first = doubled.denormalize_with_spec(spec, on_conflict='first')
        restored_last = doubled.denormalize_with_spec(spec, on_conflict='last')

        self.assertEqual(restored_first.rows[0]['age'], Decimal(24))
        self.assertEqual(restored_last.rows[0]['age'], Decimal(99))

    def test_invalid_on_conflict(self):
        table = self.make_table()

        long_table, spec = table.normalize_with_spec(key='name')

        with self.assertRaises(ValueError):
            long_table.denormalize_with_spec(spec, on_conflict='bogus')

    def test_spec_contains_only_plain_data(self):
        table = self.make_table()

        _, spec = table.normalize_with_spec(key='name')

        def assert_plain(value):
            if isinstance(value, dict):
                for k, v in value.items():
                    self.assertIsInstance(k, str)
                    assert_plain(v)
            elif isinstance(value, (list, tuple)):
                for item in value:
                    assert_plain(item)
            else:
                self.assertNotIsInstance(value, DataType)
                self.assertFalse(callable(value))

        assert_plain(spec)

        # The spec survives a deep copy, so it holds no shared live objects.
        copied = copy.deepcopy(spec)
        self.assertEqual(copied, spec)

    def test_denormalize_rejects_executable_spec(self):
        table = self.make_table()

        long_table, spec = table.normalize_with_spec(key='name')

        spec['columns'][0]['type'] = Text()

        with self.assertRaises(ValueError):
            long_table.denormalize_with_spec(spec)

    def test_denormalize_rejects_wrong_format(self):
        table = self.make_table()

        long_table, _ = table.normalize_with_spec(key='name')

        with self.assertRaises(ValueError):
            long_table.denormalize_with_spec({'format': 'something-else'})

    def test_unregistered_custom_type_refused(self):
        table = Table(
            self.rows,
            self.column_names,
            [CustomText(), Number(), Number()]
        )

        with self.assertRaises(ValueError):
            table.normalize_with_spec(key='name')

    def test_registered_custom_type_round_trip(self):
        table = Table(
            self.rows,
            self.column_names,
            [CustomText(), Number(), Number()]
        )

        registry = {'CustomText': CustomText}

        long_table, spec = table.normalize_with_spec(key='name', type_registry=registry)

        self.assertEqual(spec['columns'][0]['type'], 'CustomText')

        restored = long_table.denormalize_with_spec(spec, type_registry=registry)

        self.assertRows(restored, self.rows)
        self.assertIsInstance(restored.column_types[0], CustomText)

    def test_globally_registered_custom_type_round_trip(self):
        register_data_type('CustomText', CustomText)

        try:
            table = Table(
                self.rows,
                self.column_names,
                [CustomText(), Number(), Number()]
            )

            long_table, spec = table.normalize_with_spec(key='name')
            restored = long_table.denormalize_with_spec(spec)

            self.assertRows(restored, self.rows)
            self.assertIsInstance(restored.column_types[0], CustomText)
        finally:
            from agate.table import reshape
            del reshape._REGISTERED_DATA_TYPES['CustomText']

    def test_denormalize_refuses_unknown_type(self):
        table = self.make_table()

        long_table, spec = table.normalize_with_spec(key='name')

        spec['columns'][0]['type'] = 'NoSuchType'

        with self.assertRaises(ValueError):
            long_table.denormalize_with_spec(spec)

    def test_input_table_not_modified(self):
        table = self.make_table()

        before = [tuple(row) for row in table.rows]

        long_table, spec = table.normalize_with_spec(key='name')
        long_table.denormalize_with_spec(spec)

        self.assertEqual([tuple(row) for row in table.rows], before)
        self.assertColumnNames(table, self.column_names)
        self.assertRowNames(table, self.row_names)

    def test_results_do_not_share_row_containers(self):
        table = self.make_table()

        long_table, spec = table.normalize_with_spec(key='name')
        restored = long_table.denormalize_with_spec(spec)

        original_ids = {id(row) for row in table.rows}
        long_ids = {id(row) for row in long_table.rows}
        restored_ids = {id(row) for row in restored.rows}

        self.assertFalse(original_ids & long_ids)
        self.assertFalse(original_ids & restored_ids)
        self.assertFalse(long_ids & restored_ids)

    def test_row_position_out_of_range(self):
        table = self.make_table()

        long_table, spec = table.normalize_with_spec(key='name')

        spec['row_count'] = 2

        with self.assertRaises(ValueError):
            long_table.denormalize_with_spec(spec)
