# SPDX-FileCopyrightText: Copyright DB Netz AG and the rm-bridge contributors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import collections.abc as cabc
import datetime
import typing as t

import typing_extensions as te

Primitive = t.Union[int, float, str, list[str], bool, datetime.datetime]


class WorkitemTypeConfig(te.TypedDict):
    name: str
    fields: te.NotRequired[cabc.Sequence[str]]


TrackerConfig = te.TypedDict(
    "TrackerConfig",
    {
        "uuid": str,
        "project": str,
        "workitem-types": cabc.Sequence[WorkitemTypeConfig],
        "title": t.Optional[str],
        "space": t.Optional[str],
        "external-id": t.Optional[str],
    },
)


class ModelConfig(te.TypedDict):
    path: str


class Config(te.TypedDict):
    modules: cabc.Sequence[TrackerConfig]
    model: ModelConfig


class InvalidTrackerConfig(Exception):
    """Raised when the given config is missing a non-optional key."""


class WorkItem(te.TypedDict, total=False):
    id: te.Required[int]
    long_name: str
    text: str
    type: str
    attributes: cabc.Mapping[str, t.Any]
    children: cabc.Sequence[WorkItem]


class TrackerSnapshot(te.TypedDict):
    id: int
    version: int | float
    data_types: cabc.Mapping[str, cabc.Sequence[str]]
    requirement_types: cabc.Mapping[str, cabc.Sequence[cabc.Mapping[str, str]]]
    items: cabc.Sequence[WorkItem]


class AttributeDefinition(te.TypedDict):
    type: str


class RequirementType(t.TypedDict):
    long_name: str
    attributes: cabc.Mapping[
        str, t.Union[AttributeDefinition, EnumAttributeDefinition]
    ]


class EnumAttributeDefinition(AttributeDefinition, total=False):
    values: list[str]
    multi_values: bool


class InvalidFieldValue(Exception):
    """Raised if a value isn't matching the defined type or options."""
