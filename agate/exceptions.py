"""
This module contains various exceptions raised by agate.
"""


class DataTypeError(TypeError):  # pragma: no cover
    """
    A calculation was attempted with an invalid :class:`.DataType`.
    """
    pass


class UnsupportedAggregationError(TypeError):  # pragma: no cover
    """
    An :class:`.Aggregation` was attempted which is not supported.

    For example, if a :class:`.Percentiles` is applied to a :class:`.TableSet`.
    """
    pass


class CastError(Exception):  # pragma: no cover
    """
    A column value can not be cast to the correct type.
    """
    pass


class ReshapeConflictError(Exception):
    """
    A :meth:`.Table.denormalize_with_spec` operation found more than one value
    for the same (original row, original column) position.

    The conflicting positions are available as a list of
    :code:`(row_position, column_name)` tuples via :attr:`conflicts`.
    """
    def __init__(self, conflicts):
        self.conflicts = list(conflicts)
        super().__init__(
            'Found conflicting values for these (row, column) positions: %r. '
            'Use the on_conflict argument to resolve them.' % (self.conflicts,)
        )


class ReshapeMissingError(Exception):
    """
    A :meth:`.Table.denormalize_with_spec` operation could not find values for
    every (original row, original column) position described by the structure
    description.

    Missing positions (no record in the long table) are reported separately
    from explicit null values via :attr:`missing_positions` and
    :attr:`null_positions`. Both are lists of :code:`(row_position,
    column_name)` tuples.
    """
    def __init__(self, missing_positions, null_positions):
        self.missing_positions = list(missing_positions)
        self.null_positions = list(null_positions)
        super().__init__(
            'Missing values for these (row, column) positions: %r. '
            'Explicit null values found at: %r. '
            'Pass fill_missing to denormalize_with_spec to fill the missing positions.'
            % (self.missing_positions, self.null_positions)
        )


class FieldSizeLimitError(Exception):  # pragma: no cover
    """
    A field in a CSV file exceeds the maximum length.

    This length may be the default or one set by the user.
    """
    def __init__(self, limit, line_number):
        super().__init__(
            'CSV contains a field longer than the maximum length of %i characters on line %i. Try raising the maximum '
            'with the field_size_limit parameter, or try setting quoting=csv.QUOTE_NONE.' % (limit, line_number)
        )
