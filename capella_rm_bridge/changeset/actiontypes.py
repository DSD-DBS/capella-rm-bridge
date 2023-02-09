# SPDX-FileCopyrightText: Copyright DB Netz AG and the capella-rm-bridge contributors
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
        "capella-uuid": str,
        "workitem-types": cabc.Sequence[WorkitemTypeConfig],
        "id": str,
    },
)


class Config(te.TypedDict):
    modules: cabc.Sequence[TrackerConfig]
    trackers: cabc.Sequence[TrackerConfig]


class InvalidTrackerConfig(Exception):
    """Raised when the given config is missing a non-optional key."""


class WorkItem(te.TypedDict, total=False):
    id: te.Required[int]
    long_name: str
    text: str
    type: str
    attributes: cabc.Mapping[str, t.Any]
    children: cabc.Sequence[WorkItem]


class MetaData(te.TypedDict):
    tool: str
    revision: str
    connector: str


class TrackerSnapshot(te.TypedDict):
    id: int
    version: int | float
    data_types: cabc.Mapping[str, cabc.Sequence[str]]
    requirement_types: cabc.Mapping[str, cabc.Sequence[cabc.Mapping[str, str]]]
    items: cabc.Sequence[WorkItem]


class Snapshot(te.TypedDict):
    metadata: MetaData
    modules: cabc.Sequence[TrackerSnapshot]


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


class InvalidSnapshotModule(Exception):
    """Raised if the module snapshot is invalid."""


class InvalidWorkItemType(Exception):
    """Raised if the type isn't matching any of the defined types."""


class InvalidWorkItem(Exception):
    """Raised if the work item is faulty, e.g. missing a work-item-type."""


class InvalidFieldValue(Exception):
    """Raised if a value isn't matching the defined type or options."""


class InvalidAttributeDefinition(Exception):
    """Raised if an AttributeDefinition's data-type isn't found."""
