..
   SPDX-FileCopyrightText: Copyright DB Netz AG and the capella-rm-bridge contributors
   SPDX-License-Identifier: Apache-2.0

.. _snapshot:

********
Snapshot
********

The snapshot is the input needed for calculating the change set and is a list
of modules. Each module will be compared against a matching
:external:class:`~capellambse.extensions.reqif.CapellaModule`
from the given model. If no matching ``RequirementsModule`` was found this
module will be skipped. Differences of the module snapshot and the model
``RequirementsModule`` will result in change actions according to the
:ref:`declarative modelling<declarative-modelling>` syntax of capellambse.

Module description
==================
As previously noted: A module (or tracker) in the given snapshot equals a
``RequirementsModule`` in Capella. Every module consists of 4 sections:

.. code-block:: yaml

   - id: MODULE-000 # mandatory
     long_name: Example # optional

     data_types: # Enumeration Data Type Definitions
       ...
     requirement_types: # WorkItemTypes
       ...
     items: # WorkItems
       ...

- descriptionary part of the module,
- **data_types**: For
  :external:class:`~capellambse.extensions.reqif.EnumerationDataTypeDefinition`\
  s, all needed options/values for
  :external:class:`~capellambse.extensions.reqif.EnumerationValueAttribute`\
  s,
- **requirement_types**: For
  :external:class:`~capellambse.extensions.reqif.RequirementType`\ s
  and finally
- **items**: For the exported work items that will result into
  :external:class:`~capellambse.extensions.reqif.Requirement`\ s and
  :external:class:`~capellambse.extensions.reqif.Folder`\ s.

The ``id`` is required and will be compared with the ``identifier`` of the
matched ``RequirementsModule``. Other attributes like ``long_name`` or ``text``
can be declared optionally for comparison.

Enumeration Data Types (``data_types``)
=======================================

This section describes ``EnumDataTypeDefinition``\ s: For now only as a mapping
from ``long_name`` to its values.

.. code-block:: yaml

   data_types: # Enumeration Data Type Definitions
     Type:
       - Unset
       - Folder
       - Functional
     Release:
       - Feature Rel. 1
       - Feature Rel. 2

.. warning::

    The current format does not allow for equally named
    ``EnumerationDataTypeDefinition``\ s such that
    ``EnumerationAttributeValue``\ s on separate ``RequirementType``\ s have
    different options available. For now there is only one shared DataType
    exploiting the availability in the ``CapellaModule``. This makes it
    possible to choose values which shouldn't be available on the respective
    ValueAttribute.

.. _requirement_types:

Requirement Types (``requirement_types``)
=========================================

.. code-block:: yaml

   requirement_types: # WorkItemTypes
    system_requirement:
      long_name: System Requirement
      attributes: # Field Definitions, we don't need the IDs
        Capella ID: # Field name
          type: String # -> AttributeDefinition
        Type:
          type: Enum
        Submitted at:
          type: Date # -> AttributeDefinition
        Release:
          type: Enum
          multi_values: true

    software_requirement:
      long_name: Software Requirement
      attributes:
        Capella ID:
          type: String
        Type:
          type: Enum
        Submitted at:
          type: Date

    stakeholder_requirement:
      long_name: Stakeholder Requirement
      attributes:
        Capella ID:
          type: String

Work item types are dealt by most RM tools as special fields. This section is
therefore a mapping that describes ``RequirementType``\ s from a given
``identifier`` to its ``long_name`` and ``attribute_definitions`` (in short
``attributes``). Therein the keys are matched against the ``long_name`` of the
``EnumDataTypeDefinition`` defined in ``data_types`` if it is an
``AttributeDefinitionEnumeration``. Else an ``AttributeDefinition`` is meant
and for these a type-hint via ``type`` is needed.

``Requirement``\ s and ``RequirementFolder``\ s (``items``)
===========================================================

.. code-block:: yaml

   items: # WorkItems
     - id: REQ-001
       long_name: Functional Requirements
       text: <p>Test Description</p>
       type: system_requirement # WorkItemType ID

       attributes:
         Type: [Unset] # Fields for a Folder

       children: # Folder b/c non-empty children
         - id: REQ-002
           long_name: Function Requirement
           # [...]
         - id: REQ-003
           # [...]

This section consists of all work items and folders that are exported from the
RM tool. Important keys are the ``id`` (written to ``identifier``) and
``text``. The latter can also include referenced content like images using the
`data-URI`_ schema. The ``type`` field is an identifier for the respective
``RequirementType`` and needs to also appear under :ref:`requirement_types`.

.. _data-URI: https://en.wikipedia.org/wiki/Data_URI_scheme

The field data of work items is reflected by the ``attributes`` key. In general
fields are ``ValueAttributes`` in Capella. For now only the basic primitives
are supported:

- ``IntegerValueAttribute`` (required as an integer value in the snapshot)
- ``StringValueAttribute`` (required as a string value in the snapshot)
- ``RealValueAttribute`` (required as a float value in the snapshot)
- ``DateValueAttribute`` (required as a !!timestamp value in the snapshot)
- ``BooleanValueAttribute`` (required as a boolean value in the snapshot)
- ``EnumerationValueAttribute`` (required as a sequence of strings value in the
  snapshot)

In order to have a nice display of these ``ValueAttribute``\ s in Capella and
also functioning ``.values`` for
:external:class:`~capellambse.extensions.reqif.EnumerationValueAttribute`\
s, :external:class:`~capellambse.extensions.reqif.AttributeDefinition`
and
:external:class:`~capellambse.extensions.reqif.AttributeDefinitionEnumeration`\
s are needed. This subsection is a ``long_name`` to value (values) mapping that
are matched against the attribute-definitions (``attributes``) subsection in
:ref:`requirement_types`.

.. note::

  During execution of
  :py:meth:`~capella_rm_bridge.change_set.change.TrackerChange.calculate_change` the
  integrity of the snapshot is checked. That means for example work items that
  have ``type`` identifiers which are not defined in the
  :ref:`requirement_types` section will be skipped. In general there needs to
  be a ``type`` identifier exported in order to have fields maintained.

  Another example: If there are any options/values exported on an enum-field
  which are not defined in the respective enum definition under ``data_types``,
  the field will be skipped.

With the ``children`` key the hierarchical structure of the workitems is
exported and empty children will result in a ``Requirement``. Conversely
non-empty children will cause change action on a ``RequirementsFolder``.

Complete snapshot
=================

The exemplary sections combined to one snapshot will result into the following
Capella model state:

.. image:: _static/img/capella_migration.png

.. note::

  The
  :external:class:`~capellambse.extensions.reqif.CapellaTypesFolder`
  will be initially created in the ``RequirementsModule`` for compactness.
  Every module has its own ``CapellaTypesFolder`` named **Types** with all
  necessary definitions.
