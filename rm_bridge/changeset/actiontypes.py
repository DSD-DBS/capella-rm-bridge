# SPDX-FileCopyrightText: Copyright DB Netz AG and the rm-bridge contributors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import datetime
import typing as t

import typing_extensions as te

Primitive = t.Union[int, float, str, list[str], bool, datetime.datetime]


class WorkItem(te.TypedDict, total=False):
    id: te.Required[int]
    long_name: str
    text: str
    attributes: dict[str, t.Any]
    # <https://github.com/python/mypy/issues/731>
    children: list[WorkItem]  # type: ignore[misc]


class TrackerSnapshot(te.TypedDict):
    id: int
    version: int | float
    attributes: dict[str, t.Any]
    items: list[WorkItem]


class AttributeDefinition(te.TypedDict):
    type: str


class EnumAttributeDefinition(AttributeDefinition, total=False):
    values: list[str]
    multi_values: bool
