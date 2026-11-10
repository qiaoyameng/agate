from collections import OrderedDict
from decimal import Decimal

from agate import utils
from agate.aggregations import Aggregation
from agate.data_types import Number, Text
from agate.rows import Row


class PivotResult:
    """
    The result of :meth:`.Table.pivot_measures`.

    The pivot table is available as :attr:`.table`. Because output column
    names must be unique strings while pivot axis values can be any value
    (including :code:`None` or strings containing separators), the original
    identity of every generated column is preserved in
    :attr:`.column_identity`.

    :param table:
        The :class:`.Table` produced by the pivot.
    :param column_identity:
        An :class:`collections.OrderedDict` mapping each generated column name
        to a :code:`(pivot_value, measure_name)` tuple.
    """
    def __init__(self, table, column_identity):
        self.table = table
        self.column_identity = column_identity

    def __getitem__(self, key):
        return self.table[key]

    def column_keys(self):
        """
        Return the ordered sequence of :code:`(pivot_value, measure_name)`
        tuples that identify the generated columns.
        """
        return tuple(self.column_identity.values())

    def column_names_for(self, pivot_value):
        """
        Return the ordered unique column names generated for one pivot value.
        """
        return tuple(
            column_name
            for column_name, (value, measure_name) in self.column_identity.items()
            if value == pivot_value
        )

    def column_identity_table(self):
        """
        Build an exportable :class:`.Table` describing the generated columns.

        Each row pairs the unique column name used in :attr:`.table` with the
        original pivot axis value and the measure name. Pivot values are cast
        with :class:`.Text`, so :code:`None` and values containing separators
        stay distinguishable from the headers used in the pivot table.
        """
        from agate.table import Table

        rows = [
            (column_name, pivot_value, measure_name)
            for column_name, (pivot_value, measure_name) in self.column_identity.items()
        ]

        return Table(
            rows,
            ['column_name', 'pivot_value', 'measure_name'],
            [Text(), Text(), Text()]
        )

    def __repr__(self):
        return f'<agate.PivotResult: {len(self.column_identity)} measure columns>'


def pivot_measures(self, measures, key=None, pivot=None, pivot_domain=None, default_value=utils.default,
                   key_name=None):
    """
    Pivot a table around several measures at once.

    Unlike :meth:`.Table.pivot`, which organizes the result around a single
    :class:`.Aggregation`, each generated column is identified by the pair
    :code:`(pivot axis value, measure name)`. This makes it possible to report,
    for example, a sum, a count and an earliest date for every pivot value in
    a single table while preserving each measure's own :class:`.DataType`.

    Column names in agate tables must be unique strings, so the original
    :code:`(pivot value, measure name)` identities are exported separately on
    the returned :class:`.PivotResult`. Collisions, including pivot values
    that contain separators, are disambiguated with a numeric suffix rather
    than by joining the two values with an underscore.

    Cells for row/pivot combinations that do not exist in the data are filled
    with the measure's declared default value. A group that exists but whose
    aggregation returns :code:`None` keeps that :code:`None` result.

    :param measures:
        A sequence of measure declarations. Each declaration is either a
        :code:`(name, aggregation)` tuple or a
        :code:`(name, aggregation, default_value)` tuple, where :code:`name`
        is a string and :code:`aggregation` is an :class:`.Aggregation`
        instance. A measure without an explicit default uses
        :code:`Decimal(0)` when its data type is :class:`.Number` and
        :code:`None` otherwise.
    :param key:
        Either the name of a column to group by, a sequence of such column
        names, a :class:`function` that takes a row and returns a value to
        group by, or :code:`None`, in which case there is a single output row.
    :param pivot:
        A column name whose unique values become columns, a
        :class:`function` that takes a row and returns the pivot value, or
        :code:`None`, in which case there is one column per measure.
    :param pivot_domain:
        An explicit sequence of pivot axis values, which may include
        :code:`None`. It guarantees a stable set of columns for empty input
        or for values that do not occur in the data. When omitted, axis
        values are taken in first-appearance order.
    :param default_value:
        Fallback for measures that do not declare their own default value.
    :param key_name:
        A name for the key column when :code:`key` is a function. Not valid
        when :code:`key` is a sequence.
    :returns:
        A :class:`.PivotResult`.
    """
    if key is None:
        key = []
    elif not utils.issequence(key):
        key = [key]
    elif key_name:
        raise ValueError('key_name is not a valid argument when key is a sequence.')

    if pivot is None and pivot_domain is not None:
        raise ValueError('pivot_domain can only be used when a pivot column or function is provided.')

    normalized_measures = _normalize_measures(measures)

    measure_types = OrderedDict(
        (measure_name, aggregation.get_aggregate_data_type(self))
        for measure_name, aggregation, measure_default in normalized_measures
    )
    measure_defaults = _resolve_defaults(normalized_measures, measure_types, default_value)

    key_names = []
    key_types = []

    pivot_is_function = pivot is not None and hasattr(pivot, '__call__')

    if pivot is not None and not pivot_is_function:
        pivot_name = self._columns[pivot].name
        pivot_type = self._columns[pivot].data_type
    elif pivot_is_function:
        pivot_name = 'pivot'
        pivot_type = Text()
    else:
        pivot_name = None
        pivot_type = None

    aggregations = [(measure_name, aggregation) for measure_name, aggregation, measure_default in normalized_measures]

    if len(self.rows) == 0:
        for group_key in key:
            if hasattr(group_key, '__call__'):
                key_names.append(key_name or 'group')
                key_types.append(Text())
            else:
                key_names.append(self._columns[group_key].name)
                key_types.append(self._columns[group_key].data_type)

        aggregated = _empty_aggregate_table(key_names, key_types, pivot, pivot_name, pivot_type, aggregations,
                                            measure_types)
    else:
        groups = self

        for group_key in key:
            if hasattr(group_key, '__call__'):
                groups = groups.group_by(group_key, key_name=key_name)
            else:
                groups = groups.group_by(group_key)

            key_names.append(groups.key_name)
            key_types.append(groups.key_type)

        if pivot is not None:
            if pivot_is_function:
                groups = groups.group_by(pivot, key_name=pivot_name)
            else:
                groups = groups.group_by(pivot)

        aggregated = groups.aggregate(aggregations)

    measure_names = [measure_name for measure_name, aggregation, measure_default in normalized_measures]

    if pivot is not None:
        observed_values = list(OrderedDict.fromkeys(aggregated.columns[pivot_name].values()))
    else:
        observed_values = [None]

    pivot_values = _resolve_pivot_values(pivot_domain, pivot_type, observed_values)

    value_column_names = set(measure_names)

    if pivot is not None:
        value_column_names.add(pivot_name)

    row_key_names = [name for name in aggregated.column_names if name not in value_column_names]

    cells = OrderedDict()

    for row in aggregated.rows:
        row_key = tuple(row[name] for name in row_key_names)
        pivot_value = row[pivot_name] if pivot is not None else None

        cells.setdefault(row_key, {})

        for measure_name in measure_names:
            cells[row_key][(pivot_value, measure_name)] = row[measure_name]

    column_identity = OrderedDict()
    used_names = []

    for pivot_value in pivot_values:
        for measure_name in measure_names:
            column_name = _unique_name(_column_base_name(pivot_value, measure_name), used_names)

            used_names.append(column_name)
            column_identity[column_name] = (pivot_value, measure_name)

    new_column_names = row_key_names + list(column_identity.keys())

    row_key_types = [
        aggregated.column_types[aggregated.column_names.index(name)]
        for name in row_key_names
    ]
    generated_column_types = [
        measure_types[measure_name]
        for pivot_value in pivot_values
        for measure_name in measure_names
    ]

    new_rows = []
    row_names = []

    for row_key, row_cells in cells.items():
        row = list(row_key)

        if row_key:
            row_names.append(row_key[0] if len(row_key) == 1 else row_key)

        for column_name, (pivot_value, measure_name) in column_identity.items():
            identity = (pivot_value, measure_name)

            if identity in row_cells:
                row.append(row_cells[identity])
            else:
                row.append(measure_defaults[measure_name])

        new_rows.append(Row(row, new_column_names))

    from agate.table import Table

    new_table = Table(
        new_rows,
        new_column_names,
        row_key_types + generated_column_types,
        row_names=row_names or None
    )

    return PivotResult(new_table, column_identity)


def _normalize_measures(measures):
    normalized_measures = []

    for measure in measures:
        if len(measure) == 2:
            measure_name, aggregation = measure
            measure_default = utils.default
        elif len(measure) == 3:
            measure_name, aggregation, measure_default = measure
        else:
            raise ValueError(
                'Each measure must be a (name, aggregation) or (name, aggregation, default_value) tuple.'
            )

        if not isinstance(measure_name, str):
            raise ValueError('Measure names must be strings.')

        if not isinstance(aggregation, Aggregation):
            raise ValueError('Each measure must be backed by an Aggregation instance.')

        normalized_measures.append((measure_name, aggregation, measure_default))

    if not normalized_measures:
        raise ValueError('At least one measure is required.')

    return normalized_measures


def _empty_aggregate_table(key_names, key_types, pivot, pivot_name, pivot_type, aggregations, measure_types):
    from agate.table import Table

    column_names = list(key_names)
    column_types = list(key_types)

    if pivot is not None:
        column_names.append(pivot_name)
        column_types.append(pivot_type)

    column_names.extend(name for name, aggregation in aggregations)
    column_types.extend(measure_types[name] for name, aggregation in aggregations)

    return Table([], column_names, column_types)


def _resolve_pivot_values(pivot_domain, pivot_type, observed_values):
    if pivot_domain is None:
        return list(observed_values)

    pivot_values = []

    for value in pivot_domain:
        cast_value = pivot_type.cast(value) if pivot_type is not None else value

        if cast_value not in pivot_values:
            pivot_values.append(cast_value)

    for value in observed_values:
        if value not in pivot_values:
            pivot_values.append(value)

    return pivot_values


def _resolve_defaults(normalized_measures, measure_types, default_value):
    measure_defaults = OrderedDict()

    for measure_name, aggregation, measure_default in normalized_measures:
        if measure_default is not utils.default:
            resolved_default = measure_default
        elif default_value is not utils.default:
            resolved_default = default_value
        elif isinstance(measure_types[measure_name], Number):
            resolved_default = Decimal(0)
        else:
            resolved_default = None

        measure_defaults[measure_name] = resolved_default

    return measure_defaults


def _column_base_name(pivot_value, measure_name):
    if pivot_value is None:
        return measure_name

    return f'{pivot_value}…{measure_name}'


def _unique_name(base_name, existing_names):
    if base_name not in existing_names:
        return base_name

    suffix = 2

    while f'{base_name}_{suffix}' in existing_names:
        suffix += 1

    return f'{base_name}_{suffix}'
