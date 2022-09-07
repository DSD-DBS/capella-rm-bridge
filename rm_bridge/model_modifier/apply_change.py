# SPDX-FileCopyrightText: Copyright DB Netz AG and the rm-bridge contributors
# SPDX-License-Identifier: Apache-2.0

"""Functionality for applying actions of a ``ChangeSet`` to a model."""
from __future__ import annotations

import collections.abc as cabc
import copy
import logging
import typing as t

import capellambse
from capellambse.extensions import reqif
from capellambse.model.common import accessors as acc
from lxml import etree

from .changeset import (
    CreateAction,
    DeleteAction,
    ModAction,
    actiontypes,
    change,
    find,
)
from .changeset.actiontypes import ActionType, Primitive

LOGGER = logging.getLogger(__name__)


class ModelChange:
    """A model change."""

    model: capellambse.MelodyModel
    """Model instance."""
    reqfinder: find.ReqFinder
    """Find ReqIF elements in the model."""
    logger: logging.Logger

    def __init__(
        self,
        model: capellambse.MelodyModel,
        reqfinder: find.ReqFinder | None = None,
    ) -> None:
        self.model = model
        self.reqfinder = reqfinder or find.ReqFinder(model)
        assert self.reqfinder.model is self.model

    def apply_changes(
        self,
        tracker_id: str,
        tracker_uuid: str,
        changes: cabc.MutableSequence[CreateAction | ModAction | DeleteAction],
        target: acc.WritableAccessor
        | acc.ElementListCouplingMixin
        | None = None,
    ) -> None:
        """Apply given ``Action``s to the model."""
        for _change in changes:
            change_ = dict(copy.deepcopy(_change))
            type = change_["_type"]
            if type == ActionType.CREATE:
                self.create_requirement_element(
                    tracker_id, tracker_uuid, change_, target
                )
            elif type == ActionType.MOD:
                self.mod_requirement_element(tracker_id, tracker_uuid, change_)
            else:
                assert type == ActionType.DELETE
                self.delete_requirement_element(
                    tracker_id, tracker_uuid, change_, target
                )

    def create_requirement_element(
        self,
        tracker_id: str,
        tracker_uuid: str,
        action: CreateAction,
        target: acc.WritableAccessor
        | acc.ElementListCouplingMixin
        | None = None,
    ) -> None:
        req_module = self.reqfinder.find_module(tracker_uuid, tracker_id)
        req_types_folder = self.reqfinder.find_reqtypesfolder_by_identifier(
            change.CACHEKEY_TYPES_FOLDER_IDENTIFIER, below=req_module
        )
        if target is not None:
            assert hasattr(target, "create")

        if action["cls"] == reqif.RequirementsTypesFolder:
            action: actiontypes.RequirementTypesFolderCreateAction
            puuid = action.pop("parent")
            parent = self.model.by_uuid(puuid)

            for dtdef in action["data_type_definitions"]:
                dtdef["_type"] = dtdef.pop("cls").__name__

            for reqtype in action["requirement_types"]:
                reqtype["_type"] = reqtype.pop("cls").__name__

                for adef in reqtype["attribute_definitions"]:
                    adef["_type"] = adef.pop("cls").__name__

            del action["_type"]
            del action["cls"]
            obj = (target or parent.requirement_types_folders).create(**action)
        elif action["cls"] == reqif.RequirementsFolder:
            action: actiontypes.RequirementFolderCreateAction
            patch_type(action, req_types_folder)
            obj = (target or req_module.folders).create(**action)
        elif action["cls"] == reqif.Requirement:
            action: actiontypes.RequirementCreateAction
            patch_type(action, req_types_folder)
            obj = (target or req_module.requirements).create(**action)
        else:
            assert target is not None
            del action["_type"]
            obj = target.create(action.pop("cls").__name__, **action)

        LOGGER.info("Created '%r'", obj)

    def mod_requirement_element(
        self, tracker_id: str, tracker_uuid: str, action: ModAction
    ) -> None:
        assert action.pop("_type") == actiontypes.ActionType.MOD
        element = self.model.by_uuid(action.pop("uuid"))

        def values_are_actions(values: list[t.Any]) -> bool:
            return all(isinstance(v, dict) for v in values)

        logger = LOGGER
        value: CreateAction | ModAction | DeleteAction | Primitive
        for attribute, value in action.items():
            target = getattr(element, attribute)
            if isinstance(value, list) and values_are_actions(value):
                self.apply_changes(tracker_id, tracker_uuid, value, target)
            elif attribute == "parent":  # Location change
                assert element.parent.uuid != value
                new_parent = self.model.by_uuid(value)
                old_parent_elt: etree._Element = element._element.getparent()
                old_parent_elt.remove(element._element)
                new_parent._element.append(element._element)
                logger.info("Moved '%r'", element)
            elif isinstance(target, acc.ElementListCouplingMixin):
                set_enum_values(target, value)
            else:
                setattr(element, attribute, value)

    def delete_requirement_element(
        self,
        tracker_id: str,
        tracker_uuid: str,
        action: DeleteAction,
        target: acc.WritableAccessor | acc.ElementListCouplingMixin | None,
    ) -> None:
        req_module = self.reqfinder.find_module(tracker_uuid, tracker_id)
        element = self.model.by_uuid(action["uuid"])
        try:
            rep = element._short_repr_()
        except Exception:
            rep = f"<{type(element).__name__} ({element.uuid})>"

        if isinstance(element, reqif.RequirementsFolder):
            parent = req_module.folders
        elif isinstance(element, reqif.Requirement):
            parent = req_module.requirements
        elif isinstance(element, reqif.AbstractRequirementsAttribute):
            parent = req_module.attributes

        origin = target or parent
        LOGGER.info("Deleting '%s'", rep)
        del origin[origin.index(element)]


def patch_type(
    req: actiontypes.RequirementCreateAction
    | actiontypes.RequirementFolderCreateAction,
    req_types_folder: reqif.RequirementsTypesFolder,
) -> None:
    """Patch ``CreateAction``s."""
    req["type"] = req_types_folder.requirement_types.by_identifier(
        change.CACHEKEY_REQTYPE_IDENTIFIER, single=True
    )
    if attributes := req.get("attributes", []):
        for attr in attributes:
            attr["_type"] = attr.pop("cls").__name__
            attr["definition"] = req[
                "type"
            ].attribute_definitions.by_long_name(
                attr["definition"], single=True
            )
    else:
        del req["attributes"]

    if req["cls"] == reqif.RequirementsFolder:
        for name in ("requirements", "folders"):
            if (value := req.get(name)) is not None and not value:
                del req[name]
            else:
                for item in value:
                    patch_type(item, req_types_folder)

        del req["_type"]
        del req["cls"]
    else:
        req["_type"] = req.pop("cls").__name__


def set_enum_values(
    target: acc.ElementListCouplingMixin,
    value: CreateAction | ModAction | DeleteAction | Primitive,
) -> None:
    assert isinstance(value, list)
    if (nv := len(value)) < (nt := len(target)):
        while len(target) > nv:
            target.pop()
    elif nv > nt:
        while len(target) < nv:
            target.create_singleattr("blank")

    assert nv == len(target)
    for ev, val in zip(target, value):
        if ev.long_name != val:
            ev.long_name = val
