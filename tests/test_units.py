import io
import unittest
from decimal import Decimal

from agate import Table
from agate.data_types import Number, Text
from agate.exceptions import UnitError
from agate.units import (
    CELSIUS,
    CELSIUS_DELTA,
    CENTIMETER,
    KELVIN,
    KELVIN_DELTA,
    METER,
    MILLISECOND,
    SECOND,
    Unit,
    convert_value,
)


class TestUnitModel(unittest.TestCase):
    def test_scales_and_offsets_are_decimals(self):
        for unit in (METER, CENTIMETER, SECOND, MILLISECOND, KELVIN, CELSIUS, KELVIN_DELTA, CELSIUS_DELTA):
            self.assertIsInstance(unit.scale, Decimal)
            self.assertIsInstance(unit.offset, Decimal)

        self.assertEqual(CENTIMETER.scale, Decimal('0.01'))
        self.assertEqual(MILLISECOND.scale, Decimal('0.001'))
        self.assertEqual(CELSIUS.offset, Decimal('273.15'))

    def test_length_conversion(self):
        self.assertEqual(METER.convert(Decimal('1'), CENTIMETER), Decimal('100'))
        self.assertEqual(CENTIMETER.convert(Decimal('150'), METER), Decimal('1.50'))

    def test_time_conversion(self):
        self.assertEqual(SECOND.convert(Decimal('1'), MILLISECOND), Decimal('1000'))
        self.assertEqual(MILLISECOND.convert(Decimal('2500'), SECOND), Decimal('2.500'))

    def test_temperature_conversion_keeps_offset(self):
        self.assertEqual(CELSIUS.convert(Decimal('0'), KELVIN), Decimal('273.15'))
        self.assertEqual(KELVIN.convert(Decimal('373.15'), CELSIUS), Decimal('100'))

    def test_null_passes_through(self):
        self.assertIsNone(METER.convert(None, CENTIMETER))
        self.assertIsNone(convert_value(None, METER, CENTIMETER))

    def test_cross_dimension_rejected(self):
        with self.assertRaises(UnitError):
            METER.convert(Decimal('1'), SECOND)

        with self.assertRaises(UnitError):
            CELSIUS.convert(Decimal('1'), KELVIN_DELTA)

    def test_absolute_and_delta_are_not_compatible(self):
        self.assertFalse(KELVIN.is_compatible(KELVIN_DELTA))
        self.assertTrue(KELVIN_DELTA.is_compatible(CELSIUS_DELTA))

    def test_delta_units_have_no_offset(self):
        self.assertEqual(CELSIUS.delta_unit(), KELVIN_DELTA)
        self.assertEqual(METER.delta_unit(), METER)
        self.assertEqual(KELVIN_DELTA.offset, Decimal(0))

        with self.assertRaises(ValueError):
            Unit('x', 'custom', offset=Decimal('1'), absolute=False)

    def test_custom_unit(self):
        inch = Unit('in', 'length', scale=Decimal('0.0254'))

        self.assertEqual(inch.convert(Decimal('100'), METER), Decimal('2.5400'))
        self.assertEqual(METER.convert(Decimal('2.54'), inch), Decimal('100.00'))

    def test_equality_and_hash(self):
        self.assertEqual(Unit('m', 'length'), METER)
        self.assertEqual(hash(Unit('m', 'length')), hash(METER))
        self.assertNotEqual(METER, CENTIMETER)


class TestTableUnits(unittest.TestCase):
    def setUp(self):
        self.number_type = Number()
        self.text_type = Text()

    def _table(self, units):
        rows = ((Decimal('1'), Decimal('100'), 'a'),)

        return Table(
            rows,
            ['meters', 'centimeters', 'label'],
            [self.number_type, self.number_type, self.text_type],
            column_units=units,
        )

    def test_units_attached_to_columns(self):
        table = self._table([METER, CENTIMETER, None])

        self.assertEqual(table.column_units, (METER, CENTIMETER, None))
        self.assertEqual(table.columns['meters'].unit, METER)
        self.assertIsNone(table.columns['label'].unit)

    def test_units_as_dict(self):
        table = Table(
            ((Decimal('1'),),),
            ['meters'],
            [self.number_type],
            column_units={'meters': METER},
        )

        self.assertEqual(table.column_units, (METER,))

    def test_unit_requires_number_column(self):
        with self.assertRaises(ValueError):
            self._table([None, None, METER])

    def test_wrong_length_rejected(self):
        with self.assertRaises(ValueError):
            self._table([METER])

    def test_ununitized_table_has_none_units(self):
        table = Table(((1, 2),), ['a', 'b'], [self.number_type, self.number_type])

        self.assertEqual(table.column_units, (None, None))

    def test_select_carries_units(self):
        table = self._table([METER, CENTIMETER, None])
        selected = table.select(['centimeters', 'meters'])

        self.assertEqual(selected.column_units, (CENTIMETER, METER))

    def test_rename_keeps_identity_based_units(self):
        table = self._table([METER, CENTIMETER, None])
        renamed = table.rename(column_names={'meters': 'centimeters', 'centimeters': 'meters'})

        self.assertEqual(renamed.column_names, ('centimeters', 'meters', 'label'))
        self.assertEqual(renamed.column_units, (METER, CENTIMETER, None))
        self.assertEqual(renamed.columns['centimeters'].unit, METER)
        self.assertEqual(renamed.columns['meters'].unit, CENTIMETER)

    def test_join_keeps_units_on_duplicated_column_names(self):
        left = Table(
            ((1, Decimal('2')),),
            ['key', 'value'],
            [self.number_type, self.number_type],
            column_units=[None, METER],
        )
        right = Table(
            ((1, Decimal('300')),),
            ['key', 'value'],
            [self.number_type, self.number_type],
            column_units=[None, CENTIMETER],
        )

        joined = left.join(right, 'key')

        self.assertEqual(joined.column_names, ('key', 'value', 'value2'))
        self.assertEqual(joined.columns['value'].unit, METER)
        self.assertEqual(joined.columns['value2'].unit, CENTIMETER)

    def test_explicit_convert(self):
        table = self._table([METER, CENTIMETER, None])
        converted = table.convert({'centimeters': METER})

        self.assertEqual(converted.rows[0]['centimeters'], Decimal('1.00'))
        self.assertEqual(converted.columns['centimeters'].unit, METER)
        self.assertEqual(table.rows[0]['centimeters'], Decimal('100'))

        converted_tuple = table.convert(('meters', CENTIMETER))
        self.assertEqual(converted_tuple.rows[0]['meters'], Decimal('100'))
        self.assertEqual(converted_tuple.columns['meters'].unit, CENTIMETER)

    def test_convert_rejects_unknown_dimension(self):
        table = self._table([METER, CENTIMETER, None])

        with self.assertRaises(UnitError):
            table.convert({'meters': SECOND})

    def test_column_convert(self):
        table = self._table([METER, CENTIMETER, None])

        self.assertEqual(table.columns['centimeters'].convert(METER), (Decimal('1.00'),))
        self.assertIsNone(table.columns['label'].unit)

    def test_merge_rejects_conflicting_units(self):
        first = Table(
            ((Decimal('1'),),),
            ['value'],
            [self.number_type],
            column_units=[METER],
        )
        second = Table(
            ((Decimal('100'),),),
            ['value'],
            [self.number_type],
            column_units=[CENTIMETER],
        )

        with self.assertRaises(UnitError):
            Table.merge([first, second])

        merged = Table.merge([first, second.convert({'value': METER})])
        self.assertEqual(merged.column_units, (METER,))
        self.assertEqual(merged.rows[1]['value'], Decimal('1.00'))

    def test_merge_accepts_unit_and_none(self):
        unitized = Table(
            ((Decimal('1'),),),
            ['value'],
            [self.number_type],
            column_units=[METER],
        )
        plain = Table(((Decimal('2'),),), ['value'], [self.number_type])

        merged = Table.merge([unitized, plain])
        self.assertEqual(merged.column_units, (METER,))

    def test_from_csv_attaches_units(self):
        import agate

        csv_file = io.StringIO('meters,centimeters\n1,100\n2,200\n')

        table = agate.Table.from_csv(
            csv_file,
            column_types=[Number(), Number()],
            column_units=[METER, CENTIMETER],
        )

        self.assertEqual(table.column_units, (METER, CENTIMETER))
        self.assertEqual(table.rows[1]['centimeters'], Decimal('200'))


if __name__ == '__main__':
    unittest.main()
