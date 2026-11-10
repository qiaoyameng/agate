import datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from agate import Table
from agate.aggregations import Count, Sum
from agate.data_types import Date, DateTime, Number, Text
from agate.exceptions import DataTypeError
from agate.testcase import AgateTestCase


class TestResample(AgateTestCase):
    def setUp(self):
        self.tz = ZoneInfo('America/New_York')
        self.column_names = ['when', 'amount']
        self.column_types = [DateTime(), Number()]

    def make_table(self, rows):
        return Table(rows, self.column_names, self.column_types)

    def test_day_buckets_around_dst_spring_forward(self):
        # 2024-03-10 is the spring-forward day in America/New_York: it lasts
        # 23 hours, not 86400 seconds.
        rows = [
            [datetime.datetime(2024, 3, 9, 23, 30, tzinfo=self.tz), Decimal('1')],
            [datetime.datetime(2024, 3, 10, 1, 30, tzinfo=self.tz), Decimal('2')],
            [datetime.datetime(2024, 3, 10, 3, 30, tzinfo=self.tz), Decimal('4')],
            [datetime.datetime(2024, 3, 10, 23, 30, tzinfo=self.tz), Decimal('8')],
            [datetime.datetime(2024, 3, 11, 0, 30, tzinfo=self.tz), Decimal('16')],
        ]

        table = self.make_table(rows)
        result = table.resample('when', freq='day', timezone=self.tz, aggregations=[
            ('count', Count()),
            ('total', Sum('amount'))
        ])

        self.assertColumnNames(result, ['start', 'end', 'count', 'total'])
        self.assertColumnTypes(result, [DateTime, DateTime, Number, Number])
        self.assertEqual(len(result.rows), 3)

        self.assertEqual(result.rows[0]['start'], datetime.datetime(2024, 3, 9, tzinfo=self.tz))
        self.assertEqual(result.rows[0]['end'], datetime.datetime(2024, 3, 10, tzinfo=self.tz))
        self.assertEqual(result.rows[1]['start'], datetime.datetime(2024, 3, 10, tzinfo=self.tz))
        self.assertEqual(result.rows[1]['end'], datetime.datetime(2024, 3, 11, tzinfo=self.tz))

        # The DST day bucket spans 23 actual hours, not 86400 seconds
        dst_day = result.rows[1]
        utc = datetime.timezone.utc
        elapsed = dst_day['end'].astimezone(utc) - dst_day['start'].astimezone(utc)
        self.assertEqual(elapsed.total_seconds(), 23 * 3600)

        self.assertSequenceEqual(result.columns['count'].values(), [1, 3, 1])
        self.assertSequenceEqual(
            result.columns['total'].values(),
            [Decimal('1'), Decimal('14'), Decimal('16')]
        )

        # Every event falls into exactly one bucket
        for row in table.rows:
            matches = [
                r for r in result.rows
                if r['start'] <= row['when'] < r['end']
            ]
            self.assertEqual(len(matches), 1)

    def test_day_buckets_around_dst_fall_back(self):
        # 2024-11-03 is the fall-back day in America/New_York: 25 hours.
        rows = [
            [datetime.datetime(2024, 11, 3, 1, 30, tzinfo=self.tz), Decimal('1')],
        ]

        result = self.make_table(rows).resample('when', timezone=self.tz)

        day = result.rows[0]
        utc = datetime.timezone.utc
        elapsed = day['end'].astimezone(utc) - day['start'].astimezone(utc)
        self.assertEqual(elapsed.total_seconds(), 25 * 3600)

    def test_month_buckets_around_month_end(self):
        rows = [
            [datetime.datetime(2024, 1, 31, 23, 30, tzinfo=self.tz), Decimal('1')],
            [datetime.datetime(2024, 2, 1, 0, 30, tzinfo=self.tz), Decimal('2')],
        ]

        result = self.make_table(rows).resample('when', freq='month', timezone=self.tz)

        self.assertEqual(len(result.rows), 2)
        self.assertEqual(result.rows[0]['start'], datetime.datetime(2024, 1, 1, tzinfo=self.tz))
        self.assertEqual(result.rows[0]['end'], datetime.datetime(2024, 2, 1, tzinfo=self.tz))
        self.assertEqual(result.rows[1]['start'], datetime.datetime(2024, 2, 1, tzinfo=self.tz))
        self.assertEqual(result.rows[1]['end'], datetime.datetime(2024, 3, 1, tzinfo=self.tz))
        self.assertSequenceEqual(result.columns['count'].values(), [1, 1])

    def test_week_buckets_respect_week_start(self):
        # 2024-03-10 is a Sunday
        rows = [
            [datetime.datetime(2024, 3, 10, 12, 0, tzinfo=self.tz), Decimal('1')],
        ]
        table = self.make_table(rows)

        monday = table.resample('when', freq='week', timezone=self.tz, week_start=0)
        sunday = table.resample('when', freq='week', timezone=self.tz, week_start=6)

        self.assertEqual(monday.rows[0]['start'], datetime.datetime(2024, 3, 4, tzinfo=self.tz))
        self.assertEqual(monday.rows[0]['end'], datetime.datetime(2024, 3, 11, tzinfo=self.tz))
        self.assertEqual(sunday.rows[0]['start'], datetime.datetime(2024, 3, 10, tzinfo=self.tz))
        self.assertEqual(sunday.rows[0]['end'], datetime.datetime(2024, 3, 17, tzinfo=self.tz))

    def test_fill_empty_buckets(self):
        rows = [
            [datetime.datetime(2024, 3, 9, 12, 0, tzinfo=self.tz), Decimal('1')],
            [datetime.datetime(2024, 3, 11, 12, 0, tzinfo=self.tz), Decimal('2')],
        ]

        result = self.make_table(rows).resample(
            'when', timezone=self.tz, fill=True,
            start=datetime.date(2024, 3, 9), end=datetime.date(2024, 3, 11),
            aggregations=[('count', Count()), ('total', Sum('amount'))]
        )

        self.assertEqual(len(result.rows), 3)
        self.assertSequenceEqual(result.columns['count'].values(), [1, 0, 1])

        # Empty bucket sum follows the existing aggregation null rules
        self.assertEqual(result.rows[1]['total'], 0)

        # Filled buckets tile the range without overlapping in actual time
        for previous, current in zip(result.rows, result.rows[1:]):
            self.assertLess(previous['start'], current['start'])
            self.assertEqual(previous['end'], current['start'])

    def test_group_by(self):
        column_names = ['when', 'kind', 'amount']
        column_types = [DateTime(), Text(), Number()]
        rows = [
            [datetime.datetime(2024, 3, 9, 12, 0, tzinfo=self.tz), 'a', Decimal('1')],
            [datetime.datetime(2024, 3, 9, 13, 0, tzinfo=self.tz), 'b', Decimal('2')],
            [datetime.datetime(2024, 3, 10, 12, 0, tzinfo=self.tz), 'a', Decimal('4')],
        ]

        result = Table(rows, column_names, column_types).resample(
            'when', timezone=self.tz, group_by='kind'
        )

        self.assertColumnNames(result, ['kind', 'start', 'end', 'count'])
        self.assertEqual(len(result.rows), 3)
        self.assertSequenceEqual(result.columns['kind'].values(), ['a', 'a', 'b'])
        self.assertSequenceEqual(result.columns['count'].values(), [1, 1, 1])

    def test_explicit_range_excludes_outlying_events(self):
        rows = [
            [datetime.datetime(2024, 3, 8, 12, 0, tzinfo=self.tz), Decimal('1')],
            [datetime.datetime(2024, 3, 9, 12, 0, tzinfo=self.tz), Decimal('2')],
            [datetime.datetime(2024, 3, 10, 12, 0, tzinfo=self.tz), Decimal('4')],
        ]

        result = self.make_table(rows).resample(
            'when', timezone=self.tz,
            start=datetime.date(2024, 3, 9), end=datetime.date(2024, 3, 9)
        )

        self.assertEqual(len(result.rows), 1)
        self.assertEqual(result.rows[0]['count'], 1)

    def test_naive_datetimes_rejected(self):
        rows = [
            [datetime.datetime(2024, 3, 9, 12, 0), Decimal('1')],
        ]

        with self.assertRaises(DataTypeError):
            self.make_table(rows).resample('when', timezone=self.tz)

    def test_dates_rejected(self):
        rows = [
            [datetime.date(2024, 3, 9), Decimal('1')],
        ]

        table = Table(rows, self.column_names, [Date(), Number()])

        with self.assertRaises(DataTypeError):
            table.resample('when', timezone=self.tz)

    def test_reversed_range_rejected(self):
        rows = [
            [datetime.datetime(2024, 3, 9, 12, 0, tzinfo=self.tz), Decimal('1')],
        ]

        with self.assertRaises(ValueError):
            self.make_table(rows).resample(
                'when', timezone=self.tz,
                start=datetime.date(2024, 3, 10), end=datetime.date(2024, 3, 9)
            )

    def test_invalid_freq_rejected(self):
        rows = [
            [datetime.datetime(2024, 3, 9, 12, 0, tzinfo=self.tz), Decimal('1')],
        ]

        with self.assertRaises(ValueError):
            self.make_table(rows).resample('when', freq='hour', timezone=self.tz)
