# SPDX-FileCopyrightText: Copyright DB Netz AG and the capella-rm-bridge contributors
# SPDX-License-Identifier: Apache-2.0

"""Functionality for finding ReqIF elements in a ``MelodyModel``."""
from __future__ import annotations

import logging
import typing as t

import capellambse
from capellambse.extensions import reqif
from capellambse.model import crosslayer

LOGGER = logging.getLogger(__name__)


class ReqFinder:
    """Find ReqIF elements in a ``MelodyModel`` easily and efficiently."""

    def __init__(self, model: capellambse.MelodyModel) -> None:
        self.model = model

    def _get(
        self,
        value: t.Any,
        *xtypes: str,
        attr: str = "identifier",
        below: reqif.ReqIFElement | None = None,
    ) -> reqif.ReqIFElement | None:
        try:
            objs = self.model.search(*xtypes, below=below)
            return getattr(objs, f"by_{attr}")(value, single=True)
        except KeyError:
            types = " or ".join(xt.split(":")[-1] for xt in xtypes)
            LOGGER.info("No %s found with %s: %r", types, attr, value)
        return None

    def reqmodule(self, uuid: str) -> reqif.RequirementsModule | None:
        """Try to return the ``RequirementsModule``."""
        return self._get(uuid, reqif.XT_MODULE, attr="uuid")

    def reqtypesfolder_by_identifier(
        self,
        identifier: int | str,
        below: crosslayer.BaseArchitectureLayer
        | reqif.RequirementsModule
        | None = None,
    ) -> reqif.RequirementsTypesFolder | None:
        """Try to return the ``RequirementTypesFolder``."""
        return self._get(str(identifier), reqif.XT_REQ_TYPES_F, below=below)

    def reqtype_by_identifier(
        self, identifier: int | str, below: reqif.ReqIFElement | None = None
    ) -> reqif.RequirementsType | None:
        """Try to return a ``RequirementType``."""
        return self._get(str(identifier), reqif.XT_REQ_TYPE, below=below)

    def attribute_definition_by_identifier(
        self, xtype: str, identifier: str, below: reqif.ReqIFElement | None
    ) -> reqif.AttributeDefinition | reqif.AttributeDefinitionEnumeration:
        """Try to return an ``AttributeDefinition``-/``Enumeration``."""
        return self._get(identifier, xtype, below=below)

    def work_item_by_identifier(
        self,
        identifier: int | str,
        below: reqif.ReqIFElement | None = None,
    ) -> reqif.Requirement | reqif.RequirementsFolder | None:
        """Try to return a ``Requirement``/``RequirementsFolder``."""
        return self._get(
            str(identifier), reqif.XT_REQUIREMENT, reqif.XT_FOLDER, below=below
        )

    def enum_data_type_definition_by_long_name(
        self, long_name: str, below: reqif.ReqIFElement | None
    ) -> reqif.EnumDataTypeDefinition | None:
        """Try to return an ``EnumDataTypeDefinition``.

        The object is matched with given ``long_name``.
        """
        return self._get(
            long_name, reqif.XT_REQ_TYPE_ENUM, attr="long_name", below=below
        )

    def enum_value_by_long_name(
        self, long_name: str, below: reqif.ReqIFElement | None = None
    ) -> reqif.EnumValue | None:
        """Try to return an ``EnumValue``.

        The object is matched with given ``long_name``.
        """
        xt = reqif.XT_REQ_TYPE_ATTR_ENUM
        return self._get(long_name, xt, attr="long_name", below=below)
