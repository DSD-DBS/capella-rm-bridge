..
   SPDX-FileCopyrightText: Copyright DB Netz AG and the rm-bridge contributors
   SPDX-License-Identifier: Apache-2.0

.. _snapshot:

********
Snapshot
********

The snapshot is the input needed for calculating the change set. An example:

.. literalinclude:: ../../tests/data/snapshots/snapshot.yaml
   :language: yaml
   :emphasize-lines: 5,6,14,41

The snapshot consists of 3 separate sections:

- ``data_types``: For :external:class:`~capellambse.extensions.reqif.elements.EnumDataTypeDefinition`\ s, all needed options/values for :external:class:`~capellambse.extensions.reqif.elements.EnumerationValueAttribute` \s,
- ``requirement_types``: For :external:class:`~capellambse.extensions.reqif.elements.RequirementType`\ s. The keys underneath are the identifiers from the RM tool and finally
- ``items``: For the exported work items that will result into :external:class:`~capellambse.extensions.reqif.elements.Requirement`\ s and :external:class:`~capellambse.extensions.reqif.elements.RequirementsFolder`\ s.

Data Types
==========

This section describes ``EnumDataTypeDefinition``\ s: For now only as a mapping
from ``long_name`` to its values.

.. warning::

    The current format does not allow for equally named
    ``EnumerationDataTypeDefinition``\ s such that
    ``EnumerationAttributeValue``\ s on separate ``RequirementType``\ s have
    different options available. For now there is only one shared DataType
    exploiting the global availability in Capella. This makes it possible to
    choose values which shouldn't be available on the respective
    ValueAttribute.

Requirement Types
=================

Polarion supports work item types as special field. This section is therefore a
mapping that describes ``RequirementType``\ s from a given ``identifier`` to
its ``long_name`` and ``attribute_definitions`` (in short ``attributes``).
Therein the keys are matched against the ``data_types`` if it is an
``AttributeDefinitionEnumeration``.

Items
=====

This section consists of all work items and folders that are exported from the
RM tool. Important keys are the ``id`` (written to ``identifier``) and ``text``
(written to ``text``). The latter can also include referenced content like
images, then in b64-encoded form. The ``type`` field is an identifier for the
respective ``RequirementType`` and needs to also appear under
``requirement_types``.

The field data of work items is reflected by the ``attributes`` key. In general
fields are ``ValueAttributes`` in Capella. For now only the basic primitives
are supported:

- ``IntegerValueAttribute``
- ``StringValueAttribute``
- ``RealValueAttribute``
- ``DateValueAttribute``
- ``BooleanValueAttribute``
- ``EnumerationValueAttribute``

In order to have a nice display of these ``ValueAttribute``\ s in Capella and
also functioning ``.values`` for
:external:class:`~capellambse.extensions.reqif.elements.EnumerationValueAttribute`\
s, :external:class:`~capellambse.extensions.reqif.elements.AttributeDefinition`
and
:external:class:`~capellambse.extensions.reqif.elements.AttributeDefinitionEnumeration`\
s are needed. The previous snapshot will result into the following state:

.. image:: _static/img/capella_migration.png
