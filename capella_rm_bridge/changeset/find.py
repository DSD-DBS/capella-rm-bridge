# SPDX-FileCopyrightText: Copyright DB Netz AG and the capella-rm-bridge contributors
# SPDX-License-Identifier: Apache-2.0

"""Functionality for finding ReqIF elements in a ``MelodyModel``."""
from __future__ import annotations

import logging
import typing as t

import capellambse
from capellambse.extensions import reqif
from capellambse.model import common

LOGGER = logging.getLogger(__name__)


def find_by(
    model: capellambse.MelodyModel,
    value: t.Any,
    *xtypes: str,
    attr: str = "identifier",
    below: common.GenericElement | None = None,
) -> reqif.ReqIFElement | None:
    try:
        objs = model.search(*xtypes, below=below)
        return getattr(objs, f"by_{attr}")(value, single=True)
    except KeyError:
        types = " or ".join(xt.split(":")[-1] for xt in xtypes)
        LOGGER.info("No %s found with %s: %r", types, attr, value)
    return None


def find_by_identifier(
    model: capellambse.MelodyModel, id: str, *xtypes: str, **kw
) -> reqif.ReqIFElement | None:
    """Try to return a model object by its ``identifier``."""
    return find_by(model, id, *xtypes, **kw)
