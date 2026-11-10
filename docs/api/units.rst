=====
Units
=====

A :class:`.Unit` describes how the :class:`decimal.Decimal` values stored in
a :class:`.Number` column relate to a reference unit. The relationship is
linear::

    reference_value = scale * value + offset

Both ``scale`` and ``offset`` are :class:`decimal.Decimal` values, so
conversions such as Celsius to kelvin keep full precision.

Units are attached per column through the optional ``column_units`` argument
of :class:`.Table` (or :meth:`.Table.from_csv`). Tables without unit
metadata behave exactly as before.

.. code-block:: python

    import agate

    table = agate.Table(
        [(1, 100)],
        ['meters', 'centimeters'],
        [agate.Number(), agate.Number()],
        column_units=[agate.METER, agate.CENTIMETER],
    )

Unit metadata travels with the column through :meth:`.Table.select`,
:meth:`.Table.rename`, :meth:`.Table.join`, :meth:`.Table.compute` and
:meth:`.Table.merge`. It is keyed to the column itself, not its name, so
renaming two columns onto each other's names never swaps their units.

Use :meth:`.Table.convert` to convert values explicitly:

.. code-block:: python

    converted = table.convert({'centimeters': agate.METER})

Built-in units
--------------

.. autosummary::
    :nosignatures:

    agate.METER
    agate.CENTIMETER
    agate.SECOND
    agate.MILLISECOND
    agate.KELVIN
    agate.CELSIUS
    agate.KELVIN_DELTA
    agate.CELSIUS_DELTA

Arithmetic rules
----------------

* :class:`.Change` converts both columns to the reference unit before
  subtracting. Units of different dimensions (for example a length and a
  temperature) raise :class:`.UnitError`.
* Subtracting absolute temperatures produces an offset-free temperature
  difference (:data:`.KELVIN_DELTA`), not another absolute temperature.
* :class:`.Mean` works on absolute temperatures and reports the result in the
  reference unit (kelvin).
* :class:`.Sum` refuses to add absolute temperatures, but accepts difference
  units such as :data:`.KELVIN_DELTA`.
* A custom :class:`.Computation` or :class:`.Aggregation` does not inherit
  the unit of its input. Override ``get_computed_unit`` /
  ``get_aggregate_unit``, or pass an explicit ``unit`` to :class:`.Formula`
  or :class:`.Summary`, to declare one. Otherwise the result is undetermined
  (``None``).

Custom units
------------

Any unit can be built directly:

.. code-block:: python

    from decimal import Decimal
    from agate.units import Unit

    inch = Unit('in', 'length', scale=Decimal('0.0254'))

Detailed list
-------------

.. autoclass:: agate.Unit
    :members:
.. autoclass:: agate.UnitError
    :members:
