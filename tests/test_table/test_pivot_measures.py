import datetime as dt
from decimal import Decimal

from agate import Table
from agate.aggregations import Count, Min, Sum
from agate.data_types import Date, Number, Text
from agate.table.pivot_measures import PivotResult
from agate.testcase import AgateTestCase


class TestPivotMeasures(AgateTestCase):
    def setUp(self):
        self.rows = (
            ('joe', 'white_male', dt.date(2020, 1, 1), 20),
            ('jane', 'white_male', dt.date(2020, 1, 2), 20),
            ('josh', None, dt.date(2020, 1, 3), 20),
            ('jim', 'asian', None, 25),
        )

        self.column_names = ['name', 'race', 'seen', 'age']
        self.column_types = [Text(), Text(), Date(), Number()]

        self.table = Table(self.rows, self.column_names, self.column_types)

        self.measures = [
            ('total', Sum('age')),
            ('records', Count()),
            ('earliest', Min('seen')),
        ]

    def test_pivot_measures_returns_result(self):
        result = self.table.pivot_measures(self.measures, key='name', pivot='race')

        self.assertIsInstance(result, PivotResult)
        self.assertIsInstance(result.table, Table)

    def test_pivot_measures_columns_and_types(self):
        result = self.table.pivot_measures(self.measures, key='name', pivot='race')
        pivot_table = result.table

        self.assertColumnTypes(
            pivot_table,
            [Text, Number, Number, Date, Number, Number, Date, Number, Number, Date]
        )
        self.assertRowNames(pivot_table, ['joe', 'jane', 'josh', 'jim'])

        self.assertRows(pivot_table, [
            ('joe', Decimal(20), Decimal(1), dt.date(2020, 1, 1), Decimal(0), Decimal(0), None,
             Decimal(0), Decimal(0), None),
            ('jane', Decimal(20), Decimal(1), dt.date(2020, 1, 2), Decimal(0), Decimal(0), None,
             Decimal(0), Decimal(0), None),
            ('josh', Decimal(0), Decimal(0), None, Decimal(20), Decimal(1), dt.date(2020, 1, 3),
             Decimal(0), Decimal(0), None),
            ('jim', Decimal(0), Decimal(0), None, Decimal(0), Decimal(0), None,
             Decimal(25), Decimal(1), None),
        ])

    def test_pivot_measures_column_identity(self):
        result = self.table.pivot_measures(self.measures, key='name', pivot='race')

        self.assertEqual(
            result.column_keys(),
            (
                ('white_male', 'total'),
                ('white_male', 'records'),
                ('white_male', 'earliest'),
                (None, 'total'),
                (None, 'records'),
                (None, 'earliest'),
                ('asian', 'total'),
                ('asian', 'records'),
                ('asian', 'earliest'),
            )
        )

        for column_name, identity in result.column_identity.items():
            self.assertIsInstance(column_name, str)
            self.assertEqual(result.table.columns[column_name].name, column_name)
            self.assertEqual(identity, result.column_identity[column_name])

        self.assertEqual(
            result.column_names_for(None),
            ('total', 'records', 'earliest')
        )

    def test_pivot_measures_identity_table_is_exportable(self):
        result = self.table.pivot_measures(self.measures, key='name', pivot='race')
        identity_table = result.column_identity_table()

        self.assertColumnNames(identity_table, ['column_name', 'pivot_value', 'measure_name'])
        self.assertColumnTypes(identity_table, [Text, Text, Text])

        identity_rows = {row[0]: (row[1], row[2]) for row in identity_table.rows}

        self.assertEqual(identity_rows['total'], (None, 'total'))
        self.assertEqual(identity_rows['white_male…total'], ('white_male', 'total'))
        self.assertEqual(identity_rows['asian…earliest'], ('asian', 'earliest'))

        located = next(
            row for row in identity_table.rows
            if row[1] == 'white_male' and row[2] == 'earliest'
        )

        self.assertEqual(located[0], 'white_male…earliest')
        self.assertIn(located[0], result.table.column_names)

    def test_pivot_measures_separator_collision(self):
        rows = (
            ('a', 'x', 1),
            ('a', 'x…n', 2),
        )
        table = Table(rows, ['k', 'p', 'v'], [Text(), Text(), Number()])

        result = table.pivot_measures([('n', Sum('v'))], key='k', pivot='p')

        names = list(result.column_identity)

        self.assertEqual(len(names), len(set(names)))
        self.assertEqual(result.column_identity[names[0]], ('x', 'n'))
        self.assertEqual(result.column_identity[names[1]], ('x…n', 'n'))

        identity_table = result.column_identity_table()
        identities = {(row[1], row[2]): row[0] for row in identity_table.rows}

        self.assertEqual(identities[('x', 'n')], names[0])
        self.assertEqual(identities[('x…n', 'n')], names[1])

    def test_pivot_measures_missing_combination_vs_none_result(self):
        rows = (
            ('a', 'x', None),
            ('a', 'y', 5),
        )
        table = Table(rows, ['k', 'p', 'v'], [Text(), Text(), Number()])

        result = table.pivot_measures(
            [('minimum', Min('v'))],
            key='k',
            pivot='p',
            pivot_domain=['x', 'y', 'z']
        )

        column_by_identity = {identity: name for name, identity in result.column_identity.items()}

        self.assertEqual(
            tuple(result.table.rows[0]),
            ('a', None, Decimal(5), Decimal(0))
        )

        # The existing "x" group aggregates to None (all values null); the
        # unseen "z" combination receives the Number measure default of 0.
        self.assertEqual(result.table.rows[0][column_by_identity[('x', 'minimum')]], None)
        self.assertEqual(result.table.rows[0][column_by_identity[('z', 'minimum')]], Decimal(0))
        self.assertEqual(result.column_names_for('z'), ('z…minimum',))

    def test_pivot_measures_measure_default_value(self):
        result = self.table.pivot_measures(
            [('total', Sum('age')), ('earliest', Min('seen'), None)],
            key='name',
            pivot='race'
        )

        row = result.table.rows[0]

        self.assertEqual(row['white_male…earliest'], dt.date(2020, 1, 1))
        self.assertEqual(row['asian…earliest'], None)
        self.assertEqual(row['asian…total'], Decimal(0))

    def test_pivot_measures_text_measure_default_value(self):
        from agate.aggregations import First

        result = self.table.pivot_measures(
            [('first_name', First('name'), 'nobody')],
            key='race',
            pivot='age'
        )

        row = result.table.rows[0]

        self.assertEqual(row['20…first_name'], 'joe')
        self.assertEqual(row['25…first_name'], 'nobody')

    def test_pivot_measures_explicit_domain_and_none_axis(self):
        result = self.table.pivot_measures(
            self.measures,
            key='name',
            pivot='race',
            pivot_domain=['asian', None, 'unseen']
        )

        pivot_values = [value for value, measure_name in result.column_keys()]

        self.assertEqual(
            pivot_values,
            ['asian', 'asian', 'asian', None, None, None, 'unseen', 'unseen', 'unseen',
             'white_male', 'white_male', 'white_male']
        )

        self.assertEqual(
            result.column_names_for('unseen'),
            ('unseen…total', 'unseen…records', 'unseen…earliest')
        )

    def test_pivot_measures_empty_input_with_domain(self):
        table = Table([], self.column_names, self.column_types)

        result = table.pivot_measures(
            [('total', Sum('age')), ('earliest', Min('seen'))],
            key='name',
            pivot='race',
            pivot_domain=['a_b', None]
        )

        self.assertEqual(len(result.table.rows), 0)
        self.assertColumnNames(
            result.table,
            ['name', 'a_b…total', 'a_b…earliest', 'total', 'earliest']
        )
        self.assertColumnTypes(result.table, [Text, Number, Date, Number, Date])
        self.assertEqual(
            result.column_keys(),
            (('a_b', 'total'), ('a_b', 'earliest'), (None, 'total'), (None, 'earliest'))
        )

    def test_pivot_measures_empty_input_without_domain(self):
        table = Table([], self.column_names, self.column_types)

        result = table.pivot_measures([('total', Sum('age'))], key='name')

        self.assertEqual(len(result.table.rows), 0)
        self.assertColumnNames(result.table, ['name', 'total'])
        self.assertColumnTypes(result.table, [Text, Number])
        self.assertEqual(result.column_keys(), ((None, 'total'),))

    def test_pivot_measures_no_pivot(self):
        result = self.table.pivot_measures([('total', Sum('age')), ('records', Count())], key='race')

        self.assertColumnNames(result.table, ['race', 'total', 'records'])
        self.assertColumnTypes(result.table, [Text, Number, Number])
        self.assertRowNames(result.table, ['white_male', None, 'asian'])
        self.assertEqual(
            result.column_keys(),
            ((None, 'total'), (None, 'records'))
        )

    def test_pivot_measures_no_key(self):
        result = self.table.pivot_measures([('total', Sum('age')), ('records', Count())], pivot='race')

        self.assertIsNone(result.table.row_names)
        self.assertRows(
            result.table,
            [(Decimal(40), Decimal(2), Decimal(20), Decimal(1), Decimal(25), Decimal(1))]
        )

    def test_pivot_measures_multiple_keys_preserve_order(self):
        result = self.table.pivot_measures([('records', Count())], key=['race', 'name'], pivot='age')

        self.assertColumnNames(result.table, ['race', 'name', '20…records', '25…records'])
        self.assertRowNames(result.table, [
            ('white_male', 'joe'),
            ('white_male', 'jane'),
            (None, 'josh'),
            ('asian', 'jim'),
        ])

    def test_pivot_measures_function_keys(self):
        result = self.table.pivot_measures(
            [('records', Count())],
            key=lambda row: row['race'],
            pivot=lambda row: row['name'],
            key_name='race'
        )

        self.assertEqual(result.table.column_names[0], 'race')
        self.assertEqual(
            result.column_keys(),
            (('joe', 'records'), ('jane', 'records'), ('josh', 'records'), ('jim', 'records'))
        )
        self.assertRowNames(result.table, ['white_male', None, 'asian'])

    def test_pivot_measures_invalid_measure(self):
        with self.assertRaises(ValueError):
            self.table.pivot_measures([('only_one',)], key='name')

        with self.assertRaises(ValueError):
            self.table.pivot_measures([(1, Count())], key='name')

        with self.assertRaises(ValueError):
            self.table.pivot_measures([], key='name')

        with self.assertRaises(ValueError):
            self.table.pivot_measures([('n', Count())], pivot_domain=['x'])

        with self.assertRaises(ValueError):
            self.table.pivot_measures([('n', Count())], key=['race'], key_name='foo')

    def test_pivot_measures_default_value_precedence(self):
        table = Table(
            (('a', 'x', 1), ('a', 'y', 2)),
            ['k', 'p', 'v'],
            [Text(), Text(), Number()]
        )

        result = table.pivot_measures(
            [('sum', Sum('v')), ('count', Count(), Decimal(9))],
            key='k',
            pivot='p',
            pivot_domain=['x', 'y', 'z'],
            default_value=Decimal(7)
        )

        row = result.table.rows[0]

        self.assertEqual(row[result.column_names_for('z')[0]], Decimal(7))
        self.assertEqual(row[result.column_names_for('z')[1]], Decimal(9))
