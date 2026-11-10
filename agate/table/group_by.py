from collections import OrderedDict

from agate.data_types import Text
from agate.tableset import TableSet


def group_by(self, key, key_name=None, key_type=None, key_strategy=None):
    """
    Create a :class:`.TableSet` with a table for each unique key.

    Note that group names will always be coerced to a string, regardless of the
    format of the input column.

    :param key:
        Either the name of a column from this table to group by, a sequence
        of such column names for a composite key, or a :class:`function` that
        takes a row and returns a value to group by.
    :param key_name:
        A name that describes the grouped properties. Defaults to the
        column name that was grouped on or "group" if grouping with a key
        function. See :class:`.TableSet` for more.
    :param key_type:
        An instance of any subclass of :class:`.DataType`. If not provided
        it will default to a :class`.Text`.
    :param key_strategy:
        An optional :class:`.KeyStrategy` that supplies typed,
        address-independent key identity (including :code:`None` and NaN
        handling). When omitted, values are grouped using their native Python
        equality, preserving the historical behavior.
    :returns:
        A :class:`.TableSet` mapping where the keys are unique values from
        the :code:`key` and the values are new :class:`.Table` instances
        containing the grouped rows.
    """
    key_is_row_function = hasattr(key, '__call__')
    key_is_sequence = not key_is_row_function and (
        isinstance(key, (list, tuple)) and all(not hasattr(part, '__call__') for part in key)
    )

    if key_is_row_function:
        key_name = key_name or 'group'
        key_type = key_type or Text()
    elif key_is_sequence:
        columns = [self._columns[part] for part in key]
        key_name = key_name or ', '.join(column.name for column in columns)
        key_type = key_type or Text()
    else:
        column = self._columns[key]

        key_name = key_name or column.name
        key_type = key_type or column.data_type

    # Maps internal key tokens to the rows in the group.
    groups = OrderedDict()
    # Maps each token back to the first native key value so that the internal
    # encoding is never exposed as a TableSet key or column value.
    display_keys = OrderedDict()

    for row in self._rows:
        if key_is_row_function:
            native_key = key(row)
        elif key_is_sequence:
            native_key = tuple(row[column.name] for column in columns)
        else:
            native_key = row[column.name]

        if key_strategy is None:
            token = key_type.cast(native_key)
        elif key_is_sequence:
            token = key_strategy.encode_composite(native_key)
        else:
            token = key_strategy.encode(native_key)

        display_key = native_key if key_strategy is not None else token

        if token not in groups:
            groups[token] = []
            display_keys[token] = display_key

        groups[token].append(row)

    if not groups:
        return TableSet([self._fork([])], [], key_name=key_name, key_type=key_type)

    grouped_tables = []
    group_keys = []

    for token, grouped_rows in groups.items():
        grouped_tables.append(self._fork(grouped_rows))
        group_keys.append(display_keys[token])

    return TableSet(grouped_tables, group_keys, key_name=key_name, key_type=key_type)
