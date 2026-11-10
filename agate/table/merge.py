from collections import OrderedDict

from agate.exceptions import DataTypeError, UnitError
from agate.rows import Row


@classmethod
def merge(cls, tables, row_names=None, column_names=None):
    """
    Create a new table from a sequence of similar tables.

    This method will not carry over row names from the merged tables, but new
    row names can be specified with the :code:`row_names` argument.

    It is possible to limit the columns included in the new :class:`.Table`
    with :code:`column_names` argument. For example, to only include columns
    from a specific table, set :code:`column_names` equal to
    :code:`table.column_names`.

    :param tables:
        An sequence of :class:`.Table` instances.
    :param row_names:
        See :class:`.Table` for the usage of this parameter.
    :param column_names:
        A sequence of column names to include in the new :class:`.Table`. If
        not specified, all distinct column names from `tables` are included.
    :returns:
        A new :class:`.Table`.
    """
    from agate.table import Table

    new_columns = OrderedDict()
    new_units = OrderedDict()

    for table in tables:
        for i in range(0, len(table.columns)):
            if column_names is None or table.column_names[i] in column_names:
                column_name = table.column_names[i]
                column_type = table.column_types[i]
                column_unit = table.column_units[i]

                if column_name in new_columns:
                    if not isinstance(column_type, type(new_columns[column_name])):
                        raise DataTypeError('Tables contain columns with the same names, but different types.')

                    existing_unit = new_units[column_name]

                    if existing_unit is not None and column_unit is not None and existing_unit != column_unit:
                        raise UnitError(
                            'Tables contain columns with the same name "%s", but different units: %s and %s. '
                            'Use Table.convert to unify the units before merging.'
                            % (column_name,
                               existing_unit.name if existing_unit is not None else 'none',
                               column_unit.name if column_unit is not None else 'none')
                        )
                else:
                    new_columns[column_name] = column_type
                    new_units[column_name] = column_unit

                if new_units[column_name] is None and column_unit is not None:
                    new_units[column_name] = column_unit

    column_keys = tuple(new_columns.keys())
    column_types = tuple(new_columns.values())
    column_units = tuple(new_units.values())

    rows = []

    for table in tables:
        # Performance optimization for identical table structures
        if table.column_names == column_keys and table.column_types == column_types:
            rows.extend(table.rows)
        else:
            for row in table.rows:
                data = []

                for column_key in column_keys:
                    data.append(row.get(column_key, None))

                rows.append(Row(data, column_keys))

    return Table(rows, column_keys, column_types, row_names=row_names, _is_fork=True,
                 column_units=column_units)
