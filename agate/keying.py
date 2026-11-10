"""
Typed key strategies used to decide when rows share a key across
:meth:`.Table.distinct`, :meth:`.Table.group_by` and :meth:`.Table.join`.

The strategy maps native column values to *key tokens*. Key tokens are
internal objects: they are never stored in a column or exposed as the name of
a group. They exist only so that the special values (:code:`None`, NaN, mixed
numeric types) have a single, address-independent identity on every code path.
"""

import datetime
import math
from decimal import Decimal

from agate.data_types import Boolean, Date, DateTime, Number, Text, TimeDelta
from agate.exceptions import KeyStrategyError

#: Sentinel token shared by every NaN, regardless of the object that carries it.
NAN_TOKEN = ('nan',)

#: Sentinel token used for :code:`None` when nulls are configured to match.
NULL_TOKEN = ('null',)


class KeyStrategy:
    """
    Defines how key values are identified when grouping, deduplicating or
    joining tables.

    Pass an instance as the :code:`key_strategy` argument of
    :meth:`.Table.distinct`, :meth:`.Table.group_by` or :meth:`.Table.join`.
    When no strategy is supplied, agate keeps its historical behavior: keys are
    compared using the native equality and hashing of the Python values.

    The built-in typing rules are:

    - Booleans and numbers occupy separate key spaces, so :code:`True` never
      matches :code:`1`.
    - Finite :class:`decimal.Decimal` values (and plain :class:`int` values)
      match by numeric value.
    - :code:`None` matches :code:`None` only when :code:`null_matches_null` is
      :code:`True`; otherwise nulls never match anything, including other
      nulls.
    - Every NaN is collapsed into a single missing-value class. NaN never
      matches a finite value, another null or itself through object identity.
    - Strings are never coerced to numbers.
    - :class:`datetime.date` and :class:`datetime.datetime` are never coerced
      into one another.

    Values of an unsupported (for example mutable) Python type, or values whose
    column uses a custom :class:`.DataType`, must be handled by an explicit
    :code:`adapter`. The adapter receives the native value and must return a
    stable, hashable token. :func:`repr` output is deliberately not used as an
    identity.

    :param null_matches_null:
        If :code:`True` (the default), two :code:`None` values share a key. If
        :code:`False`, :code:`None` never matches, modeling SQL-style null
        semantics.
    :param adapter:
        Optional callable invoked for values the built-in types do not cover.
        It takes a single native value and returns a hashable, value-stable
        token.
    """

    def __init__(self, null_matches_null=True, adapter=None):
        self.null_matches_null = null_matches_null
        self.adapter = adapter

    def encode(self, value):
        """
        Map a single native key value to an internal, hashable key token.

        :raises KeyStrategyError:
            If the value type is not supported and no :code:`adapter` was
            provided, or if the adapter returns an unhashable token.
        """
        if value is None:
            if self.null_matches_null:
                return NULL_TOKEN

            # A fresh, unequal object each time: nulls must never match.
            return object()

        value_type = type(value)

        if value_type is bool:
            return ('boolean', value)

        if value_type is Decimal:
            if value.is_nan():
                return NAN_TOKEN

            return ('number', value)

        if value_type is int:
            return ('number', Decimal(value))

        if value_type is float:
            if math.isnan(value):
                return NAN_TOKEN

            return ('number', Decimal(repr(value)))

        if value_type is str:
            return ('text', value)

        if value_type is datetime.datetime:
            return ('datetime', value)

        if value_type is datetime.date:
            return ('date', value)

        if value_type is datetime.timedelta:
            return ('timedelta', value)

        if self.adapter is None:
            raise KeyStrategyError(
                'Key values of type %s have no built-in stable key. Provide a '
                'KeyStrategy with an adapter that returns a hashable token '
                'instead of relying on object identity or repr().'
                % value_type.__name__
            )

        token = self.adapter(value)

        try:
            hash(token)
        except TypeError:
            raise KeyStrategyError(
                'The key adapter returned an unhashable token of type %s. '
                'It must return a stable, hashable value.'
                % type(token).__name__
            )

        # Wrap in a single-element tuple so the token occupies the strategy's
        # own key space even if the adapter returns a bare string or number.
        return ('adapter', type(value).__name__, token)

    def encode_composite(self, values):
        """
        Encode a composite key (a sequence of column values) into a single
        hashable token.
        """
        return tuple(self.encode(part) for part in values)

    def check_join_compatibility(self, left_column, right_column):
        """
        Verify that a pair of join columns can share a key space.

        Columns of different built-in type families are rejected rather than
        silently coerced. Columns backed by custom :class:`.DataType`
        subclasses are accepted only when an adapter is available.

        :raises KeyStrategyError:
            With the names of both columns when their types are incompatible.
        """
        left_type = type(left_column.data_type)
        right_type = type(right_column.data_type)

        if left_type is right_type:
            if left_type not in _BUILTIN_KEY_TYPES and self.adapter is None:
                raise KeyStrategyError(
                    'Join columns "%s" and "%s" use the custom data type %s, '
                    'which has no built-in stable key. Provide a KeyStrategy '
                    'with an adapter.'
                    % (left_column.name, right_column.name, left_type.__name__)
                )

            return

        left_family = _TYPE_FAMILIES.get(left_type)
        right_family = _TYPE_FAMILIES.get(right_type)

        if left_family is not None and right_family is not None and left_family == right_family:
            return

        raise KeyStrategyError(
            'Join columns "%s" (%s) and "%s" (%s) have incompatible key '
            'types and can not be matched without coercion.'
            % (
                left_column.name,
                left_type.__name__,
                right_column.name,
                right_type.__name__
            )
        )


_BUILTIN_KEY_TYPES = frozenset((Boolean, Number, Text, Date, DateTime, TimeDelta))

#: Type families whose members may share a key space. Boolean occupies its own
#: family so booleans never match numeric values.
_TYPE_FAMILIES = {
    Number: 'number',
    Text: 'text',
    Date: 'date',
    DateTime: 'datetime',
    TimeDelta: 'timedelta',
    Boolean: 'boolean'
}
