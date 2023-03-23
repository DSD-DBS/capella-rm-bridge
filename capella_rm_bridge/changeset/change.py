# SPDX-FileCopyrightText: Copyright DB Netz AG and the capella-rm-bridge contributors
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
TYPES_FOLDER_IDENTIFIER = "-2"

REQ_TYPE_NAME = "Requirement"
_ATTR_BLACKLIST = frozenset({("Type", "Folder")})
_ATTR_VALUE_DEFAULT_MAP: cabc.Mapping[str, type] = {
    "Boolean": bool,
    "Date": datetime.datetime,
    "Datetime": datetime.datetime,
    "Enum": list,
    "Float": float,
    "Integer": int,
    "String": str,
}


WorkItem = t.Union[reqif.Requirement, reqif.Folder]
RMIdentifier = t.NewType("RMIdentifier", str)
AttributeDefinitionClass = t.Union[
    type[reqif.AttributeDefinition], type[reqif.AttributeDefinitionEnumeration]
]


class _AttributeValueBuilder(t.NamedTuple):
    deftype: str
    key: str
    value: act.Primitive | RMIdentifier | None


class MissingCapellaModule(Exception):
    """A ``CapellaModule`` with matching UUID could not be found."""


class TrackerChange:
    """Unites the calculators for finding actions to sync requirements."""

    _location_changed: set[RMIdentifier]
    _req_deletions: dict[helpers.UUIDString, dict[str, t.Any]]
    _evdeletions: set[RMIdentifier]
    _reqtype_ids: set[RMIdentifier]
    _faulty_attribute_definitions: set[str]
    errors: list[str]

    tracker: cabc.Mapping[str, t.Any]
    """Snapshot of tracker, i.e. a `reqif.CapellaModule`."""
    model: capellambse.MelodyModel
    """Model instance."""
    config: act.TrackerConfig
    """Config section for the tracker."""
    gather_logs: bool
    """Collect error messages in ``errors`` instead of immediate logging."""

    req_module: reqif.CapellaModule
    """The corresponding ``reqif.CapellaModule`` for the tracker."""
    reqt_folder: reqif.CapellaTypesFolder | None
    """The `reqif.CapellaTypesFolder` storing fields data."""
    reqtype_fields_filter: cabc.Mapping[RMIdentifier, set[str]]
    """A mapping for whitelisted fieldnames per RequirementType."""
    actions: list[dict[str, t.Any]]
    """List of action requests for the tracker sync."""
    data_type_definitions: cabc.Mapping[str, act.DataType]
    """A lookup for DataTypeDefinitions from the tracker snapshot."""
    requirement_types: cabc.Mapping[RMIdentifier, act.RequirementType]
    """A lookup for RequirementTypes from the tracker snapshot."""

    def __init__(
        self,
        tracker: cabc.Mapping[str, t.Any],
        model: capellambse.MelodyModel,
        config: act.TrackerConfig,
        gather_logs: bool = True,
    ) -> None:
        """Construct a ``TrackerChange``.

        Parameters
        ----------
        tracker
            Is a mapping that has ``id``, ``data_types``,
            ``requirement_types`` and ``items`` defined. Maybe called
            module in different RM tools.
        model
            An instance of ``MelodyModel`` for comparison with the
            snapshot.
        config
            A configuration for the module (tracker).

        Raises
        ------
        InvalidTrackerConfig
            If the given ``config`` is missing any of the mandatory
            keys (uuid, project and/or title).
        MissingCapellaModule
            If the model is missing a ``CapellaModule`` from the UUID
            declared in the ``config``.
        InvalidWorkItemType
            May be raised during
            :meth:`TrackerChange.calculate_change` if an unknown ID of a
            RequirementType is used (i.e. the integrity of the
            ``requirement_types`` section in the snapshot is broken).
        InvalidFieldValue
            May be raised during
            :meth:`TrackerChange.calculate_change` if it is tried to
            set an unavailable field value (i.e. the integrity of the
            ``attributes`` of a work item is broken).
        """
        self.tracker = tracker
        self.data_type_definitions = self.tracker.get("data_types", {})
        self.requirement_types = self.tracker.get("requirement_types", {})

        self.model = model
        self.config = config
        self.gather_logs = gather_logs
        self.actions = []

        self._location_changed = set[RMIdentifier]()
        self._req_deletions = {}
        self._evdeletions = set[RMIdentifier]()
        self._faulty_attribute_definitions = set[str]()
        self.errors = []

        self.calculate_change()

    def calculate_change(self) -> None:
        """Render actions for CapellaModule synchronization.

        Handles synchronization of RequirementTypesFolder first and
        Requirements and Folders afterwards. If no
        RequirementTypesFolder was found an action for creation will be
        added to the actions. Work items are searched by the
        ``identifier``. Location changes of work items will invalidate
        deletions.
        """
        base = self.check_requirements_module()
        self.reqt_folder = find.find_by_identifier(  # type: ignore [assignment]
            self.model,
            TYPES_FOLDER_IDENTIFIER,
            reqif.CapellaTypesFolder.__name__,
            below=self.req_module,
        )
        if self.reqt_folder is None:
            base = self.requirement_types_folder_create_action(base)
        else:
            assert isinstance(self.reqt_folder, reqif.CapellaTypesFolder)
            reqt_folder_action = self.data_type_definition_mod_actions()
            if reqtype_deletions := self.requirement_type_delete_actions():
                dels = {"delete": {"requirement_types": reqtype_deletions}}
                _deep_update(reqt_folder_action, dels)

            reqtype_creations = list[dict[str, t.Any]]()
            for id, reqtype in self.requirement_types.items():
                id = RMIdentifier(id)
                if new_rtype := self.requirement_type_mod_action(id, reqtype):
                    reqtype_creations.append(new_rtype)

            if reqtype_creations:
                exts = {"extend": {"requirement_types": reqtype_creations}}
                _deep_update(reqt_folder_action, exts)

            if set(reqt_folder_action) != {"parent"}:
                self.actions.append(reqt_folder_action)

        visited = set[str]()
        for item in self.tracker["items"]:
            if "children" in item:
                type = "Folder"
                second_key = "folders"
            else:
                type = "Requirement"
                second_key = "requirements"

            req = find.find_by_identifier(self.model, item["id"], type)
            if req is None:
                req_actions = self.yield_requirements_create_actions(item)
                item_action = next(req_actions)
                _add_action_safely(base, "extend", second_key, item_action)
            else:
                assert isinstance(req, (reqif.Requirement, reqif.Folder))
                try:
                    req_actions = self.yield_requirements_mod_actions(
                        req, item
                    )
                except act.InvalidWorkItemType as error:
                    self._handle_user_error(
                        f"Invalid workitem '{item['id']}'. " + error.args[0]
                    )
                    continue

                visited.add(req.identifier)
                if req.parent != self.req_module:
                    iaction = decl.UUIDReference(req.uuid)
                    _add_action_safely(base, "extend", second_key, iaction)
                    self._location_changed.add(RMIdentifier(req.identifier))
                    self.invalidate_deletion(req)

            self.actions.extend(req_actions)

        for action in self._req_deletions.values():
            if set(action) == {"parent"}:
                self.actions.remove(action)

        _deep_update(base, self.req_delete_actions(visited))
        _deep_update(base, self.req_delete_actions(visited, "folders"))
        if set(base) != {"parent"}:
            self.actions.append(base)

    def check_requirements_module(self) -> dict[str, t.Any]:
        """Return the starting action for the ``CapellaModule``.

        Check if a ``CapellaModule`` can be found and that the config is
        valid.
        """
        try:
            module_uuid = self.config["capella-uuid"]
            req_module = find.find_by(
                self.model, module_uuid, "CapellaModule", attr="uuid"
            )
        except KeyError as error:
            raise act.InvalidTrackerConfig(
                "The given module configuration is missing UUID of the "
                "target CapellaModule"
            ) from error

        if req_module is None:
            raise MissingCapellaModule(
                f"No CapellaModule with UUID {module_uuid!r} found in "
                + repr(self.model.info)
            )

        try:
            identifier = self.tracker["id"]
        except KeyError as error:
            raise act.InvalidSnapshotModule(
                "In the snapshot the module is missing an id key"
            ) from error

        assert isinstance(req_module, reqif.CapellaModule)
        self.req_module = req_module
        base: dict[str, t.Any] = {
            "parent": decl.UUIDReference(self.req_module.uuid)
        }
        if self.req_module.identifier != identifier:
            base["modify"] = {"identifier": identifier}

        long_name = self.tracker.get("long_name", self.req_module.long_name)
        if self.req_module.long_name != long_name:
            base.setdefault("modify", {})["long_name"] = long_name

        return base

    def _handle_user_error(self, message: str) -> None:
        if self.gather_logs:
            self.errors.append(message)
            return

        LOGGER.error("Invalid module '%s'. %s", self.tracker["id"], message)

    def invalidate_deletion(self, requirement: WorkItem) -> None:
        """Try to remove ``requirement`` from deletions.

        Remove empty dictionaries or even whole action if its only
        delete action was removed.
        """
        key = "requirements"
        if isinstance(requirement, reqif.Folder):
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

    def req_delete_actions(
        self,
        visited: cabc.Iterable[str],
        attr_name: str = "requirements",
    ) -> dict[str, t.Any]:
        """Return an action for deleting elements under the ReqModule.

        Filter all elements from the CapellaModule attribute with
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

    def requirement_types_folder_create_action(
        self, base: dict[str, t.Any]
    ) -> dict[str, t.Any]:
        """Return an action for creating the ``CapellaTypesFolder``.

        See Also
        --------
        capellambse.extensions.reqif.CapellaTypesFolder :
            Folder for (Data-)Type- and Attribute-Definitions
        """
        data_type_defs = self.yield_data_type_definition_create_actions()
        req_types = self.yield_requirement_type_create_actions()
        reqt_folder = {
            "long_name": REQ_TYPES_FOLDER_NAME,
            "identifier": TYPES_FOLDER_IDENTIFIER,
            "data_type_definitions": list(data_type_defs),
            "requirement_types": list(req_types),
        }
        base["extend"] = {"requirement_types_folders": [reqt_folder]}
        return base

    def yield_data_type_definition_create_actions(
        self,
    ) -> cabc.Iterator[dict[str, t.Any]]:
        r"""Yield actions for creating ``EnumDataTypeDefinition``\ s."""
        for id, ddef in self.data_type_definitions.items():
            yield self.data_type_create_action(id, ddef)

    # pylint: disable=line-too-long
    def data_type_create_action(
        self, data_type_id: str, data_type_definition: act.DataType
    ) -> dict[str, t.Any]:
        r"""Return an action for creating an ``EnumDataTypeDefinition``.

        See Also
        --------
        capellambse.extensions.reqif.EnumerationDataTypeDefinition :
            Definition for the ``data_type`` attribute of
            :class:`~capellambse.extensions.reqif.AttributeDefinitionEnumeration`\
            s.
        """
        type = "EnumerationDataTypeDefinition"
        enum_values = [
            {
                "identifier": value["id"],
                "long_name": value["long_name"],
                "promise_id": f"EnumValue {data_type_id} {value['id']}",
            }
            for value in data_type_definition["values"]
        ]
        return {
            "identifier": data_type_id,
            "long_name": data_type_definition["long_name"],
            "values": enum_values,
            "promise_id": f"{type} {data_type_id}",
            "_type": type,
        }

    def yield_requirement_type_create_actions(
        self,
    ) -> cabc.Iterator[dict[str, t.Any]]:
        r"""Yield actions for creating ``RequirementType``\ s."""
        for identifier, req_type in self.requirement_types.items():
            yield self.requirement_type_create_action(identifier, req_type)

    def requirement_type_create_action(
        self, identifier: RMIdentifier, req_type: act.RequirementType
    ) -> dict[str, t.Any]:
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
        attribute_definitions = list[dict[str, t.Any]]()
        for id, adef in req_type.get("attributes", {}).items():
            try:
                attr_def = self.attribute_definition_create_action(
                    id, adef, identifier
                )
                attribute_definitions.append(attr_def)
            except act.InvalidAttributeDefinition as error:
                self._handle_user_error(
                    f"In RequirementType '{req_type['long_name']}': "
                    + error.args[0]
                )

        return {
            "identifier": identifier,
            "long_name": req_type["long_name"],
            "promise_id": f"RequirementType {identifier}",
            "attribute_definitions": attribute_definitions,
        }

    def attribute_definition_create_action(
        self,
        id: str,
        item: act.AttributeDefinition | act.EnumAttributeDefinition,
        req_type_id: str,
    ) -> dict[str, t.Any]:
        r"""Return an action for creating ``AttributeDefinition``\ s.

        In case of an ``AttributeDefinitionEnumeration`` requires
        ``id`` of possibly promised ``EnumerationDataTypeDefinition``.

        See Also
        --------
        capellambse.extensions.reqif.EnumerationDataTypeDefinition
        capellambse.extensions.reqif.AttributeDefinition
        capellambse.extensions.reqif.AttributeDefinitionEnumeration
        """
        identifier = f"{id} {req_type_id}"
        base: dict[str, t.Any] = {
            "identifier": identifier,
            "long_name": item["long_name"],
        }
        cls: AttributeDefinitionClass = reqif.AttributeDefinition
        if item["type"] == "Enum":
            cls = reqif.AttributeDefinitionEnumeration
            etdef = find.find_by_identifier(
                self.model,
                id,
                "EnumerationDataTypeDefinition",
                below=self.reqt_folder,
            )
            if etdef is None:
                promise_id = f"EnumerationDataTypeDefinition {id}"
                if id not in self.data_type_definitions:
                    self._faulty_attribute_definitions.add(promise_id)
                    raise act.InvalidAttributeDefinition(
                        f"Invalid {cls.__name__} found: {id!r}. Missing its "
                        "datatype definition in `data_types`."
                    )

                ref: decl.Promise | decl.UUIDReference = decl.Promise(
                    promise_id
                )
            else:
                ref = decl.UUIDReference(etdef.uuid)

            base["data_type"] = ref
            base["multi_valued"] = item.get("multi_values") is not None

        base["_type"] = cls.__name__
        base["promise_id"] = f"{cls.__name__} {identifier}"
        return base

    def yield_requirements_create_actions(
        self, item: act.WorkItem
    ) -> cabc.Iterator[dict[str, t.Any]]:
        """Yield actions for creating Requirements or Folders.

        The ``WorkItem`` is identified as a ``RequirementsFolder`` if
        there are non-empty ``children`` or a ``(Type, "Folder")`` pair
        in the attributes exists. Also yields creations or modifications
        for children.

        See Also
        --------
        capellambse.extensions.reqif.Requirement
        capellambse.extensions.reqif.RequirementsFolder
        """
        iid = item["id"]
        attributes = list[dict[str, t.Any]]()
        req_type_id = RMIdentifier(item.get("type", ""))
        for attr_id, value in item.get("attributes", {}).items():
            check = self._check_attribute((attr_id, value), (req_type_id, iid))
            if check == "break":
                break
            elif check == "continue":
                continue

            self._try_create_attribute_value(
                (attr_id, value), (req_type_id, iid), attributes
            )

        identifier = RMIdentifier(str(item["id"]))
        base: dict[str, t.Any] = {
            "long_name": item["long_name"],
            "identifier": identifier,
        }
        if text := item.get("text"):
            base["text"] = text

        if attributes:
            base["attributes"] = attributes

        if req_type_id:
            reqtype = find.find_by_identifier(
                self.model,
                req_type_id,
                "RequirementType",
                below=self.reqt_folder,
            )
            if reqtype is None:
                base["type"] = decl.Promise(f"RequirementType {req_type_id}")
            else:
                base["type"] = decl.UUIDReference(reqtype.uuid)

        child_mods: list[dict[str, t.Any]] = []
        if "children" in item:
            base["requirements"] = []
            base["folders"] = []
            child: act.WorkItem
            for child in item["children"]:
                if "children" in child:
                    key = "folders"
                    creq = find.find_by_identifier(
                        self.model, child["id"], "Folder"
                    )
                else:
                    key = "requirements"
                    creq = find.find_by_identifier(
                        self.model, child["id"], "Requirement"
                    )

                action: dict[str, t.Any] | decl.UUIDReference
                if creq is None:
                    child_actions = self.yield_requirements_create_actions(
                        child
                    )
                    # pylint: disable=stop-iteration-return
                    action = next(child_actions)
                else:
                    assert isinstance(creq, (reqif.Requirement, reqif.Folder))
                    child_actions = self.yield_requirements_mod_actions(
                        creq, child, decl.Promise(identifier)
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

    def _check_attribute(
        self,
        attribute: tuple[t.Any, t.Any],
        identifiers: tuple[RMIdentifier, t.Any],
    ) -> str | None:
        id, value = attribute
        req_type_id, iitem_id = identifiers
        if not req_type_id:
            self._handle_user_error(
                f"Invalid workitem '{iitem_id}'. "
                "Missing type but attributes found"
            )
            return "break"

        if _blacklisted(id, value):
            return "continue"

        reqtype_defs = self.requirement_types.get(req_type_id)
        if reqtype_defs and id not in reqtype_defs["attributes"]:
            self._handle_user_error(
                f"Invalid workitem '{iitem_id}'. "
                f"Invalid field found: field identifier '{id}' not defined in "
                f"attributes of requirement type '{req_type_id}'"
            )
            return "continue"
        return None

    def _try_create_attribute_value(
        self,
        attribute: tuple[t.Any, t.Any],
        identifiers: tuple[RMIdentifier, t.Any],
        actions: list[dict[str, t.Any]],
    ) -> None:
        id, value = attribute
        req_type_id, iitem_id = identifiers
        try:
            action = self.attribute_value_create_action(id, value, req_type_id)
            actions.append(action)
        except act.InvalidFieldValue as error:
            self._handle_user_error(
                f"Invalid workitem '{iitem_id}'. {error.args[0]}"
            )

    def attribute_value_create_action(
        self,
        id: str,
        value: act.Primitive | RMIdentifier,
        req_type_id: RMIdentifier,
    ) -> dict[str, t.Any]:
        """Return an action for creating an ``AttributeValue``.

        Requires ``id`` of possibly promised
        ``AttributeDefinition/AttributeDefinitionEnumeration`` and
        checks given ``value`` to be of the correct types.

        See Also
        --------
        capellambse.extension.reqif.IntegerValueAttribute
        capellambse.extension.reqif.StringValueAttribute
        capellambse.extension.reqif.RealValueAttribute
        capellambse.extension.reqif.DateValueAttribute
        capellambse.extension.reqif.BooleanValueAttribute
        capellambse.extension.reqif.EnumerationValueAttribute
        """
        builder = self.check_attribute_value_is_valid(id, value, req_type_id)
        deftype = "AttributeDefinition"
        values: list[decl.UUIDReference | decl.Promise] = []
        if builder.deftype == "Enum":
            deftype += "Enumeration"
            assert isinstance(builder.value, list)
            edtdef = find.find_by_identifier(
                self.model,
                id,
                "EnumerationDataTypeDefinition",
                below=self.reqt_folder,
            )

            for evid in builder.value:
                if isinstance(evid, decl.UUIDReference):
                    eid: str = evid.uuid
                elif isinstance(evid, decl.Promise):
                    eid = evid.identifier
                else:
                    eid = evid

                enumvalue = find.find_by_identifier(
                    self.model,
                    eid,
                    "EnumValue",
                    below=edtdef or self.reqt_folder,
                )
                ev_ref: decl.Promise | decl.UUIDReference
                if enumvalue is None or evid in self._evdeletions:
                    ev_ref = decl.Promise(f"EnumValue {id} {evid}")
                    assert ev_ref is not None
                else:
                    ev_ref = decl.UUIDReference(enumvalue.uuid)

                values.append(ev_ref)

        attr_def_id = f"{id} {req_type_id}"
        definition = find.find_by_identifier(
            self.model, attr_def_id, deftype, below=self.reqt_folder
        )
        definition_ref: decl.Promise | decl.UUIDReference
        if definition is None:
            promise_id = f"{deftype} {attr_def_id}"
            if promise_id in self._faulty_attribute_definitions:
                raise act.InvalidFieldValue(
                    f"Invalid field found: No AttributeDefinition {id!r} "
                    "promised."
                )
            else:
                definition_ref = decl.Promise(promise_id)
        else:
            definition_ref = decl.UUIDReference(definition.uuid)

        return {
            "_type": builder.deftype.lower(),
            "definition": definition_ref,
            builder.key: values or builder.value,
        }

    def check_attribute_value_is_valid(
        self, id: str, value: act.Primitive, req_type_id: RMIdentifier
    ) -> _AttributeValueBuilder:
        """Perform various integrity checks on the given attribute value.

        Raises
        ------
        capella_rm_bridge.changeset.actiontypes.InvalidFieldValue
            If the types are not matching, if the used data_type
            definition is missing in the snapshot or the used options
            on an `EnumerationAttributeValue` are missing in the
            snapshot.

        Returns
        -------
        builder
            A data-class that gathers all needed data for creating the
            `(Enumeration)AttributeValue`.
        """
        reqtype_attr_defs = self.requirement_types[req_type_id]["attributes"]
        deftype = reqtype_attr_defs[id]["type"]
        if default_type := _ATTR_VALUE_DEFAULT_MAP.get(deftype):
            matches_type = isinstance(value, default_type)
        else:
            matches_type = True
            LOGGER.warning(
                "Unknown field type '%s' for %s: %r", deftype, id, value
            )

        if not matches_type:
            assert default_type is not None
            raise act.InvalidFieldValue(
                f"Invalid field found: {id!r}. Not matching expected types: "
                f"{value!r} should be of type {default_type.__name__!r}"
            )

        if deftype == "Enum":
            datatype = self.data_type_definitions.get(id)
            if datatype is None:
                raise act.InvalidFieldValue(
                    f"Invalid field found: {id!r}. Missing its "
                    "datatype definition in `data_types`."
                )

            assert isinstance(value, cabc.Iterable)
            assert not isinstance(value, str)
            options = (value["id"] for value in datatype["values"])
            key = "values"
            if not set(value) & set(options):
                raise act.InvalidFieldValue(
                    f"Invalid field found: {key} {value!r} for {id!r}"
                )
        else:
            key = "value"

        return _AttributeValueBuilder(deftype, key, value)

    def data_type_definition_mod_actions(self) -> dict[str, t.Any]:
        r"""Populate with ModActions for the RequirementTypesFolder.

        The data type definitions and requirement type are checked via
        :meth:`~TrackerChange.make_datatype_definition_mod_action` and
        :meth:`~TrackerChange.make_reqtype_mod_action` respectively.
        If there are changes the ``actions`` container will be
        populated.
        """
        assert self.reqt_folder
        dt_defs_deletions: list[decl.UUIDReference] = [
            decl.UUIDReference(dtdef.uuid)
            for dtdef in self.reqt_folder.data_type_definitions
            if dtdef.identifier not in self.data_type_definitions
        ]
        self._populate_ev_deletions(dt_defs_deletions)

        dt_defs_creations = list[dict[str, t.Any]]()
        dt_defs_modifications = list[dict[str, t.Any]]()
        for id, ddef in self.data_type_definitions.items():
            action = self.data_type_mod_action(id, ddef)
            if action is None:
                continue

            if "parent" in action:
                dt_defs_modifications.append(action)
            else:
                dt_defs_creations.append(action)

        base: dict[str, t.Any] = {
            "parent": decl.UUIDReference(self.reqt_folder.uuid)
        }
        if dt_defs_creations:
            base["extend"] = {"data_type_definitions": dt_defs_creations}
        if dt_defs_deletions:
            base["delete"] = {"data_type_definitions": dt_defs_deletions}

        self.actions.extend(dt_defs_modifications)
        return base

    def _populate_ev_deletions(self, refs: list[decl.UUIDReference]) -> None:
        for ref in refs:
            dtdef = self.model.by_uuid(ref.uuid)
            self._evdeletions |= set(dtdef.values.by_identifier)

    def data_type_mod_action(
        self, id: str, ddef: act.DataType
    ) -> dict[str, t.Any] | None:
        """Return an Action for creating or modifying a DataTypeDefinition.

        If a :class:`reqif.DataTypeDefinition` can be found via ``id``
        and it differs against the snapshot an action for modification
        is returned. If it doesn't differ the returned ``action`` is
        ``None``. If the definition can't be found an action for
        creating an
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
            dtdef = self.reqt_folder.data_type_definitions.by_identifier(
                id, single=True
            )
            base: dict[str, t.Any] = {"parent": decl.UUIDReference(dtdef.uuid)}
            mods = dict[str, t.Any]()
            if dtdef.long_name != ddef["long_name"]:
                mods["long_name"] = ddef["long_name"]

            if mods:
                base["modify"] = mods

            creations = [
                value
                for value in ddef["values"]
                if value["id"] not in dtdef.values.by_identifier
            ]
            action = self.data_type_create_action(
                id, {"long_name": ddef["long_name"], "values": creations}
            )
            if creations:
                base["extend"] = {"values": action["values"]}

            deletions = set(dtdef.values.by_identifier) - set(
                value["id"] for value in ddef["values"]
            )
            if deletions:
                evs = dtdef.values.by_identifier(*deletions)
                self._evdeletions |= deletions
                base["delete"] = {
                    "values": [decl.UUIDReference(ev.uuid) for ev in evs]
                }

            if set(base) == {"parent"}:
                return None
            return base
        except KeyError:
            return self.data_type_create_action(id, ddef)

    def requirement_type_delete_actions(self) -> list[decl.UUIDReference]:
        r"""Populate actions for deleting ``RequirementType``\ s."""
        assert self.reqt_folder
        dels = [
            decl.UUIDReference(reqtype.uuid)
            for reqtype in self.reqt_folder.requirement_types
            if RMIdentifier(reqtype.identifier) not in self.requirement_types
        ]
        return dels

    def requirement_type_mod_action(
        self, identifier: RMIdentifier, item: act.RequirementType
    ) -> None | dict[str, t.Any]:
        assert self.reqt_folder
        try:
            reqtype = self.reqt_folder.requirement_types.by_identifier(
                identifier, single=True
            )
            assert isinstance(reqtype, reqif.RequirementType)

            try:
                mods = _compare_simple_attributes(
                    reqtype, item, filter=("attributes",)
                )
            except AttributeError as error:
                self._handle_user_error(
                    f"Invalid workitem '{identifier}'. {error.args[0]}"
                )

            attribute_definition_ids = {
                f"{id} {reqtype.identifier}" for id in item["attributes"]
            }
            attr_defs_deletions: list[decl.UUIDReference] = [
                decl.UUIDReference(adef.uuid)
                for adef in reqtype.attribute_definitions
                if adef.identifier not in attribute_definition_ids
            ]

            attr_defs_creations = list[dict[str, t.Any]]()
            attr_defs_modifications = list[dict[str, t.Any]]()
            for id, data in item["attributes"].items():
                action = self.attribute_definition_mod_action(
                    reqtype, id, data
                )
                if action is None:
                    continue

                if "parent" in action:
                    attr_defs_modifications.append(action)
                else:
                    attr_defs_creations.append(action)

            base: dict[str, t.Any] = {
                "parent": decl.UUIDReference(reqtype.uuid)
            }
            if mods:
                base["modify"] = mods

            if attr_defs_creations:
                base["extend"] = {"attribute_definitions": attr_defs_creations}
            if attr_defs_deletions:
                base["delete"] = {"attribute_definitions": attr_defs_deletions}

            if set(base) != {"parent"}:
                self.actions.append(base)

            self.actions.extend(attr_defs_modifications)
            return None
        except KeyError:
            return self.requirement_type_create_action(identifier, item)

    def yield_requirements_mod_actions(
        self,
        req: reqif.CapellaModule | WorkItem,
        item: dict[str, t.Any] | act.WorkItem,
        parent: reqif.CapellaModule | WorkItem | decl.Promise | None = None,
    ) -> cabc.Iterator[dict[str, t.Any]]:
        """Yield an action for modifying given ``req``.

        If any modifications to simple attributes (e.g. ``long_name``),
        attributes or creations/deletions of children
        (in case of ``req`` being a Folder) were identified an action
        for modification of ``req`` is yielded. For modifications of
        children the method is called recursively and yields actions
        from it.
        """
        base: dict[str, t.Any] = {"parent": decl.UUIDReference(req.uuid)}
        try:
            mods = _compare_simple_attributes(
                req, item, filter=("id", "type", "attributes", "children")
            )
        except AttributeError as error:
            self._handle_user_error(
                f"Invalid workitem '{item['id']}'. {error.args[0]}"
            )
            return

        req_type_id = RMIdentifier(item.get("type", ""))
        attributes_deletions = list[decl.UUIDReference]()
        if req_type_id != req.type.identifier:
            if req_type_id and req_type_id not in self.requirement_types:
                raise act.InvalidWorkItemType(
                    "Faulty workitem in snapshot: "
                    f"Unknown workitem-type {req_type_id!r}"
                )

            reqtype = find.find_by_identifier(
                self.model,
                req_type_id,
                "RequirementType",
                below=self.reqt_folder,
            )
            if reqtype is None:
                mods["type"] = decl.Promise(req_type_id)
            else:
                mods["type"] = decl.UUIDReference(reqtype.uuid)

            attributes_deletions = [
                decl.UUIDReference(attr.uuid) for attr in req.attributes
            ]

        iid = item["id"]
        item_attributes = item.get("attributes", {})
        attributes_creations = list[dict[str, t.Any]]()
        attributes_modifications = list[dict[str, t.Any]]()
        for id, value in item_attributes.items():
            check = self._check_attribute((id, value), (req_type_id, iid))
            if check == "break":
                break
            elif check == "continue":
                continue

            action: act.Primitive | dict[str, t.Any] | None
            if mods.get("type"):
                self._try_create_attribute_value(
                    (id, value), (req_type_id, iid), attributes_creations
                )
            else:
                try:
                    action = self.attribute_value_mod_action(
                        req, id, value, req_type_id
                    )
                    if action is None:
                        continue

                    attributes_modifications.append(action)
                except KeyError:
                    self._try_create_attribute_value(
                        (id, value), (req_type_id, iid), attributes_creations
                    )
                except act.InvalidFieldValue as error:
                    self._handle_user_error(
                        f"Invalid workitem '{iid}'. {error.args[0]}"
                    )

        attribute_definition_ids = {
            f"{attr} {req_type_id}" for attr in item_attributes
        }
        if not attributes_deletions:
            attributes_deletions = [
                decl.UUIDReference(attr.uuid)
                for attr in req.attributes
                if attr.definition.identifier not in attribute_definition_ids
            ]

        if mods:
            base["modify"] = mods
        if attributes_creations:
            base["extend"] = {"attributes": attributes_creations}
        if attributes_deletions:
            base["delete"] = {"attributes": attributes_deletions}

        if parent is None:
            parent = self.req_module

        if req.parent != parent:
            self._location_changed.add(RMIdentifier(req.identifier))
            assert not isinstance(req, reqif.CapellaModule)
            self.invalidate_deletion(req)

        children = item.get("children", [])
        cr_creations: list[dict[str, t.Any] | decl.UUIDReference] = []
        cf_creations: list[dict[str, t.Any] | decl.UUIDReference] = []
        containers = [cr_creations, cf_creations]
        child_mods: list[dict[str, t.Any]] = []
        if isinstance(req, reqif.Folder):
            child_req_ids = set[RMIdentifier]()
            child_folder_ids = set[RMIdentifier]()
            for child in children:
                cid = RMIdentifier(str(child["id"]))
                if "children" in child:
                    key = "folders"
                    child_folder_ids.add(cid)
                    creq = find.find_by_identifier(self.model, cid, "Folder")
                else:
                    key = "requirements"
                    child_req_ids.add(cid)
                    creq = find.find_by_identifier(
                        self.model, cid, "Requirement"
                    )

                container = containers[key == "folders"]
                if creq is None:
                    child_actions = self.yield_requirements_create_actions(
                        child
                    )
                    # pylint: disable=stop-iteration-return
                    action = next(child_actions)
                    container.append(action)
                else:
                    assert isinstance(creq, (reqif.Requirement, reqif.Folder))
                    try:
                        child_actions = self.yield_requirements_mod_actions(
                            creq, child, req
                        )
                    except act.InvalidWorkItemType as error:
                        self._handle_user_error(
                            f"Invalid workitem '{child['id']}'. "
                            + error.args[0]
                        )
                        continue

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

        yield from attributes_modifications
        yield from child_mods

    def attribute_value_mod_action(
        self,
        req: reqif.CapellaModule | WorkItem,
        id: str,
        valueid: str | list[str | decl.UUIDReference | decl.Promise],
        req_type_id: RMIdentifier,
    ) -> dict[str, t.Any] | None:
        """Return an action for modifying an ``AttributeValue``.

        If an ``AttributeValue`` can be found via
        ``definition.identifier`` it is compared against the snapshot.
        If any changes to its ``value/s`` are identified a tuple of the
        name and value is returned else None. If the attribute can't be
        found an action for creation is returned.

        Parameters
        ----------
        req
            The ReqIFElement under which the attribute value
            modification takes place.
        id
            The identifier of the definition for the attribute value.
        valueid
            The value identifier from the snapshot that is compared
            against the value on the found attribute if it exists. Else
            a new ``AttributeValue`` with this value is created.
        req_type_id : optional
            The identifier of ``RequirementType`` for given ``req`` if
            it was changed. If not given or ``None`` the identifier
            ``req.type.identifier`` is taken.

        Returns
        -------
        action
            Either a create-action, the value to modify or ``None`` if
            nothing changed.
        """
        builder = self.check_attribute_value_is_valid(id, valueid, req_type_id)
        deftype = "AttributeDefinition"
        if builder.deftype == "Enum":
            deftype += "Enumeration"

        attrdef = find.find_by_identifier(
            self.model, f"{id} {req_type_id}", deftype, below=self.reqt_folder
        )
        attr = req.attributes.by_definition(attrdef, single=True)
        assert attrdef is not None
        if isinstance(attr, reqif.EnumerationValueAttribute):
            assert isinstance(valueid, list)
            actual = set(attr.values.by_identifier)
            delete = actual - set(valueid)
            create = set(valueid) - actual
            differ = bool(create) or bool(delete)
            options = attrdef.data_type.values.by_identifier
            valueid = [
                decl.Promise(f"EnumValue {id} {v}")
                if v not in options
                else decl.UUIDReference(options(v, single=True).uuid)
                for v in create | (actual - delete)
            ]
            key = "values"
        else:
            differ = bool(attr.value != valueid)
            key = "value"

        if differ:
            return {
                "parent": decl.UUIDReference(attr.uuid),
                "modify": {key: valueid},
            }
        return None

    def attribute_definition_mod_action(
        self,
        reqtype: reqif.RequirementType,
        identifier: str,
        data: act.AttributeDefinition | act.EnumAttributeDefinition,
    ) -> dict[str, t.Any] | None:
        """Return an action for an ``AttributeDefinition``.

        If a :class:`capellambse.extensions.reqif.AttributeDefinition`
        or :class:`capellambse.extensions.reqif.AttributeDefinitionEnumeration`
        can be found via its ``identifier``, it is compared against the
        snapshot. If any changes are identified an action for
        modification is returned else None. If the definition can't be
        found an action for creation is returned.

        Returns
        -------
        action
            Either a create-, mod-action or ``None`` if nothing changed.
        """
        try:
            attrdef = reqtype.attribute_definitions.by_identifier(
                f"{identifier} {reqtype.identifier}", single=True
            )
            mods = dict[str, t.Any]()
            if attrdef.long_name != data["long_name"]:
                mods["long_name"] = data["long_name"]
            if data["type"] == "Enum":
                dtype = attrdef.data_type
                if dtype is None or dtype.identifier != identifier:
                    mods["data_type"] = identifier
                if attrdef.multi_valued != data.get("multi_values", False):
                    mods["multi_valued"] = data[
                        "multi_values"  # type:ignore[typeddict-item]
                    ]
            if not mods:
                return None
            return {"parent": decl.UUIDReference(attrdef.uuid), "modify": mods}
        except KeyError:
            try:
                return self.attribute_definition_create_action(
                    identifier, data, reqtype.identifier
                )
            except act.InvalidAttributeDefinition as error:
                self._handle_user_error(
                    f"In RequirementType {reqtype.long_name!r}: "
                    + error.args[0]
                )
                return None


def make_requirement_delete_actions(
    req: reqif.Folder,
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


def _blacklisted(name: str, value: act.Primitive | None) -> bool:
    """Identify if a key value pair is supported."""
    if value is None:
        return False
    if not isinstance(value, cabc.Iterable) or isinstance(value, str):
        return (name, value) in _ATTR_BLACKLIST
    return all((_blacklisted(name, val) for val in value))


def _compare_simple_attributes(
    req: reqif.ReqIFElement,
    item: dict[str, t.Any] | act.WorkItem | act.RequirementType,
    filter: cabc.Iterable[str],
) -> dict[str, t.Any]:
    """Return a diff dictionary about changed attributes.

    The given ``req`` is compared against given ``item`` and any
    attribute name in given ``filter`` is skipped.

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
    type_conversion = {"text": helpers.repair_html}
    mods: dict[str, t.Any] = {}
    for name, value in item.items():
        if name in filter:
            continue

        converter = type_conversion.get(name, lambda i: i)
        converted_value = converter(value)  # type: ignore[arg-type]
        if getattr(req, name) != converted_value:
            mods[name] = value
    return mods


def _add_action_safely(
    base: dict[str, t.Any],
    first_key: str,
    second_key: str,
    action: dict[str, t.Any] | decl.UUIDReference,
) -> None:
    try:
        base[first_key][second_key].append(action)
    except KeyError:
        _deep_update(base, {first_key: {second_key: [action]}})


def _deep_update(
    source: cabc.MutableMapping[str, t.Any],
    overrides: cabc.Mapping[str, t.Any],
) -> None:
    """Update a nested dictionary in place."""
    for key, value in overrides.items():
        if isinstance(value, cabc.Mapping) and value:
            update = source.get(key, {})
            _deep_update(update, value)
        else:
            update = overrides[key]

        source[key] = update
