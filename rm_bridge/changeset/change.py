# SPDX-FileCopyrightText: Copyright DB Netz AG and the rm-bridge contributors
# SPDX-License-Identifier: Apache-2.0

"""Functionality for calulcating a ChangeSet."""
from __future__ import annotations

import collections.abc as cabc
import datetime
import logging
import typing as t

import capellambse
from capellambse import decl, helpers
from capellambse.extensions import reqif

from . import actiontypes as act
from . import find

LOGGER = logging.getLogger(__name__)
REQ_TYPES_FOLDER_NAME = "Types"
CACHEKEY_MODULE_IDENTIFIER = "-1"
CACHEKEY_TYPES_FOLDER_IDENTIFIER = "-2"
CACHEKEY_REQTYPE_IDENTIFIER = "-3"

REQ_TYPE_NAME = "Requirement"
ATTR_BLACKLIST = frozenset({("Type", "Folder")})

# TODO Remove default value patching; Snapshort should be correct
_ATTR_VALUE_DEFAULT_MAP: cabc.Mapping[
    str, cabc.Callable[[], tuple[type, act.Primitive | None]]
] = {
    "String": lambda: (str, ""),
    "Enum": lambda: (list, []),
    "Date": lambda: (datetime.datetime, None),
    "Integer": lambda: (int, 0),
    "Float": lambda: (float, 0.0),
    "Boolean": lambda: (bool, False),
}


WorkItem = t.Union[reqif.Requirement, reqif.RequirementsFolder]
RMIdentifier = t.NewType("RMIdentifier", str)


class AttributeValueBuilder(t.NamedTuple):
    deftype: str
    key: str
    value: act.Primitive | None


class TrackerChange:
    """Unites the calculators for finding actions to sync requirements."""

    _location_changed: set[RMIdentifier]
    _req_deletions: cabc.MutableMapping[
        helpers.UUIDString, cabc.MutableMapping[str, t.Any]
    ]

    tracker: cabc.Mapping[str, t.Any]
    """Snapshot of tracker, i.e. a `reqif.RequirementsModule`."""
    model: capellambse.MelodyModel
    """Model instance."""
    config: cabc.Mapping[str, t.Any]
    """Config section for the tracker."""
    reqfinder: find.ReqFinder
    """Find ReqIF elements in the model."""

    req_module: reqif.RequirementsModule
    """The corresponding `reqif.RequirementsModule` for the tracker."""
    reqt_folder: reqif.RequirementsTypesFolder | None
    """The `reqif.RequirementsTypesFolder` storing fields data."""
    actions: list[cabc.Mapping[str, t.Any]]
    """List of action requests for the tracker sync."""
    definitions: cabc.Mapping[
        str, act.AttributeDefinition | act.EnumAttributeDefinition
    ]
    """A lookup for AttributeDefinitions from the tracker snapshot."""
    data_type_definitions: cabc.Mapping[str, list[str]]
    """A lookup for DataTypeDefinitions from the tracker snapshot."""

    def __init__(
        self,
        tracker: cabc.Mapping[str, t.Any],
        model: capellambse.MelodyModel,
        config: cabc.Mapping[str, t.Any],
    ) -> None:
        self.tracker = tracker
        self.definitions = self.tracker["attributes"]
        self.data_type_definitions = {
            name: data["values"]  # type: ignore[typeddict-item]
            for name, data in self.definitions.items()
            if data["type"] == "Enum"
        }

        self.model = model
        self.config = config
        self.reqfinder = find.ReqFinder(model)

        self._location_changed = set[RMIdentifier]()
        self._req_deletions = {}

        self.req_module = self.reqfinder.reqmodule(
            config["capella-uuid"], config["external-id"]
        )
        if self.req_module is None:
            LOGGER.error("Skipping module: %s", self.config["external-id"])
            raise KeyError

        self.reqt_folder = self.reqfinder.reqtypesfolder_by_identifier(
            CACHEKEY_TYPES_FOLDER_IDENTIFIER, below=self.req_module
        )
        self.actions = []

    def calculate_change(self) -> None:
        """Render actions for RequirementsModule synchronization.

        Handles synchronization of RequirementTypesFolder first and
        Requirements and Folders afterwards.
        """
        base = {"parent": decl.UUIDReference(self.req_module.uuid)}
        if self.reqt_folder is None:
            base = self.create_requirement_types_folder_action()
        else:
            self.actions.extend(self.yield_mod_attribute_definition_actions())
            self.actions.extend(self.yield_reqtype_mod_actions())

        visited = set[str]()
        for item in self.tracker["items"]:
            second_key = "folders" if item.get("children") else "requirements"
            req = self.reqfinder.work_item_by_identifier(item["id"])
            if req is None:
                req_actions = self.create_requirements_actions(item)
                item_action = next(req_actions)
                _add_action_savely(base, "extend", second_key, item_action)
            else:
                req_actions = self.yield_mod_requirements_actions(req, item)
                visited.add(req.identifier)
                if req.parent != self.req_module:
                    item_action = decl.UUIDReference(req.uuid)
                    _add_action_savely(base, "extend", second_key, item_action)
                    self._location_changed.add(RMIdentifier(req.identifier))
                    self._invalidate_deletion(req)

            self.actions.extend(req_actions)

        for action in self._req_deletions.values():
            if set(action) == {"parent"}:
                self.actions.remove(action)

        _deep_update(base, self.delete_req_actions(visited))
        _deep_update(base, self.delete_req_actions(visited, "folders"))
        if set(base) != {"parent"}:
            self.actions.append(base)

    def _invalidate_deletion(self, requirement: WorkItem) -> None:
        """Try to remove ``requirement`` from deletions.

        Remove empty dictionaries or even whole action if its only
        delete action was removed.
        """
        key = "requirements"
        if isinstance(requirement, reqif.RequirementsFolder):
            key = "folders"

        try:
            ref = decl.UUIDReference(requirement.uuid)
            deletions = self._req_deletions[requirement.uuid]["delete"]
            deletions[key].remove(ref)

            if not deletions[key]:
                del deletions[key]
            if not deletions:
                del self._req_deletions[requirement.uuid]["delete"]
        except KeyError:
            pass

    def delete_req_actions(
        self,
        visited: cabc.Iterable[str],
        attr_name: str = "requirements",
    ) -> dict[str, t.Any]:
        """Return an action for deleting elements under the ReqModule.

        Filter all elements from the RequirementsModule attribute with
        name ``attr_name`` against ``visited``. These are the elements
        that are still in the model but not in the snapshot, and have to
        be deleted.
        """
        parent_ref = decl.UUIDReference(self.req_module.uuid)
        dels = [
            decl.UUIDReference(req.uuid)
            for req in getattr(self.req_module, attr_name)
            if req.identifier not in visited
        ]
        if not dels:
            return {"parent": parent_ref}
        return {"parent": parent_ref, "delete": {attr_name: dels}}

    def create_requirement_types_folder_action(self) -> dict[str, t.Any]:
        """Return an action for creating the ``RequirementTypesFolder``.

        See Also
        --------
        capellambse.extensions.reqif.RequirementsTypesFolder :
            Folder for (Data-)Type- and Attribute-Definitions
        """
        reqt_folder = {
            "long_name": REQ_TYPES_FOLDER_NAME,
            "identifier": CACHEKEY_TYPES_FOLDER_IDENTIFIER,
            "data_type_definitions": [
                self.create_data_type_action(name, values)
                for name, values in self.data_type_definitions.items()
            ],
            "requirement_types": [self.create_requirement_type_action()],
        }
        return {
            "parent": decl.UUIDReference(self.req_module.uuid),
            "extend": {"requirement_types_folders": [reqt_folder]},
        }

    def create_data_type_action(
        self, name: str, values: cabc.Sequence[str]
    ) -> dict[str, t.Any]:
        r"""Return an action for creating an ``EnumDataTypeDefinition``.

        See Also
        --------
        capellambse.extensions.reqif.EnumerationDataTypeDefinition :
            Definition for the ``data_type`` attribute of
            :class:`~capellambse.extensions.reqif.AttributeDefinitionEnumeration`\ s
        """
        type = "EnumerationDataTypeDefinition"
        enum_values = list[dict[str, str]]()
        for value in values:
            enum_values.append(
                {"long_name": value, "promise_id": f"EnumValue {name} {value}"}
            )
        return {
            "long_name": name,
            "values": enum_values,
            "promise_id": f"{type} {name}",
            "_type": type,
        }

    def create_requirement_type_action(self) -> dict[str, t.Any]:
        """Return an action for creating the ``RequirementType``.

        See Also
        --------
        capellambse.extensions.reqif.RequirementType :
            The ``type`` attribute of
            :class:`~capellambse.extensions.reqif.Requirements` and
            :class:`~capellambse.extensions.reqif.RequirementsFolder`
            that enables AttributeDefinitions via the ``definition``
            attribute.
        """
        identifier = " ".join(
            (
                reqif.RequirementType.__name__,
                REQ_TYPE_NAME,
                CACHEKEY_REQTYPE_IDENTIFIER,
            )
        )
        return {
            "identifier": CACHEKEY_REQTYPE_IDENTIFIER,
            "long_name": REQ_TYPE_NAME,
            "promise_id": identifier,
            "attribute_definitions": [
                self.create_attribute_definition_action(name, data)
                for name, data in self.definitions.items()
            ],
        }

    def create_attribute_definition_action(
        self,
        name: str,
        item: act.AttributeDefinition | act.EnumAttributeDefinition,
    ) -> dict[str, t.Any]:
        r"""Return a action for creating ``AttributeDefinition``\ s.

        In case of an ``AttributeDefinitionEnumeration`` requires
        ``name`` of possibly promised ``EnumerationDataTypeDefinition``.

        See Also
        --------
        capellambse.extensions.reqif.EnumerationDataTypeDefinition
        capellambse.extensions.reqif.AttributeDefinition
        capellambse.extensions.reqif.AttributeDefinitionEnumeration
        """
        base: dict[str, t.Any] = {"long_name": name}
        cls = reqif.AttributeDefinition
        if item["type"] == "Enum":
            cls = reqif.AttributeDefinitionEnumeration
            etdef = self.reqfinder.enum_data_type_definition_by_long_name(
                name, below=self.reqt_folder
            )
            if etdef is None:
                data_type_ref = decl.Promise(
                    f"EnumerationDataTypeDefinition {name}"
                )
            else:
                data_type_ref = decl.UUIDReference(etdef.uuid)

            base["data_type"] = data_type_ref
            base["multi_valued"] = item.get("multi_values") is not None

        base["_type"] = cls.__name__
        base["promise_id"] = f"{cls.__name__} {name}"
        return base

    def create_requirements_actions(
        self, item: dict[str, t.Any] | act.WorkItem
    ) -> cabc.Iterator[dict[str, t.Any]]:
        """Yield actions for creating Requirements or Folders.

        Also yields creations or modifications for children.

        See Also
        --------
        capellambse.extensions.reqif.Requirement
        capellambse.extensions.reqif.RequirementsFolder
        """
        attributes = []
        folder_hint = False
        for name, value in item.get("attributes", {}).items():
            if _blacklisted(name, value):
                if name == "Type" and value == "Folder":
                    folder_hint = True
                continue
            if name in self.definitions:
                attributes.append(
                    self.create_attribute_value_action(name, value)
                )

        reqtype = self.reqfinder.reqtype_by_identifier(
            CACHEKEY_REQTYPE_IDENTIFIER
        )
        if reqtype is None:
            rt_suffix = f"{REQ_TYPE_NAME} {CACHEKEY_REQTYPE_IDENTIFIER}"
            req_type_ref = decl.Promise(f"RequirementType {rt_suffix}")
        else:
            req_type_ref = decl.UUIDReference(reqtype.uuid)

        base: dict[str, t.Any] = {
            "long_name": item["long_name"],
            "identifier": str(item["id"]),
            "text": item.get("text", ""),
            "type": req_type_ref,
        }
        if attributes:
            base["attributes"] = attributes

        child_mods: list[dict[str, t.Any]] = []
        if (children := item.get("children")) is not None or folder_hint:
            base["requirements"] = []
            base["folders"] = []
            for child in children or ():
                key = "folders" if child.get("children") else "requirements"
                creq = self.reqfinder.work_item_by_identifier(child["id"])
                if creq is None:
                    child_actions = self.create_requirements_actions(child)
                    action = next(child_actions)
                else:
                    child_actions = self.yield_mod_requirements_actions(
                        creq, child, "To be created"
                    )
                    action = decl.UUIDReference(creq.uuid)

                base[key].append(action)
                child_mods.extend(child_actions)

            if not base["folders"]:
                del base["folders"]
            if not base["requirements"]:
                del base["requirements"]
        yield base
        yield from child_mods

    def create_attribute_value_action(
        self, name: str, value: str | list[str]
    ) -> dict[str, t.Any]:
        """Return an action for creating an ``AttributeValue``.

        Requires ``name`` of possibly promised
        ``AttributeDefinition/AttributeDefinitionEnumeration`` and
        patches given ``value`` from default value map
        :ref:`ATTRIBUTE_VALUE_CLASS_MAP` on faultish types.

        See Also
        --------
        patch_faulty_attribute_value
        capellambse.extension.reqif.IntegerValueAttribute
        capellambse.extension.reqif.StringValueAttribute
        capellambse.extension.reqif.RealValueAttribute
        capellambse.extension.reqif.DateValueAttribute
        capellambse.extension.reqif.BooleanValueAttribute
        capellambse.extension.reqif.EnumerationValueAttribute
        """
        builder = self.patch_faulty_attribute_value(name, value)
        deftype = "AttributeDefinition"
        values: list[decl.UUIDReference | decl.Promise] = []
        if builder.deftype == "Enum":
            deftype += "Enumeration"
            assert isinstance(builder.value, list)
            for enum_name in builder.value:
                enumvalue = self.reqfinder.enum_value_by_long_name(
                    enum_name, below=self.req_module
                )
                if enumvalue is None:
                    ev_ref = decl.Promise(f"EnumValue {name} {enum_name}")
                    assert ev_ref is not None
                else:
                    ev_ref = decl.UUIDReference(enumvalue.uuid)

                values.append(ev_ref)

        definition = self.reqfinder.attribute_definition_by_long_name(
            deftype, name, below=self.reqt_folder
        )
        if definition is None:
            definition_ref = decl.Promise(f"{deftype} {name}")
        else:
            definition_ref = decl.UUIDReference(definition.uuid)

        return {
            "_type": builder.deftype.lower(),
            "definition": definition_ref,
            builder.key: values or builder.value,
        }

    def patch_faulty_attribute_value(
        self, name: str, value: str | list[str]
    ) -> AttributeValueBuilder:
        """Swap value with faulty type with definition's default value.

        TODO Remove default value patching; Snapshort should be correct
        """
        deftype = self.definitions[name]["type"]
        type, default_value = _ATTR_VALUE_DEFAULT_MAP[deftype]()
        pvalue: act.Primitive | None
        if deftype == "Enum":
            default = self.data_type_definitions[name]
            is_faulty = not value or not isinstance(value, type)
            pvalue = default[:1] if is_faulty else value
            key = "values"
        else:
            pvalue = value if isinstance(value, type) else default_value
            key = "value"
        return AttributeValueBuilder(deftype, key, pvalue)

    def yield_mod_attribute_definition_actions(
        self,
    ) -> cabc.Iterator[dict[str, t.Any]]:
        r"""Yields a ModAction when the RequirementTypesFolder changed.

        The data type definitions and requirement type are checked via
        :meth:`~TrackerChange.make_datatype_definition_mod_action` and
        :meth:`~TrackerChange.make_reqtype_mod_action` respectively.

        Yields
        ------
        action
            An action that describes the changes on
            ``EnumerationDataTypeDefinition``\ s and the
            ``RequirementType``.
        """
        assert self.reqt_folder
        dt_defs_deletions: list[decl.UUIDReference] = [
            decl.UUIDReference(dtdef.uuid)
            for dtdef in self.reqt_folder.data_type_definitions
            if dtdef.long_name not in self.data_type_definitions
        ]

        dt_defs_creations = list[dict[str, t.Any]]()
        dt_defs_modifications = list[dict[str, t.Any]]()
        for name, values in self.data_type_definitions.items():
            action = self.make_datatype_definition_mod_action(name, values)
            if action is None:
                continue

            if "parent" in action:
                dt_defs_modifications.append(action)
            else:
                dt_defs_creations.append(action)

        base = {"parent": decl.UUIDReference(self.reqt_folder.uuid)}
        if dt_defs_creations:
            base["extend"] = {"data_type_definitions": dt_defs_creations}
        if dt_defs_deletions:
            base["delete"] = {"data_type_definitions": dt_defs_deletions}

        if base.get("extend", {}) or base.get("delete", {}):
            yield base

        yield from dt_defs_modifications

    def make_datatype_definition_mod_action(
        self, name: str, values: cabc.Sequence[str]
    ) -> dict[str, t.Any] | None:
        """Return an Action for creating or modifying a DataTypeDefinition.

        If a :class:`reqif.DataTypeDefinition` can be found via
        ``long_name`` and it differs against the snapshot an action for
        modification is returned. If it doesn't differ the returned
        ``action`` is ``None``. If the definition can't be found an
        action for creating an
        :class:`~capellambse.extensions.reqif.EnumerationDataTypeDefinition``
        is returned.

        Returns
        -------
        action
            Either an create- or mod-action or ``None`` if nothing
            changed.
        """
        assert self.reqt_folder
        try:
            dtdef = self.reqt_folder.data_type_definitions.by_long_name(
                name, single=True
            )
            mods = dict[str, t.Any]()
            if dtdef.long_name != name:
                mods["long_name"] = name
            if set(dtdef.values.by_long_name) != set(values):
                mods["values"] = list(values)
            if not mods:
                return None
            return {"parent": decl.UUIDReference(dtdef.uuid), "modify": mods}
        except KeyError:
            return self.create_data_type_action(name, values)

    def yield_reqtype_mod_actions(self) -> cabc.Iterator[dict[str, t.Any]]:
        """Yield an action for modifying the ``RequirementType``.

        If a :class:`reqif.RequirementType` can be found via
        `long_name` it is compared against the snapshot. If any changes
        to its attribute definitions are identified an action for
        modification is yielded else None. If the type can't be found an
        action for creation is yielded.

        Yields
        ------
        action
            Either a create- or mod-action or ``None`` if nothing
            changed.
        """
        assert self.reqt_folder
        try:
            reqtype = self.reqt_folder.requirement_types.by_long_name(
                REQ_TYPE_NAME, single=True
            )
            assert isinstance(reqtype, reqif.RequirementType)
            attr_defs_deletions: list[decl.UUIDReference] = [
                decl.UUIDReference(adef.uuid)
                for adef in reqtype.attribute_definitions
                if adef.long_name not in self.definitions
            ]

            attr_defs_creations = list[dict[str, t.Any]]()
            attr_defs_modifications = list[dict[str, t.Any]]()
            for name, data in self.definitions.items():
                action = self.mod_attribute_definition_action(
                    reqtype, name, data
                )
                if action is None:
                    continue

                if "parent" in action:
                    attr_defs_modifications.append(action)
                else:
                    attr_defs_creations.append(action)

            base = {"parent": decl.UUIDReference(reqtype.uuid)}
            if attr_defs_creations:
                base["extend"] = {"attribute_definitions": attr_defs_creations}
            if attr_defs_deletions:
                base["delete"] = {"attribute_definitions": attr_defs_deletions}

            if base.get("extend", {}) or base.get("delete", {}):
                yield base

            yield from attr_defs_modifications
        except KeyError:
            yield self.create_requirement_type_action()

    def yield_mod_requirements_actions(
        self,
        req: reqif.RequirementsModule | WorkItem,
        item: dict[str, t.Any],
        parent: reqif.RequirementsModule | WorkItem | None = None,
    ) -> cabc.Iterator[dict[str, t.Any]]:
        """Yield an action for modifying given ``req``.

        If any modifications to simple attributes (e.g. ``long_name``),
        attributes or creations/deletions of children
        (in case of ``req`` being a Folder) were identified an action
        for modification of ``req`` is yielded. For modifications of
        children the method is called recursively and yields actions
        from it.
        """
        item_attributes = item.get("attributes", {})
        attributes_creations = list[dict[str, t.Any]]()
        attributes_modifications = dict[str, t.Any]()
        for name, value in item_attributes.items():
            if value is not None and _blacklisted(name, value):
                continue

            action = self.mod_attribute_value_action(req, name, value)
            if action is None:
                continue

            if isinstance(action, dict):
                attributes_creations.append(action)
            else:
                attributes_modifications[name] = action[1]
        attributes_deletions: list[dict[str, t.Any]] = [
            decl.UUIDReference(attr.uuid)
            for attr in req.attributes
            if attr.definition.long_name not in item_attributes
        ]

        base = {"parent": decl.UUIDReference(req.uuid)}
        mods = _compare_simple_attributes(
            req, item, filter=("id", "attributes", "children")
        )
        if mods:
            base["modify"] = mods
        if attributes_modifications:
            base["modify"].update({"attributes": attributes_modifications})
        if attributes_creations:
            base["extend"] = {"attributes": attributes_creations}
        if attributes_deletions:
            base["delete"] = {"attributes": attributes_deletions}

        parent = self.req_module if parent is None else parent
        if req.parent != parent:
            self._location_changed.add(RMIdentifier(req.identifier))
            self._invalidate_deletion(req)

        children = item.get("children", [])
        cr_creations: list[dict[str, t.Any] | decl.UUIDReference] = []
        cf_creations: list[dict[str, t.Any] | decl.UUIDReference] = []
        containers = [cr_creations, cf_creations]
        child_mods: list[dict[str, t.Any]] = []
        if isinstance(req, reqif.RequirementsFolder):
            child_req_ids = set[RMIdentifier]()
            child_folder_ids = set[RMIdentifier]()
            for child in children:
                if child.get("children", []):
                    key = "folders"
                    child_folder_ids.add(RMIdentifier(child["id"]))
                else:
                    key = "requirements"
                    child_req_ids.add(RMIdentifier(child["id"]))

                container = containers[key == "folders"]
                creq = self.reqfinder.work_item_by_identifier(child["id"])
                if creq is None:
                    child_actions = self.create_requirements_actions(child)
                    action = next(child_actions)
                    container.append(action)
                else:
                    child_actions = self.yield_mod_requirements_actions(
                        creq, child, req
                    )
                    if creq.parent != req:
                        container.append(decl.UUIDReference(creq.uuid))

                child_mods.extend(child_actions)

            creations = dict[str, t.Any]()
            if cr_creations:
                creations["requirements"] = cr_creations
            if cf_creations:
                creations["folders"] = cf_creations
            if creations:
                _deep_update(base, {"extend": creations})

            fold_dels = make_requirement_delete_actions(
                req, child_folder_ids | self._location_changed, "folders"
            )
            req_dels = make_requirement_delete_actions(
                req, child_req_ids | self._location_changed
            )
            children_deletions = dict[str, t.Any]()
            if fold_dels:
                children_deletions["folders"] = fold_dels
            if req_dels:
                children_deletions["requirements"] = req_dels
            if children_deletions:
                _deep_update(base, {"delete": children_deletions})
            for del_ref in req_dels + fold_dels:
                self._req_deletions[del_ref.uuid] = base

        if (
            base.get("extend", {})
            or base.get("modify", {})
            or base.get("delete", {})
        ):
            yield base

        yield from child_mods

    def mod_attribute_value_action(
        self,
        req: reqif.RequirementsModule | WorkItem,
        name: str,
        value: str | list[str],
    ) -> dict[str, t.Any] | tuple[str, act.Primitive | None] | None:
        """Return an action for modifying an ``AttributeValue``.

        If a ``AttributeValue`` can be found via
        ``definition.long_name`` it is compared against the snapshot. If
        any changes to its ``value/s`` are identified a tuple of the
        name and value is returned else None. If the attribute can't be
        found an action for creation is returned.

        Returns
        -------
        action
            Either a create-action, the value to modify or ``None`` if
            nothing changed.
        """
        try:
            attr = req.attributes.by_definition.long_name(name, single=True)
            builder = self.patch_faulty_attribute_value(name, value)
            if isinstance(attr, reqif.EnumerationValueAttribute):
                assert isinstance(builder.value, list)
                differ = set(attr.values.by_long_name) != set(builder.value)
            else:
                differ = bool(attr.value != builder.value)

            if differ:
                return (name, builder.value)
            return None
        except KeyError:
            return self.create_attribute_value_action(name, value)

    def mod_attribute_definition_action(
        self,
        reqtype: reqif.RequirementType,
        name: str,
        data: act.AttributeDefinition | act.EnumAttributeDefinition,
    ) -> dict[str, t.Any] | None:
        """Return an action for an ``AttributeDefinition``.

        If a :class:`capellambse.extensions.reqif.AttributeDefinition`
        or :class:`capellambse.extensions.reqif.AttributeDefinitionEnumeration`
        can be found via ``long_name`` it is compared against the
        snapshot. If any changes are identified an action for
        modification is returned else None. If the definition can't be
        found an action for creation is returned.

        Returns
        -------
        action
            Either a create-, mod-action or ``None`` if nothing changed.
        """
        try:
            attrdef = reqtype.attribute_definitions.by_long_name(
                name, single=True
            )
            mods = dict[str, t.Any]()
            if attrdef.long_name != name:
                mods["long_name"] = name
            if data["type"] == "Enum":
                dtype = attrdef.data_type
                if dtype is None or dtype.long_name != name:
                    mods["data_type"] = name
                if (
                    attrdef.multi_valued
                    != data.get("multi_values")
                    is not None
                ):
                    mods["multi_valued"] = data[
                        "multi_values"  # type:ignore[typeddict-item]
                    ]
            if not mods:
                return None
            return {"parent": decl.UUIDReference(attrdef.uuid), "modify": mods}
        except KeyError:
            return self.create_attribute_definition_action(name, data)


def make_requirement_delete_actions(
    req: reqif.RequirementsFolder,
    child_ids: cabc.Container[RMIdentifier],
    key: str = "requirements",
) -> list[decl.UUIDReference]:
    """Return actions for deleting elements behind ``req.key``.

    The returned list is filtered against the ``identifier`` from given
    ``child_ids``.
    """
    return [
        decl.UUIDReference(creq.uuid)
        for creq in getattr(req, key)
        if creq.identifier not in child_ids
    ]


def _blacklisted(
    name: str,
    value: str | datetime.datetime | cabc.Iterable[str] | None,
) -> bool:
    """Identify if a key value pair is supported."""
    if value is None:
        return False
    if isinstance(value, (str, datetime.datetime)):
        return (name, value) in ATTR_BLACKLIST
    return all((_blacklisted(name, val) for val in value))


def _compare_simple_attributes(
    req: reqif.RequirementsModule | WorkItem,
    item: dict[str, t.Any],
    filter: cabc.Iterable[str],
) -> dict[str, t.Any]:
    """Return a diff dictionary about changed attributes for given `req`.

    Parameters
    ----------
    req
        A Requirement, Module or Folder that is compared against an
    item
        A dictionary describing the snapshotted state of `req`.
    filter
        An iterable of attribute names on `req` that shall be ignored
        during comparison.

    Returns
    -------
    diff
        A dictionary of attribute name and value pairs found to differ
        on `req` and `item`.
    """
    mods: dict[str, t.Any] = {}
    for name, value in item.items():
        if name in filter:
            continue
        if getattr(req, name, None) != value:
            mods[name] = value
    return mods


def _add_action_savely(
    base: dict[str, t.Any],
    first_key: str,
    second_key: str,
    action: dict[str, t.Any],
) -> None:
    try:
        base[first_key][second_key].append(action)
    except KeyError:
        _deep_update(base, {first_key: {second_key: [action]}})


def _deep_update(
    source: cabc.MutableMapping[str, t.Any],
    overrides: cabc.Mapping[str, t.Any],
) -> cabc.MutableMapping[str, t.Any]:
    """Update a nested dictionary in place."""
    for key, value in overrides.items():
        if isinstance(value, cabc.Mapping) and value:
            update = _deep_update(source.get(key, {}), value)
        else:
            update = overrides[key]

        source[key] = update
    return source
