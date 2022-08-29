# SPDX-FileCopyrightText: Copyright DB Netz AG and the rm-bridge contributors
# SPDX-License-Identifier: Apache-2.0

"""Functionality for finding Reqif elements in a `MelodyModel`."""
from __future__ import annotations

import collections.abc as cabc
import logging

import capellambse
from capellambse.extensions import reqif
from capellambse.model import crosslayer

LOGGER = logging.getLogger(__name__)


class ReqFinder:
    """Find RM elements in a `MelodyModel` easily and efficiently."""

    def __init__(self, model: capellambse.MelodyModel) -> None:
        self.model = model

        self._cache: cabc.Mapping[str, reqif.ReqIFElement] = {}

    def find_module(self, uuid: str, cbid: int) -> reqif.RequirementsModule:
        """Try to return the tracker/RequirementsModule."""
        req_module = None
        try:
            req_module = self.model.by_uuid(uuid)
            assert isinstance(req_module, reqif.RequirementsModule)
            if req_module.identifier != str(cbid):
                req_module.identifier = str(cbid)
            return req_module
        except KeyError as error:
            LOGGER.error(
                "No RequirementsModule found for tracker: '%s'.", cbid
            )
            raise KeyError from error

    def find_reqtypesfolder_by_identifier(
        self,
        uid: int | str,
        below: crosslayer.BaseArchitectureLayer
        | reqif.RequirementsModule
        | None = None,
    ) -> reqif.RequirementsTypesFolder | None:
        """Try to return the RequirementTypesFolder."""
        try:
            reqtf = self.model.search(
                reqif.XT_CAPELLATYPESFOLDER, below=below
            ).by_identifier(str(uid), single=True)
            assert isinstance(reqtf, reqif.RequirementsTypesFolder)
            return reqtf
        except KeyError:
            LOGGER.warning("No RequirementsTypeFolder found.")
            return None

    def find_requirement_by_identifier(
        self,
        cbid: int | str,
        below: reqif.RequirementsModule
        | reqif.RequirementsFolder
        | None = None,
    ) -> reqif.Requirement | reqif.RequirementsFolder | None:
        """Try to return a Requirement with given ``identifier``."""
        try:
            req = self.model.search(
                reqif.XT_REQUIREMENT, reqif.XT_FOLDER, below=below
            ).by_identifier(str(cbid), single=True)
            assert isinstance(req, reqif.Requirement)
            return req
        except KeyError:
            LOGGER.warning("No Requirement found with identifier: '%s'", cbid)
            return None
