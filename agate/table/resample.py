import datetime
from collections import OrderedDict
from zoneinfo import ZoneInfo

from agate import utils
from agate.aggregations import Count
from agate.aggregations.base import Aggregation
from agate.data_types import DateTime
from agate.exceptions import DataTypeError
from agate.table import Table


def _floor_date(d, freq, week_start):
    if freq == 'day':
        return d
    if freq == 'week':
        return d - datetime.timedelta(days=(d.weekday() - week_start) % 7)
    # freq == 'month'
    return d.replace(day=1)


def _next_date(d, freq):
    if freq == 'day':
        return d + datetime.timedelta(days=1)
    if freq == 'week':
        return d + datetime.timedelta(days=7)
    # freq == 'month'
    if d.month == 12:
        return d.replace(year=d.year + 1, month=1)
    return d.replace(month=d.month + 1)


def _midnight(d, tz):
    return datetime.datetime(d.year, d.month, d.day, tzinfo=tz)


def resample(self, column_name, freq='day', timezone=None, group_by=None,
             aggregations=None, start=None, end=None, week_start=0, fill=False):
    """
    Group rows into calendar buckets computed in a specific timezone and
    aggregate each bucket.

    Bucket boundaries are determined by the calendar in the given timezone
    and then converted to actual points in time. This means a day bucket is
    not necessarily 24 hours long: on days when a daylight saving time
    transition occurs it will be 23 or 25 hours. Buckets are half-open
    intervals, :code:`[start, end)`, so every instant falls into exactly one
    bucket.

    The values in the specified column must be timezone-aware
    :class:`datetime.datetime` instances. Naive datetimes and
    :class:`datetime.date` values are rejected before any calculation is
    performed.

    The resulting table has one row per group and bucket. It contains the
    grouping columns (if any), a :code:`start` and an :code:`end` column of
    type :class:`.DateTime` with the bucket boundaries, and one column per
    aggregation.

    :param column_name:
        The name of a column containing timezone-aware :class:`.DateTime`
        data.
    :param freq:
        The calendar frequency of the buckets: :code:`'day'`, :code:`'week'`
        or :code:`'month'`.
    :param timezone:
        The timezone whose calendar determines the bucket boundaries. Either
        a :class:`datetime.tzinfo` instance (such as
        :class:`zoneinfo.ZoneInfo`) or an IANA timezone name such as
        :code:`'America/New_York'`. Defaults to UTC.
    :param group_by:
        An optional column name, or sequence of column names, to group by
        before resampling. Each unique combination of values is resampled
        independently.
    :param aggregations:
        A sequence of :code:`(name, aggregation)` tuples, or a single
        :class:`.Aggregation`. If not specified, defaults to
        :class:`.Count` of the rows in each bucket.
    :param start:
        An optional :class:`datetime.date` or timezone-aware
        :class:`datetime.datetime` limiting the range of buckets. Buckets
        are generated starting with the one containing this value. Defaults
        to the minimum value in the column.
    :param end:
        An optional :class:`datetime.date` or timezone-aware
        :class:`datetime.datetime` limiting the range of buckets. Buckets
        are generated up to and including the one containing this value.
        Defaults to the maximum value in the column.
    :param week_start:
        The first day of the week when :code:`freq` is :code:`'week'`, as an
        integer where Monday is 0 and Sunday is 6. Defaults to 0 (Monday).
    :param fill:
        If :code:`True`, emit rows for buckets that contain no data. Empty
        buckets aggregate their (empty) set of rows, so a :class:`.Count`
        will be zero and other aggregations follow their usual null
        handling.
    :returns:
        A new :class:`Table`.
    """
    if freq not in ('day', 'week', 'month'):
        raise ValueError('freq must be one of "day", "week" or "month".')

    if not isinstance(week_start, int) or not 0 <= week_start <= 6:
        raise ValueError('week_start must be an integer between 0 (Monday) and 6 (Sunday).')

    if timezone is None:
        tz = datetime.timezone.utc
    elif isinstance(timezone, str):
        tz = ZoneInfo(timezone)
    elif isinstance(timezone, datetime.tzinfo):
        tz = timezone
    else:
        raise ValueError('timezone must be a tzinfo instance or an IANA timezone name.')

    column = self._columns[column_name]

    if not isinstance(column.data_type, DateTime):
        raise DataTypeError('resample can only be applied to columns containing DateTime data.')

    values = []

    for value in column.values():
        if value is None:
            continue
        if not isinstance(value, datetime.datetime):
            raise DataTypeError('resample requires datetime values, not date values.')
        if value.tzinfo is None or value.tzinfo.utcoffset(value) is None:
            raise DataTypeError('resample requires timezone-aware datetime values.')
        values.append(value)

    def to_local_date(value, name):
        if isinstance(value, datetime.datetime):
            if value.tzinfo is None or value.tzinfo.utcoffset(value) is None:
                raise ValueError('%s must be a timezone-aware datetime or a date.' % name)
            return value.astimezone(tz).date()
        if isinstance(value, datetime.date):
            return value
        raise ValueError('%s must be a date or a timezone-aware datetime.' % name)

    if start is not None:
        start_date = to_local_date(start, 'start')
    elif values:
        start_date = min(v.astimezone(tz).date() for v in values)
    else:
        raise ValueError('start is required when the column contains no values.')

    if end is not None:
        end_date = to_local_date(end, 'end')
    elif values:
        end_date = max(v.astimezone(tz).date() for v in values)
    else:
        raise ValueError('end is required when the column contains no values.')

    first = _floor_date(start_date, freq, week_start)
    last = _floor_date(end_date, freq, week_start)

    if first > last:
        raise ValueError('start must not be after end.')

    bucket_dates = []
    d = first

    while d <= last:
        bucket_dates.append(d)
        d = _next_date(d, freq)

    if group_by is None:
        group_names = []
    elif utils.issequence(group_by):
        group_names = list(group_by)
    else:
        group_names = [group_by]

    group_types = [self._columns[name].data_type for name in group_names]

    if aggregations is None:
        aggregations = [('count', Count())]
    elif isinstance(aggregations, Aggregation):
        aggregations = [(str(aggregations), aggregations)]
    else:
        aggregations = [
            tuple(item) if utils.issequence(item) else (str(item), item)
            for item in aggregations
        ]

    for _, aggregation in aggregations:
        aggregation.validate(self)

    # Assign each row to its group and bucket
    groups = OrderedDict()

    for row in self._rows:
        value = row[column_name]

        if value is None:
            continue

        bucket_date = _floor_date(value.astimezone(tz).date(), freq, week_start)

        if bucket_date < first or bucket_date > last:
            continue

        key = tuple(row[name] for name in group_names)
        buckets = groups.setdefault(key, {})
        buckets.setdefault(bucket_date, []).append(row)

    column_names = group_names + ['start', 'end'] + [name for name, _ in aggregations]
    column_types = group_types + [DateTime(), DateTime()] + [
        aggregation.get_aggregate_data_type(self) for _, aggregation in aggregations
    ]

    rows = []

    for key, buckets in groups.items():
        dates = bucket_dates if fill else sorted(buckets.keys())

        for bucket_date in dates:
            bucket_rows = buckets.get(bucket_date, [])
            sub_table = self._fork(bucket_rows)

            next_date = _next_date(bucket_date, freq)

            new_row = list(key)
            new_row.append(_midnight(bucket_date, tz))
            new_row.append(_midnight(next_date, tz))

            for _, aggregation in aggregations:
                new_row.append(aggregation.run(sub_table))

            rows.append(new_row)

    if group_names:
        key_columns = group_names + ['start']

        def row_names(r):
            return tuple(r[n] for n in key_columns)
    else:
        row_names = 'start'

    return Table(rows, column_names, column_types, row_names=row_names)
