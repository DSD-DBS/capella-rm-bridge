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
        "external-id": str,
        "capella-uuid": str,
        "project": str,
        "workitem-types": cabc.Sequence[WorkitemTypeConfig],
    },
)


class ModelConfig(te.TypedDict):
    path: str


class Config(te.TypedDict):
    trackers: cabc.Sequence[TrackerConfig]
    model: ModelConfig


class WorkItem(te.TypedDict, total=False):
    id: te.Required[int]
    long_name: str
    text: str
    type: str
    attributes: cabc.Mapping[str, t.Any]
    # <https://github.com/python/mypy/issues/731>
    children: cabc.Sequence[WorkItem]  # type: ignore[misc]


class TrackerSnapshot(te.TypedDict):
    id: int
    version: int | float
    data_types: cabc.Mapping[str, cabc.Sequence[str]]
    types: cabc.Mapping[str, cabc.Sequence[cabc.Mapping[str, str]]]
    items: cabc.Sequence[WorkItem]


class AttributeDefinition(te.TypedDict):
    type: str


class EnumAttributeDefinition(AttributeDefinition):
    data_type: str
    multi_values: te.NotRequired[bool]


class RequirementType(t.TypedDict):
    long_name: str
    attributes: cabc.Mapping[
        str, t.Union[AttributeDefinition, EnumAttributeDefinition]
    ]
