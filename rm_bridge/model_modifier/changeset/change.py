# SPDX-FileCopyrightText: Copyright DB Netz AG and the rm-bridge contributors
# SPDX-License-Identifier: Apache-2.0

"""Functionality for calulcating a ChangeSet."""
from __future__ import annotations

import collections.abc as cabc
import datetime
import logging
import typing as t

import capellambse
from capellambse.extensions import reqif

from . import actiontypes as act
from . import find
from .actiontypes import ActionType, DeleteAction

LOGGER = logging.getLogger(__name__)
REQ_TYPES_FOLDER_NAME = "Types"
CACHEKEY_MODULE_UUID = "-1"
CACHEKEY_TYPES_FOLDER_UUID = "-2"
CACHEKEY_REQTYPE_UUID = "-3"

REQ_TYPE_NAME = "Requirement"
ATTRIBUTE_VALUE_CLASS_MAP = {
    "String": reqif.StringValueAttribute,
    "Enum": reqif.EnumerationValueAttribute,
    "Date": reqif.DateValueAttribute,
    "Integer": reqif.IntegerValueAttribute,
    "Float": reqif.RealValueAttribute,
    "Boolean": reqif.BooleanValueAttribute,
}
ATTR_BLACKLIST = frozenset({("Type", "Folder")})


class TrackerChange:
    """Unites the calculators for finding actions to sync requirements."""

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
    actions: list[act.CreateAction | act.ModAction | act.DeleteAction]
    """List of action requests for the tracker sync."""
    definitions: cabc.Mapping[
        str, act.AttributeDefinition | act.EnumAttributeDefinition
    ]
    """A lookup for AttributeDefinitions from the tracker snapshot."""
    data_type_definitions: cabc.Mapping[str, cabc.Sequence[str]]
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

        try:
            self.req_module = self.reqfinder.find_module(
                config["capella-uuid"], config["external-id"]
            )
        except KeyError as error:
            LOGGER.error("Skipping tracker: %s", self.config["external-id"])
            raise KeyError from error

        self.reqt_folder = self.reqfinder.find_reqtypesfolder_by_identifier(
            CACHEKEY_TYPES_FOLDER_UUID, below=self.req_module
        )
        self.actions = []

    def calculate_change(self) -> None:
        """Render actions for RequirementsModule synchronization.

        Handles synchronization of RequirementTypesFolder first and
        Requirements and Folders second.
        """
        action: act.CreateAction | act.ModAction | None
        if self.reqt_folder:
            action = self.mod_attribute_definition_actions()
        else:
            action = self.create_attribute_definition_actions()

        if action is not None:
            self.actions.append(action)

        visited: set[str] = set()
        for item in self.tracker["items"]:
            if req := self.reqfinder.find_requirement_by_identifier(
                item["id"]
            ):
                visited.add(req.identifier)
                action = self.mod_requirements_actions(
                    req, item, self.req_module
                )
            else:
                action = self.create_requirements_actions(item)

            if action is not None:
                self.actions.append(action)

        for req in self.req_module.requirements + self.req_module.folders:
            assert req is not None
            if req.identifier not in visited:
                self.actions.append(
                    DeleteAction(
                        {"_type": ActionType.DELETE, "uuid": req.uuid}
                    )
                )

    def create_requirements_actions(
        self, item: dict[str, t.Any] | act.WorkItem
    ) -> act.RequirementFolderCreateAction | act.RequirementCreateAction:
        """Return an action for creating Requirements or Folders."""
        folder_hint = False
        attributes = []
        for name, value in item.get("attributes", {}).items():
            if blacklisted(name, value):
                if name == "Type" and value == "Folder":
                    folder_hint = True
                continue
            if name in self.definitions:
                attributes.append(
                    self.make_attribute_create_action(name, value)
                )

        base: dict[str, t.Any] = {
            "_type": act.ActionType.CREATE,
            "identifier": str(item["id"]),
            "long_name": item["long_name"],
            "cls": reqif.Requirement,
            "type": REQ_TYPE_NAME,
            "text": item.get("text", ""),
            "attributes": attributes,
        }
        if (children := item.get("children")) is not None or folder_hint:
            base["cls"] = reqif.RequirementsFolder
            base["requirements"] = []
            base["folders"] = []
            for child in children or ():
                key = "requirements"
                if child.get("children", []):
                    key = "folders"
                base[key].append(self.create_requirements_actions(child))
        return base  # type:ignore[return-value]

    def make_attribute_create_action(
        self, name: str, value: str | cabc.MutableSequence[str]
    ) -> act.AttributeValueCreateAction | act.EnumAttributeValueCreateAction:
        """Return an action for creating an AttributeValue."""
        type = self.definitions[name]["type"]
        base = {
            "_type": act.ActionType.CREATE,
            "cls": ATTRIBUTE_VALUE_CLASS_MAP[type],
            "definition": name,
        }
        if type == "Enum":
            base["values"] = [value] if not isinstance(value, list) else value
        else:
            base["value"] = value
        return base  # type:ignore[return-value]

    def create_attribute_definition_actions(
        self,
    ) -> act.RequirementTypesFolderCreateAction:
        """Add missing AttributeDefinitions and EnumerationDataTypeDefinitions."""
        return {
            "_type": act.ActionType.CREATE,
            "parent": self.req_module.uuid,
            "identifier": CACHEKEY_TYPES_FOLDER_UUID,
            "long_name": REQ_TYPES_FOLDER_NAME,
            "cls": reqif.RequirementsTypesFolder,
            "data_type_definitions": [
                make_data_type_definition(name, values)
                for name, values in self.data_type_definitions.items()
            ],
            "requirement_types": [make_requirement_type(self.definitions)],
        }

    def mod_attribute_definition_actions(
        self,
    ) -> act.AttributeDefinitionModAction | act.EnumAttributeDefinitionModAction | None:
        """Return a ModAction when the RequirementTypesFolder changed.

        The data type definitions and requirement type are checked via
        :meth:`make_datatype_definition_mod_action` and
        :meth:`make_reqtype_mod_action` respectively.

        Returns
        -------
        action
            Either a ModAction or None when nothing changed.
        """
        assert self.reqt_folder
        data_type_definitions: list[
            act.EnumerationDataTypeDefinitionCreateAction
            | act.EnumerationDataTypeDefinitionModAction
            | act.DeleteAction
        ] = [
            {
                "_type": act.ActionType.DELETE,
                "uuid": dtdef.uuid,
            }
            for dtdef in self.reqt_folder.data_type_definitions
            if dtdef.long_name not in self.data_type_definitions
        ]

        for name, values in self.data_type_definitions.items():
            action = self.make_datatype_definition_mod_action(name, values)
            if action is not None:
                data_type_definitions.append(action)

        base = {
            "_type": act.ActionType.MOD,
            "uuid": self.reqt_folder.uuid,
            "data_type_definitions": data_type_definitions,
            "requirement_types": [self.make_reqtype_mod_action()],
        }
        if not (
            base["data_type_definitions"] and any(base["requirement_types"])
        ):
            return None
        return base  # type:ignore[return-value]

    def make_datatype_definition_mod_action(
        self, name: str, values: cabc.Sequence[str]
    ) -> act.EnumerationDataTypeDefinitionCreateAction | act.EnumerationDataTypeDefinitionModAction | None:
        """Return an Action for the DataTypeDefinition.

        If a :class:`reqif.DataTypeDefinition` can be found via
        `long_name` it is compared against the snapshot. If it differs
        a ModAction is returned else None.
        If the definition can't be found a CreateAction is returned.

        Returns
        -------
        action
            Either a CreateAction, ModAction or None if nothing changed.
        """
        assert self.reqt_folder
        try:
            dtdef = self.reqt_folder.data_type_definitions.by_long_name(
                name, single=True
            )
            base = {"_type": act.ActionType.MOD, "uuid": dtdef.uuid}
            if dtdef.long_name != name:
                base["long_name"] = name
            if set(dtdef.values.by_long_name) != set(values):
                base["values"] = list(values)
            if nothing_changed(base):
                return None
            return base  # type:ignore[return-value]
        except KeyError:
            return make_data_type_definition(name, values)

    def make_reqtype_mod_action(
        self,
    ) -> act.RequirementTypeCreateAction | act.RequirementTypeModAction | None:
        """Return an Action for the RequirementType.

        If a :class:`reqif.RequirementType` can be found via
        `long_name` it is compared against the snapshot. If any changes
        to its attribute definitions are identified a ModAction is
        returned else None.
        If the type can't be found a CreateAction is returned.

        Returns
        -------
        action
            Either a CreateAction, ModAction or None if nothing changed.
        """
        assert self.reqt_folder
        try:
            reqtype = self.reqt_folder.requirement_types.by_long_name(
                REQ_TYPE_NAME, single=True
            )
            assert isinstance(reqtype, reqif.RequirementType)
            attribute_definitions: list[
                act.AttributeDefinitionNonDeleteAction | act.DeleteAction
            ] = [
                {
                    "_type": act.ActionType.DELETE,
                    "uuid": adef.uuid,
                }
                for adef in reqtype.attribute_definitions
                if adef.long_name not in self.definitions
            ]
            for name, data in self.definitions.items():
                action = make_attribute_definition_mod_action(
                    reqtype, name, data
                )
                if action is not None:
                    attribute_definitions.append(action)
            if not attribute_definitions:
                return None
            return {
                "_type": act.ActionType.MOD,
                "uuid": reqtype.uuid,
                "attribute_definitions": attribute_definitions,
            }
        except KeyError:
            return make_requirement_type(self.definitions)

    def mod_requirements_actions(
        self,
        req: reqif.RequirementsModule
        | reqif.RequirementsFolder
        | reqif.Requirement,
        item: dict[str, t.Any],
        parent: reqif.RequirementsModule
        | reqif.RequirementsFolder
        | reqif.Requirement,
    ) -> act.RequirementFolderModAction | act.RequirementModAction | None:
        """Return Actions for Requirements, Modules and Folders.

        Renders :class:`act.DeleteAction`s for attributes, child
        requirements and folders if given `req` is a
        :class:`reqif.RequirementsFolder` or a
        :class:`reqif.RequirementsModule`.

        Returns
        -------
        action
            None if no modification was identified else returns either
            an :class:`act.RequirementFolderModAction` or an
            :class:`act.RequirementModAction`.
        """
        mods = compare_simple_attributes(
            req, item, filter=("id", "attributes", "children")
        )
        item_attributes = item.get("attributes", {})
        attributes: list[
            act.AttributeDefinitionModAction
            | act.EnumAttributeDefinitionModAction
            | act.DeleteAction
        ] = [
            {
                "_type": act.ActionType.DELETE,
                "uuid": attr.uuid,
            }
            for attr in req.attributes
            if attr.definition.long_name not in item_attributes
        ]
        for name, value in item_attributes.items():
            if value is not None and blacklisted(name, value):
                continue
            if action := self.make_attribute_mod_action(req, name, value):
                attributes.append(action)  # type:ignore[arg-type]

        base = {
            "_type": act.ActionType.MOD,
            "uuid": req.uuid,
            **mods,
            "attributes": attributes,
        }
        if req.parent != parent:
            base["parent"] = parent.uuid
        if children := item.get("children", []):
            base["requirements"] = []
            base["folders"] = []
            if not isinstance(req, reqif.RequirementsFolder):
                base["_type"] = reqif.RequirementsFolder
            else:
                child_req_ids: set[str] = set()
                child_folder_ids: set[str] = set()
                for child in children:
                    if child.get("children", []):
                        child_folder_ids.add(str(child["id"]))
                    else:
                        child_req_ids.add(str(child["id"]))

                req_dels = add_requirement_delete_actions(req, child_req_ids)
                fold_dels = add_requirement_delete_actions(
                    req, child_folder_ids, "folders"
                )
            base["requirements"].extend(req_dels)
            base["folders"].extend(fold_dels)
        for child in children:
            k = "folders" if child.get("children", []) else "requirements"
            creq = self.reqfinder.find_requirement_by_identifier(  # type:ignore[assignment]
                child["id"]
            )
            if creq is None:
                action = self.create_requirements_actions(
                    child
                )  # type:ignore[assignment]
            else:
                action = self.mod_requirements_actions(
                    creq, child, req
                )  # type:ignore[assignment]
            if action is not None:
                base[k].append(action)
        if not (
            any(mods)
            or any(base["attributes"])
            or any(base.get("requirements", []))
            or any(base.get("folders", []))
        ):
            return None
        return base  # type:ignore[return-value]

    def make_attribute_mod_action(
        self,
        req: reqif.RequirementsModule
        | reqif.RequirementsFolder
        | reqif.Requirement,
        name: str,
        value: str | list[str],
    ) -> act.AttributeValueNonDeleteActions | None:
        """Return an Action for a ValueAttribute.

        If a `ValueAttribute` can be found via `definition.long_name` it
        is compared against the snapshot. If any changes to its value/s
        are identified a ModAction is returned else None.
        If the attribute can't be found a CreateAction is returned.

        Returns
        -------
        action
            Either a CreateAction, ModAction or None if nothing changed.
        """
        try:
            attr = req.attributes.by_definition.long_name(name, single=True)
            base = {"_type": act.ActionType.MOD, "uuid": attr.uuid}
            if isinstance(attr, reqif.EnumerationValueAttribute):
                value = value if isinstance(value, list) else [value]
                if set(attr.values.by_long_name) != set(value):
                    base["values"] = value
            elif attr.value != value:
                base["value"] = value
            if nothing_changed(base):
                return None
            return base  # type:ignore[return-value]
        except KeyError:
            return self.make_attribute_create_action(name, value)


def make_data_type_definition(
    name: str, values: cabc.Sequence[str]
) -> act.EnumerationDataTypeDefinitionCreateAction:
    """Return a `CreateAction` for an EnumerationDataTypeDefinition."""
    return {
        "_type": act.ActionType.CREATE,
        "long_name": name,
        "cls": reqif.EnumerationDataTypeDefinition,
        "values": list(values),
    }


def make_requirement_type(
    definitions: cabc.Mapping[
        str, act.AttributeDefinition | act.EnumAttributeDefinition
    ]
) -> act.RequirementTypeCreateAction:
    """Return a `CreateAction` for the `reqif.RequirementType`."""
    return {
        "_type": act.ActionType.CREATE,
        "identifier": CACHEKEY_REQTYPE_UUID,
        "long_name": REQ_TYPE_NAME,
        "cls": reqif.RequirementType,
        "attribute_definitions": [
            make_attribute_definition(name, data)
            for name, data in definitions.items()
        ],
    }


def make_attribute_definition(
    name: str,
    data: act.AttributeDefinition | act.EnumAttributeDefinition,
) -> act.EnumAttributeDefinitionCreateAction | act.AttributeDefinitionCreateAction:
    """Return a `CreateAction` for given definition data."""
    base = {
        "_type": act.ActionType.CREATE,
        "long_name": name,
        "cls": reqif.AttributeDefinition,
    }
    if data["type"] == "Enum":
        base["data_type"] = name
        base["multi_valued"] = data.get("multi_values") is not None
        base["cls"] = reqif.AttributeDefinitionEnumeration
    return base  # type:ignore[return-value]


def make_attribute_definition_mod_action(
    reqtype: reqif.RequirementType,
    name: str,
    data: act.AttributeDefinition | act.EnumAttributeDefinition,
) -> act.AttributeDefinitionNonDeleteAction | None:
    """Return an Action for an AttributeDefinition.

    If a :class:`reqif.AttributeDefinition` or
    :class:`reqif.AttributeDefinitionEnumeration` can be found via
    `long_name` it is compared against the snapshot. If any changes to
    its `long_name`, `data_type` or `multi_valued` attributes are
    identified a ModAction is returned else None.
    If the definition can't be found a CreateAction is returned.

    Returns
    -------
    action
        Either a CreateAction, ModAction or None if nothing changed.
    """
    try:
        attrdef = reqtype.attribute_definitions.by_long_name(name, single=True)
        base = {"_type": act.ActionType.MOD, "uuid": attrdef.uuid}
        if attrdef.long_name != name:
            base["long_name"] = name
        if data["type"] == "Enum":
            dtype = attrdef.data_type
            if dtype is None or dtype.long_name != name:
                base["data_type"] = name
            if attrdef.multi_valued != data.get("multi_values") is not None:
                base["multi_valued"] = data[
                    "multi_values"  # type:ignore[typeddict-item]
                ]
        if nothing_changed(base):
            return None
        return base  # type: ignore[return-value]
    except KeyError:
        return make_attribute_definition(name, data)


def add_requirement_delete_actions(
    req: reqif.RequirementsFolder,
    child_ids: cabc.Iterable[str],
    key: str = "requirements",
) -> list[act.DeleteAction]:
    """Return all `DeleteAction`s for elements behind `req.key`."""
    return [
        {"_type": act.ActionType.DELETE, "uuid": creq.uuid}
        for creq in getattr(req, key)
        if creq.identifier not in child_ids
    ]


def blacklisted(
    name: str,
    value: str | datetime.datetime | cabc.Iterable[str] | None,
) -> bool:
    """Identify if a key value pair is supported."""
    if value is None:
        return False
    if isinstance(value, (str, datetime.datetime)):
        return (name, value) in ATTR_BLACKLIST
    return all((blacklisted(name, val) for val in value))


def nothing_changed(base: dict[str, t.Any]) -> bool:
    """Identify if a given dictionary is a valid ModAction."""
    return set(base.keys()) == {"_type", "uuid"}


def compare_simple_attributes(
    req: reqif.RequirementsModule
    | reqif.RequirementsFolder
    | reqif.Requirement,
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
