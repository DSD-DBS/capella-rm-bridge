# SPDX-FileCopyrightText: Copyright DB Netz AG and the rm-bridge contributors
# SPDX-License-Identifier: Apache-2.0

"""Functionality for calulcating a ChangeSet."""
from __future__ import annotations

import collections.abc as cabc
import datetime
import logging
import typing as t

import capellambse
from capellambse import ymol
from capellambse.extensions import reqif

from . import actiontypes as act
from . import find

LOGGER = logging.getLogger(__name__)
REQ_TYPES_FOLDER_NAME = "Types"
CACHEKEY_MODULE_IDENTIFIER = "-1"
CACHEKEY_TYPES_FOLDER_IDENTIFIER = "-2"
CACHEKEY_REQTYPE_IDENTIFIER = "-3"

REQ_TYPE_NAME = "Requirement"
ATTRIBUTE_VALUE_CLASS_MAP: cabc.Mapping[
    str, tuple[type, act.Primitive | None]
] = {
    "String": (str, ""),
    "Enum": (list, []),
    "Date": (datetime.datetime, None),
    "Integer": (int, 0),
    "Float": (float, 0.0),
    "Boolean": (bool, False),
}
ATTR_BLACKLIST = frozenset({("Type", "Folder")})


class AttributeValueBuilder(t.NamedTuple):
    deftype: str
    key: str
    value: act.Primitive | None


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
    actions: list[cabc.Mapping[str, t.Any]]
    """List of action requests for the tracker sync."""
    definitions: cabc.Mapping[
        str, act.AttributeDefinition | act.EnumAttributeDefinition
    ]
    """A lookup for AttributeDefinitions from the tracker snapshot."""
    data_type_definitions: cabc.Mapping[str, list[str]]
    """A lookup for DataTypeDefinitions from the tracker snapshot."""
    promises: cabc.MutableMapping[str, ymol.Promise]
    """A mapping for promised RM objects."""

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
        self.promises = {}

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
            CACHEKEY_TYPES_FOLDER_IDENTIFIER, below=self.req_module
        )
        self.actions = []

    def calculate_change(self) -> None:
        """Render actions for RequirementsModule synchronization.

        Handles synchronization of RequirementTypesFolder first and
        Requirements and Folders second.
        """
        base = {"parent": ymol.UUIDReference(self.req_module.uuid)}
        action: cabc.Mapping[str, t.Any] | None
        if self.reqt_folder is None:
            key = "create"
            action = self.create_requirement_types_folder_action()
        else:
            key = "modify"
            action = self.mod_attribute_definition_actions()

        if action is not None:
            base[key] = {"requirement_types_folders": [action]}

        visited: set[str] = set()
        for item in self.tracker["items"]:
            second_key = "folders" if item.get("children") else "requirements"
            req = self.reqfinder.find_requirement_by_identifier(item["id"])
            if req is None:
                key = "create"
                action = self.create_requirements_actions(item)
            else:
                visited.add(req.identifier)
                key = "modify"
                action = self.mod_requirements_actions(
                    req, item, self.req_module
                )

            if action is not None:
                try:
                    base[key][second_key].append(action)
                except KeyError:
                    base[key][second_key] = [action]

        for req in self.req_module.requirements:
            assert req is not None
            if req.identifier not in visited:
                base["delete"]["requirements"].append(
                    ymol.UUIDReference(req.uuid)
                )

        for folder in self.req_module.folders:
            assert folder is not None
            if folder.identifier not in visited:
                base["delete"]["folders"].append(ymol.UUIDReference(req.uuid))

        self.actions.append(base)

    def create_requirement_types_folder_action(self) -> dict[str, t.Any]:
        """Return a ``CreateAction`` for the ``RequirementsTypesFolder``."""
        identifier = "-".join(
            (
                reqif.RequirementsTypesFolder.__name__,
                REQ_TYPES_FOLDER_NAME,
                CACHEKEY_TYPES_FOLDER_IDENTIFIER,
            )
        )
        promise = ymol.Promise(identifier)
        self.promises[promise.identifier] = promise
        return {
            "long_name": REQ_TYPES_FOLDER_NAME,
            "identifier": CACHEKEY_TYPES_FOLDER_IDENTIFIER,
            "data_type_definitions": [
                self.create_data_type_action(name, values)
                for name, values in self.data_type_definitions.items()
            ],
            "requirement_types": [self.create_requirement_type_action()],
        }

    def create_data_type_action(
        self, name: str, values: cabc.Sequence[str]
    ) -> dict[str, t.Any]:
        """Return a ``CreateAction`` for a ``EnumerationDataTypeDefinition``."""
        promise = ymol.Promise(f"EnumerationDataTypeDefinition-{name}")
        self.promises[promise.identifier] = promise
        return {
            "long_name": name,
            "values": list(values),
            "promise_id": promise.identifier,
            "_type": "enum",
        }

    def create_requirement_type_action(self) -> dict[str, t.Any]:
        """Return a ``CreateAction`` for the ``RequirementType``."""
        identifier = "-".join(
            (
                reqif.RequirementType.__name__,
                REQ_TYPE_NAME,
                CACHEKEY_REQTYPE_IDENTIFIER,
            )
        )
        promise = ymol.Promise(identifier)
        self.promises[promise.identifier] = promise
        return {
            "identifier": CACHEKEY_REQTYPE_IDENTIFIER,
            "long_name": REQ_TYPE_NAME,
            "promise_id": promise.identifier,
            "attribute_definitions": [
                self.create_attribute_definition_action(name, data)
                for name, data in self.definitions.items()
            ],
        }

    def create_attribute_definition_action(
        self,
        name: str,
        data: act.AttributeDefinition | act.EnumAttributeDefinition,
    ) -> dict[str, t.Any]:
        """Return a ``CreateAction`` for given definition data."""
        base: dict[str, t.Any] = {"long_name": name}
        cls = reqif.AttributeDefinition
        if data["type"] == "Enum":
            cls = reqif.AttributeDefinitionEnumeration
            data_type_ref = self.promises.get(
                f"EnumerationDataTypeDefinition-{name}"
            )
            if data_type_ref is None:
                etdef = self.reqfinder.find_enum_data_type_definition(
                    name, below=self.reqt_folder
                )
                data_type_ref = ymol.UUIDReference(etdef.uuid)

            base["data_type"] = data_type_ref
            base["multi_valued"] = data.get("multi_values") is not None

        promise = ymol.Promise(f"{cls.__name__}-{name}")
        self.promises[promise.identifier] = promise
        base["_type"] = cls.__name__
        base["promise_id"] = promise.identifier
        return base

    def create_requirements_actions(
        self, item: dict[str, t.Any] | act.WorkItem
    ) -> dict[str, t.Any]:
        """Return a ``CreateAction`` for creating Requirements or Folders."""
        attributes = []
        folder_hint = False
        for name, value in item.get("attributes", {}).items():
            if blacklisted(name, value):
                if name == "Type" and value == "Folder":
                    folder_hint = True
                continue
            if name in self.definitions:
                attributes.append(
                    self.create_attribute_value_action(name, value)
                )

        req_type_suffix = f"{REQ_TYPE_NAME}-{CACHEKEY_REQTYPE_IDENTIFIER}"
        req_type_ref = promise = self.promises.get(
            f"RequirementType-{req_type_suffix}"
        )
        if promise is None:
            assert self.reqt_folder is not None
            req_type_ref = ymol.UUIDReference(self.reqt_folder.uuid)

        base: dict[str, t.Any] = {
            "long_name": item["long_name"],
            "identifier": str(item["id"]),
            "text": item.get("text", ""),
            "type": req_type_ref,
        }
        if attributes:
            base["attributes"] = attributes
        if (children := item.get("children")) is not None or folder_hint:
            base["requirements"] = []
            base["folders"] = []
            for child in children or ():
                key = "folders" if child.get("children") else "requirements"
                base[key].append(self.create_requirements_actions(child))
            if not base["folders"]:
                del base["folders"]
            if not base["requirements"]:
                del base["requirements"]
        return base

    def create_attribute_value_action(
        self, name: str, value: str | list[str]
    ) -> dict[str, t.Any]:
        """Return a ``CreateAction`` for an AttributeValue."""
        builder = self.patch_faulty_attribute_value(name, value)
        deftype = "AttributeDefinition"
        if builder.deftype == "Enum":
            deftype += "Enumeration"

        definition_ref = promise = self.promises.get(f"{deftype}-{name}")
        if promise is None:
            definition = self.reqfinder.find_attribute_definition(
                deftype, name, below=self.reqt_folder
            )
            definition_ref = ymol.UUIDReference(definition.uuid)
        return {
            "_type": builder.deftype.lower(),
            "definition": definition_ref,
            builder.key: builder.value,
        }

    def patch_faulty_attribute_value(
        self, name: str, value: str | list[str]
    ) -> AttributeValueBuilder:
        """Swap faulty value with definition's default value."""
        deftype = self.definitions[name]["type"]
        type, default_value = ATTRIBUTE_VALUE_CLASS_MAP[deftype]
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

    def mod_attribute_definition_actions(self) -> dict[str, t.Any] | None:
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
        data_type_definitions: list[dict[str, t.Any]] = [
            {
                "_type": "DELETE",
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
            "_type": "MOD",
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
    ) -> dict[str, t.Any] | None:
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
            base = {"_type": "MOD", "uuid": dtdef.uuid}
            if dtdef.long_name != name:
                base["long_name"] = name
            if set(dtdef.values.by_long_name) != set(values):
                base["values"] = list(values)
            if nothing_changed(base):
                return None
            return base  # type:ignore[return-value]
        except KeyError:
            return self.create_data_type_action(name, values)

    def make_reqtype_mod_action(self) -> dict[str, t.Any] | None:
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
            attribute_definitions: list[dict[str, t.Any]] = [
                {
                    "_type": "DELETE",
                    "uuid": adef.uuid,
                }
                for adef in reqtype.attribute_definitions
                if adef.long_name not in self.definitions
            ]
            for name, data in self.definitions.items():
                action = self.mod_attribute_definition_action(
                    reqtype, name, data
                )
                if action is not None:
                    attribute_definitions.append(action)
            if not attribute_definitions:
                return None
            return {
                "_type": "MOD",
                "uuid": reqtype.uuid,
                "attribute_definitions": attribute_definitions,
            }
        except KeyError:
            return self.create_requirement_type_action()

    def mod_requirements_actions(
        self,
        req: reqif.RequirementsModule
        | reqif.RequirementsFolder
        | reqif.Requirement,
        item: dict[str, t.Any],
        parent: reqif.RequirementsModule
        | reqif.RequirementsFolder
        | reqif.Requirement,
    ) -> dict[str, t.Any] | None:
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
        attributes: list[dict[str, t.Any]] = [
            {
                "_type": "DELETE",
                "uuid": attr.uuid,
            }
            for attr in req.attributes
            if attr.definition.long_name not in item_attributes
        ]
        for name, value in item_attributes.items():
            if value is not None and blacklisted(name, value):
                continue
            if action := self.mod_attribute_value_action(req, name, value):
                attributes.append(action)  # type:ignore[arg-type]

        base = {
            "_type": "MOD",
            "uuid": req.uuid,
            **mods,
            "attributes": attributes,
        }
        children = item.get("children", [])
        if isinstance(req, reqif.RequirementsFolder):
            base["requirements"] = {}
            base["folders"] = {}
            child_req_ids: set[str] = set()
            child_folder_ids: set[str] = set()
            for child in children:
                if child.get("children", []):
                    child_folder_ids.add(str(child["id"]))
                else:
                    child_req_ids.add(str(child["id"]))

            req_dels = add_requirement_delete_actions(req, child_req_ids)
            base["requirements"].update(req_dels)

            fold_dels = add_requirement_delete_actions(
                req, child_folder_ids, "folders"
            )
            base["folders"].update(fold_dels)

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
                base[k][action.get("uuid", child["id"])] = action
        if not (
            any(mods)
            or any(base["attributes"])
            or any(base.get("requirements", []))
            or any(base.get("folders", []))
        ):
            return None
        return base  # type:ignore[return-value]

    def mod_attribute_value_action(
        self,
        req: reqif.RequirementsModule
        | reqif.RequirementsFolder
        | reqif.Requirement,
        name: str,
        value: str | list[str],
    ) -> dict[str, t.Any] | None:
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
            builder = self.patch_faulty_attribute_value(name, value)
            if isinstance(attr, reqif.EnumerationValueAttribute):
                assert isinstance(builder.value, list)
                differ = set(attr.values.by_long_name) != set(builder.value)
            else:
                differ = attr.value != builder.value
            if differ:
                return {
                    "_type": "MOD",
                    "uuid": attr.uuid,
                    builder.key: builder.value,  # type:ignore[misc]
                }  # type:ignore[return-value]
        except KeyError:
            return self.create_attribute_value_action(name, value)
        return None

    def mod_attribute_definition_action(
        self,
        reqtype: reqif.RequirementType,
        name: str,
        data: act.AttributeDefinition | act.EnumAttributeDefinition,
    ) -> dict[str, t.Any] | None:
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
            attrdef = reqtype.attribute_definitions.by_long_name(
                name, single=True
            )
            base = {"_type": "MOD", "uuid": attrdef.uuid}
            if attrdef.long_name != name:
                base["long_name"] = name
            if data["type"] == "Enum":
                dtype = attrdef.data_type
                if dtype is None or dtype.long_name != name:
                    base["data_type"] = name
                if (
                    attrdef.multi_valued
                    != data.get("multi_values")
                    is not None
                ):
                    base["multi_valued"] = data[
                        "multi_values"  # type:ignore[typeddict-item]
                    ]
            if nothing_changed(base):
                return None
            return base  # type: ignore[return-value]
        except KeyError:
            return self.create_attribute_definition_action(name, data)


def add_requirement_delete_actions(
    req: reqif.RequirementsFolder,
    child_ids: cabc.Iterable[str],
    key: str = "requirements",
) -> dict[str, dict[str, t.Any]]:
    """Return all `DeleteAction`s for elements behind `req.key`."""
    return {
        creq.uuid: {"_type": "DELETE", "uuid": creq.uuid}
        for creq in getattr(req, key)
        if creq.identifier not in child_ids
    }


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
