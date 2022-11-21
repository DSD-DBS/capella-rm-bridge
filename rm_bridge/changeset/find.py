# SPDX-FileCopyrightText: Copyright DB Netz AG and the rm-bridge contributors
# SPDX-License-Identifier: Apache-2.0

"""Functionality for finding Reqif elements in a `MelodyModel`."""
from __future__ import annotations

import logging

import capellambse
from capellambse.extensions import reqif
from capellambse.model import crosslayer

LOGGER = logging.getLogger(__name__)


class ReqFinder:
    """Find RM elements in a ``MelodyModel`` easily and efficiently."""

    def __init__(self, model: capellambse.MelodyModel) -> None:
        self.model = model

    def find_reqmodule(
        self, uuid: str, identifier: int | str | None = None
    ) -> reqif.RequirementsModule | None:
        """Try to return the ``RequirementsModule``.

        Parameters
        ----------
        uuid
            UUID string for the RequirementsModule to find.
        identifier : optional
            The ReqIFIdentifier that is written if the given doesn't
            match the found. Optional

        Returns
        -------
        requirement_module
            The ``RequirementsModule`` with the given ``uuid``.
        """
        req_module = None
        try:
            req_module = self.model.by_uuid(uuid)
            assert isinstance(req_module, reqif.RequirementsModule)
            if identifier and req_module.identifier != str(identifier):
                req_module.identifier = str(identifier)
        except KeyError:
            LOGGER.error(
                "No RequirementsModule found for tracker: '%s'.", identifier
            )
        return req_module

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
                reqif.XT_REQ_TYPES_F, below=below
            ).by_identifier(str(uid), single=True)
            assert isinstance(reqtf, reqif.RequirementsTypesFolder)
            return reqtf
        except KeyError:
            LOGGER.warning("No RequirementsTypeFolder found.")
            return None

    def find_reqtype_by_identifier(
        self, uid: int | str, below: reqif.ReqIFElement | None = None
    ) -> reqif.RequirementsType | None:
        """Try to return the RequirementType."""
        try:
            reqtype = self.model.search(
                reqif.XT_REQ_TYPE, below=below
            ).by_identifier(uid, single=True)
            assert isinstance(reqtype, reqif.RequirementType)
            return reqtype
        except KeyError:
            LOGGER.warning("No RequirementsType found.")
            return None

    def find_work_item_by_identifier(
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

    def find_enumvalue(
        self, name: str, below: reqif.ReqIFElement | None = None
    ) -> reqif.EnumValue | None:
        """Try to return an EnumValue with given ``long_name``."""
        try:
            cls = reqif.EnumValue
            enum_value = self.model.search(
                reqif.XT_REQ_TYPE_ATTR_ENUM, below=below
            ).by_long_name(name, single=True)
            assert isinstance(enum_value, cls)
            return enum_value
        except KeyError:
            LOGGER.warning(
                "No %s found with long_name: '%s'", cls.__name__, name
            )
            return None

    def find_attribute_definition_by_identifier(
        self, uid: int | str, below: reqif.ReqIFElement | None
    ) -> reqif.AttributeDefinition | reqif.AttributeDefinitionEnumeration:
        """Try to return an AttributeDefinition with given ``long_name``."""
        def_types = (
            reqif.AttributeDefinition,
            reqif.AttributeDefinitionEnumeration,
        )
        try:
            attrdef = self.model.search(
                reqif.XT_REQ_TYPE_ENUM_DEF,
                reqif.XT_REQ_TYPE_ATTR_DEF,
                below=below,
            ).by_identifier(str(uid), single=True)
            assert isinstance(attrdef, def_types)
            return attrdef
        except KeyError:
            type_names = " or ".join((dt.__name__ for dt in def_types))
            LOGGER.warning(
                "No %s found with identifier: '%s'", type_names, uid
            )
            return None
