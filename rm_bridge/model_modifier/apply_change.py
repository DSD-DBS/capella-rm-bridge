# SPDX-FileCopyrightText: Copyright DB Netz AG and the rm-bridge contributors
# SPDX-License-Identifier: Apache-2.0

"""Functionality for applying actions of a ``ChangeSet`` to a model."""
from __future__ import annotations

import collections.abc as cabc
import copy
import logging

import capellambse
from capellambse.extensions import reqif

from .changeset import (
    CreateAction,
    DeleteAction,
    ModAction,
    actiontypes,
    change,
    find,
)
from .changeset.actiontypes import ActionType

logging.basicConfig(
    format="<%(name)s> %(levelname)s: %(message)s", level="DEBUG"
)


class ModelChange:
    """A model change."""

    model: capellambse.MelodyModel
    """Model instance."""
    reqfinder: find.ReqFinder
    """Find ReqIF elements in the model."""
    logger: logging.Logger

    def __init__(
        self, model: capellambse.MelodyModel, reqfinder: find.ReqFinder
    ) -> None:
        self.model = model
        self.reqfinder = reqfinder

        assert reqfinder.model is model

        self.logger = logging.getLogger(__name__)

    def apply_changes(
        self,
        tracker_id: int,
        tracker_uuid: str,
        changes: cabc.Sequence[CreateAction | ModAction | DeleteAction],
    ) -> None:
        for _change in changes:
            change_ = dict(copy.deepcopy(_change))
            type = change_["_type"]
            if type == ActionType.CREATE:
                self.create_requirement_element(
                    tracker_id, tracker_uuid, change_
                )
            elif type == ActionType.MOD:
                self.mod_requirement_element()
            else:
                assert type == ActionType.DELETE
                self.delete_requirement_element()

    def create_requirement_element(
        self,
        tracker_id: int,
        tracker_uuid: str,
        action: CreateAction,
    ) -> None:
        req_module = self.reqfinder.find_module(tracker_uuid, tracker_id)
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
            obj = parent.requirement_types_folders.create(**action)
        elif action["cls"] in (reqif.Requirement, reqif.RequirementsFolder):
            action: actiontypes.RequirementFolderCreateAction
            req_types_folder = (
                self.reqfinder.find_reqtypesfolder_by_identifier(
                    change.CACHEKEY_TYPES_FOLDER_UUID, below=req_module
                )
            )
            patch_type(action, req_types_folder)
            obj = req_module.folders.create(**action)

        self.logger.info("Created '%r'", obj)

    def mod_requirement_element(self) -> None:
        ...

    def delete_requirement_element(self) -> None:
        ...


def patch_type(
    req: actiontypes.RequirementCreateAction
    | actiontypes.RequirementFolderCreateAction,
    req_types_folder: reqif.RequirementsTypesFolder,
) -> None:
    """Patch ``CreateAction``s."""
    if attributes := req.get("attributes", []):
        for attr in attributes:
            attr["_type"] = attr.pop("cls").__name__
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
