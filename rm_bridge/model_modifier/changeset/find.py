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

    def find_module(
        self, uuid: str, cbid: int | str
    ) -> reqif.RequirementsModule:
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
                reqif.XT_MODULE, below=below
            ).by_identifier(str(uid), single=True)
            assert isinstance(reqtf, reqif.RequirementsTypesFolder)
            return reqtf
        except KeyError:
            LOGGER.warning("No RequirementsTypeFolder found.")
            return None

    def find_requirement_by_identifier(
        self,
        cbid: int | str,
        below: reqif.ReqIFElement | None = None,
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

    def find_enum_data_type_definition(
        self, name: str, below: reqif.ReqIFElement | None
    ) -> reqif.EnumDataTypeDefinition:
        """Try to return an EnumDataTypeDefinition with given ``long_name``."""
        try:
            edtdef = self.model.search(
                reqif.XT_REQ_TYPE_ENUM, below=below
            ).by_long_name(name, single=True)
            assert isinstance(edtdef, reqif.EnumDataTypeDefinition)
            return edtdef
        except KeyError:
            LOGGER.warning(
                "No EnumDataTypeDefinition found with long_name: '%s'", name
            )
            return None

    def find_attribute_definition(
        self, xtype: str, name: str, below: reqif.ReqIFElement | None
    ) -> reqif.AttributeDefinition | reqif.AttributeDefinitionEnumeration:
        """Try to return an AttributeDefinition with given ``long_name``."""
        try:
            if xtype.endswith("Enumeration"):
                cls = reqif.AttributeDefinitionEnumeration
            else:
                cls = reqif.AttributeDefinition

            attrdef = self.model.search(xtype, below=below).by_long_name(
                name, single=True
            )
            assert isinstance(attrdef, cls)
            return attrdef
        except KeyError:
            LOGGER.warning(
                "No %s found with long_name: '%s'", cls.__name__, name
            )
            return None
