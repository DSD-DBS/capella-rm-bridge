..
   SPDX-FileCopyrightText: Copyright DB Netz AG and the capella-rm-bridge contributors
   SPDX-License-Identifier: Apache-2.0

.. _change-set:

*********
ChangeSet
*********

The ChangeSet is the output of
:py:func:`~capella_rm_bridge.changeset.calculate_change_set` and uses the
:ref:`declarative modelling <declarative-modelling>` syntax of capellambse. An
example for the initial migration of the snapshot example:

.. literalinclude:: ../../tests/data/changesets/create.yaml
   :language: yaml
   :lines: 4-

The following ChangeSet shows modifications (i.e. synchronizations) after the
initial migration:

.. literalinclude:: ../../tests/data/changesets/mod.yaml
   :language: yaml
   :lines: 4-

Then an example for deletions is given by:

.. literalinclude:: ../../tests/data/changesets/delete.yaml
   :language: yaml
   :lines: 4-

A module in the snapshot is resolved in the
:py:class:`~capella_rm_bridge.changeset.change.TrackerChange` and its method
:py:meth:`~capella_rm_bridge.changeset.change.TrackerChange.calculate_change`:

.. class:: capella_rm_bridge.changeset.change.TrackerChange
   :noindex:

   .. automethod:: __init__
      :noindex:
   .. automethod:: calculate_change
      :noindex:
