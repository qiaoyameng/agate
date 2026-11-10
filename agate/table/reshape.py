"""
Explicit, reversible reshaping between wide and long tables.

Unlike :meth:`.Table.normalize` and :meth:`.Table.denormalize`, which infer
structure from values, these methods emit and consume an explicit structure
description so that a table can be converted to a long format and restored
without guessing row names, column types or which cells were originally null.
"""

from decimal import Decimal

from agate import utils
from agate.data_types import Boolean, DataType, Date, DateTime, Number, Text, TimeDelta
from agate.exceptions import ReshapeConflictError, ReshapeMissingError
from agate.rows import Row

#: Value of the ``format`` field in reshape structure descriptions.
SPEC_FORMAT = 'agate-reshape'

#: Version of the structure description emitted by this module.
SPEC_VERSION = 1

_DEFAULT_TYPE_REGISTRY = {
    'Boolean': Boolean,
    'Date': Date,
    'DateTime': DateTime,
    'Number': Number,
    'Text': Text,
    'TimeDelta': TimeDelta,
}

_REGISTERED_DATA_TYPES = dict(_DEFAULT_TYPE_REGISTRY)

_PLAIN_SCALARS = (str, int, float, bool, Decimal, type(None))


def register_data_type(name, data_type):
    """
    Register a name that may be used to refer to a :class:`.DataType` in
    reshape structure descriptions.

    Structure descriptions never contain type objects themselves, only
    registered names. Custom data types must be registered before they can be
    used with :meth:`.Table.normalize_with_spec` and rebuilt by
    :meth:`.Table.denormalize_with_spec`.

    :param name:
        A unique, non-empty string name for the data type.
    :param data_type:
        A :class:`.DataType` subclass, a :class:`.DataType` instance or a
        zero-argument callable returning a :class:`.DataType` instance.
    """
    if not isinstance(name, str) or not name:
        raise ValueError('Data type names must be non-empty strings.')

    is_class = isinstance(data_type, type) and issubclass(data_type, DataType)

    if not is_class and not isinstance(data_type, DataType) and not callable(data_type):
        raise ValueError('data_type must be a DataType subclass, instance or factory.')

    _REGISTERED_DATA_TYPES[name] = data_type


def _effective_registry(type_registry):
    registry = dict(_REGISTERED_DATA_TYPES)

    if type_registry:
        registry.update(type_registry)

    return registry


def _type_name(data_type, registry):
    for name, entry in registry.items():
        if isinstance(entry, DataType):
            if entry is data_type:
                return name
        elif isinstance(entry, type) and issubclass(entry, DataType):
            if type(data_type) is entry:
                return name

    raise ValueError(
        'Column type %r is not registered. Register it with '
        'agate.table.reshape.register_data_type or pass a type_registry.'
        % (type(data_type).__name__,)
    )


def _build_type(name, registry):
    if name not in registry:
        raise ValueError(
            'Can not rebuild column type %r: it is not registered. '
            'Register it with agate.table.reshape.register_data_type or pass a type_registry.' % (name,)
        )

    entry = registry[name]

    if isinstance(entry, DataType):
        return entry

    built = entry()

    if not isinstance(built, DataType):
        raise ValueError('Registered factory %r did not return a DataType.' % (name,))

    return built


def _validate_plain_data(value, path='spec'):
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                raise ValueError('Structure descriptions may only contain string keys, found %r at %s.' % (key, path))
            _validate_plain_data(item, '%s.%s' % (path, key))
    elif isinstance(value, (list, tuple)):
        for i, item in enumerate(value):
            _validate_plain_data(item, '%s[%i]' % (path, i))
    elif not isinstance(value, _PLAIN_SCALARS):
        raise ValueError(
            'Structure descriptions may only contain plain data (strings, numbers, booleans, '
            'None, lists and dicts), found %r at %s.' % (type(value).__name__, path)
        )


def normalize_with_spec(self, key=None, properties=None, property_column='property', value_column='value',
                        property_labels=None, row_column='row_position', column_column='column_position',
                        type_registry=None):
    """
    Convert this table to a long format together with an explicit structure
    description that makes the conversion reversible.

    Each (row, property column) pair of the original table becomes one record
    in the long table. Columns are identified by their stable positions in the
    original table, recorded in the `row_column` and `column_column` columns,
    so external labels that collide when stringified can not corrupt the
    mapping.

    The returned structure description contains only plain data (no type
    instances or other executable objects): the original column order, the
    registered names of the column types, the row names and the positions of
    every originally-null cell. Pass it to
    :meth:`.Table.denormalize_with_spec` to restore the original table.

    The input table is not modified and the returned table does not share row
    containers with it.

    :param key:
        A column name or a sequence of column names to keep as they are.
        Defaults to none.
    :param properties:
        A column name or a sequence of column names to convert to property
        records. Defaults to every column not named in `key`. If specified,
        `key` and `properties` must together cover every column, otherwise
        the conversion would not be reversible.
    :param property_column:
        The name of the long table column holding the property labels.
    :param value_column:
        The name of the long table column holding the cell values.
    :param property_labels:
        An optional sequence of external labels for the property columns, in
        the original column order. Labels may be duplicated or of mixed
        types; column identity is always derived from `column_column`.
        Defaults to the property column names.
    :param row_column:
        The name of the long table column holding the original row position.
    :param column_column:
        The name of the long table column holding the original column
        position.
    :param type_registry:
        An optional dict mapping names to :class:`.DataType` subclasses,
        instances or factories, extending the registered data types.
    :returns:
        A tuple of the long-format :class:`.Table` and the structure
        description as a plain-data :class:`dict`.
    """
    from agate.table import Table

    if key is None:
        key = []
    elif not utils.issequence(key):
        key = [key]

    key = list(key)

    for name in key:
        if name not in self._column_names:
            raise ValueError('Key column %r is not in this table.' % (name,))

    if properties is None:
        properties = [name for name in self._column_names if name not in key]
    elif not utils.issequence(properties):
        properties = [properties]

    properties = list(properties)

    for name in properties:
        if name not in self._column_names:
            raise ValueError('Property column %r is not in this table.' % (name,))

    if set(key) & set(properties):
        raise ValueError('Columns can not be both keys and properties.')

    if set(key) | set(properties) != set(self._column_names):
        raise ValueError(
            'key and properties must together cover every column, otherwise the conversion is not reversible.'
        )

    # Property columns are always processed in their original column order.
    property_positions = sorted(self._column_names.index(name) for name in properties)
    properties = [self._column_names[position] for position in property_positions]

    if property_labels is None:
        property_labels = list(properties)
    else:
        property_labels = list(property_labels)

        if len(property_labels) != len(properties):
            raise ValueError('property_labels must have one label per property column.')

    generated_columns = [row_column, column_column, property_column, value_column]

    if set(generated_columns) & set(key):
        raise ValueError('Generated column names must not overlap with key column names.')

    if len(set(generated_columns)) != len(generated_columns):
        raise ValueError('Generated column names must be unique.')

    registry = _effective_registry(type_registry)

    column_specs = []

    for position, name in enumerate(self._column_names):
        column_specs.append({
            'name': name,
            'type': _type_name(self._column_types[position], registry),
            'role': 'key' if name in key else 'property'
        })

    null_cells = []

    for i, row in enumerate(self._rows):
        for position in range(len(self._column_names)):
            if row[position] is None:
                null_cells.append([i, position])

    new_column_names = tuple(key) + tuple(generated_columns)

    key_types = [self._column_types[self._column_names.index(name)] for name in key]

    property_types = [self._column_types[position] for position in property_positions]

    if property_types and all(type(t) is type(property_types[0]) for t in property_types):
        value_type = property_types[0]
    else:
        value_type = Text()

    new_column_types = key_types + [Number(), Number(), Text(), value_type]

    new_rows = []

    for i, row in enumerate(self._rows):
        key_values = tuple(row[name] for name in key)

        for position, label in zip(property_positions, property_labels):
            values = key_values + (Decimal(i), Decimal(position), label, row[position])
            new_rows.append(Row(values, new_column_names))

    spec = {
        'format': SPEC_FORMAT,
        'version': SPEC_VERSION,
        'row_count': len(self._rows),
        'row_names': list(self._row_names) if self._row_names is not None else None,
        'columns': column_specs,
        'property_labels': property_labels,
        'null_cells': null_cells,
        'long_columns': {
            'key': list(key),
            'row': row_column,
            'column': column_column,
            'property': property_column,
            'value': value_column
        }
    }

    _validate_plain_data(spec)

    long_table = Table(new_rows, new_column_names, new_column_types, _is_fork=True)

    return long_table, spec


def denormalize_with_spec(self, spec, fill_missing=utils.default, on_conflict='error', type_registry=None):
    """
    Restore a wide table from a long table and a structure description
    produced by :meth:`.Table.normalize_with_spec`.

    Values are placed by their (original row, original column) positions, so
    the original column order, column types, row names and null cells are
    restored exactly, without any type guessing.

    Duplicate values for the same position are a conflict and raise
    :class:`.ReshapeConflictError` by default. Positions with no
    corresponding record in the long table are reported separately from
    explicit null values: they raise :class:`.ReshapeMissingError` unless
    `fill_missing` is given.

    The structure description must contain only plain data. Column types are
    rebuilt from registered names; a type that can not be rebuilt causes the
    conversion to be refused.

    :param spec:
        A structure description created by
        :meth:`.Table.normalize_with_spec`.
    :param fill_missing:
        If specified, positions with no record in the long table are filled
        with this value. If not specified, missing positions raise
        :class:`.ReshapeMissingError`.
    :param on_conflict:
        How to handle duplicate values for the same position: ``'error'``
        (the default) raises :class:`.ReshapeConflictError`, ``'first'``
        keeps the first value and ``'last'`` keeps the last value.
    :param type_registry:
        An optional dict mapping names to :class:`.DataType` subclasses,
        instances or factories, extending the registered data types.
    :returns:
        A new :class:`.Table` with the original structure.
    """
    from agate.table import Table

    if on_conflict not in ('error', 'first', 'last'):
        raise ValueError('on_conflict must be "error", "first" or "last".')

    _validate_plain_data(spec)

    if not isinstance(spec, dict) or spec.get('format') != SPEC_FORMAT:
        raise ValueError('Not an agate reshape structure description.')

    if spec.get('version') != SPEC_VERSION:
        raise ValueError('Unsupported reshape structure description version: %r.' % (spec.get('version'),))

    registry = _effective_registry(type_registry)

    column_specs = spec['columns']
    column_names = tuple(entry['name'] for entry in column_specs)
    column_types = [_build_type(entry['type'], registry) for entry in column_specs]
    column_count = len(column_specs)

    long_columns = spec['long_columns']
    key_columns = list(long_columns['key'])
    row_column = long_columns['row']
    column_column = long_columns['column']
    value_column = long_columns['value']

    row_count = spec['row_count']

    key_positions = [column_names.index(name) for name in key_columns]

    grid = {}
    conflicts = []

    for row in self._rows:
        row_position = int(row[row_column])
        column_position = int(row[column_column])

        if not 0 <= row_position < row_count:
            raise ValueError('Row position %r is outside the range described by the spec.' % (row_position,))

        if column_position >= column_count or column_specs[column_position]['role'] != 'property':
            raise ValueError('Column position %r is not a property column in the spec.' % (column_position,))

        # Key cells repeat once per property record of the same row, so only
        # disagreeing values are conflicts. Property cells must be unique.
        cells = [(column_position, row[value_column], False)]
        cells.extend(
            (key_position, row[name], True)
            for key_position, name in zip(key_positions, key_columns)
        )

        for position, value, is_key in cells:
            location = (row_position, position)

            if location in grid:
                if is_key and grid[location] == value:
                    continue

                if on_conflict == 'error':
                    conflicts.append((row_position, column_names[position]))
                elif on_conflict == 'last':
                    grid[location] = value
            else:
                grid[location] = value

    if conflicts:
        raise ReshapeConflictError(conflicts)

    missing_positions = []
    null_positions = []

    for row_position in range(row_count):
        for position in range(column_count):
            location = (row_position, position)

            if location not in grid:
                missing_positions.append((row_position, column_names[position]))
            elif grid[location] is None:
                null_positions.append((row_position, column_names[position]))

    if missing_positions:
        if fill_missing is utils.default:
            raise ReshapeMissingError(missing_positions, null_positions)

        for row_position, name in missing_positions:
            grid[(row_position, column_names.index(name))] = fill_missing

    new_rows = []

    for row_position in range(row_count):
        values = tuple(grid[(row_position, position)] for position in range(column_count))
        new_rows.append(Row(values, column_names))

    return Table(new_rows, column_names, column_types, row_names=spec['row_names'], _is_fork=True)
