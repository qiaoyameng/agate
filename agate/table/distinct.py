from agate import utils


def distinct(self, key=None, key_strategy=None):
    """
    Create a new table with only unique rows.

    :param key:
        Either the name of a single column to use to identify unique rows, a
        sequence of such column names, a :class:`function` that takes a
        row and returns a value to identify unique rows, or `None`, in
        which case the entire row will be checked for uniqueness.
    :param key_strategy:
        An optional :class:`.KeyStrategy` that supplies typed,
        address-independent key identity (including :code:`None` and NaN
        handling). When omitted, values are compared using their native
        Python equality, preserving the historical behavior.
    :returns:
        A new :class:`.Table`.
    """
    key_is_row_function = hasattr(key, '__call__')
    key_is_sequence = utils.issequence(key)

    uniques = set()
    rows = []

    if self._row_names is not None:
        row_names = []
    else:
        row_names = None

    for i, row in enumerate(self._rows):
        if key_is_row_function:
            k = key(row)
            token = key_strategy.encode(k) if key_strategy is not None else k
        elif key_is_sequence:
            k = tuple(row[j] for j in key)
            token = key_strategy.encode_composite(k) if key_strategy is not None else k
        elif key is None:
            k = tuple(row)
            token = key_strategy.encode_composite(k) if key_strategy is not None else k
        else:
            k = row[key]
            token = key_strategy.encode(k) if key_strategy is not None else k

        if token not in uniques:
            uniques.add(token)
            rows.append(row)

            if self._row_names is not None:
                row_names.append(self._row_names[i])

    return self._fork(rows, row_names=row_names)
