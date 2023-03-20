# SPDX-FileCopyrightText: Copyright DB Netz AG and the capella-rm-bridge contributors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import collections.abc as cabc
import datetime
import typing as t

import typing_extensions as te
from capellambse import decl

Primitive = t.Union[
    int,
    float,
    str,
    decl.UUIDReference | decl.Promise,
    list[str | decl.UUIDReference | decl.Promise],
    bool,
    datetime.datetime,
]
"""Type alias for primitive values."""


class WorkitemTypeConfig(te.TypedDict):
    """A configeration for workitem types."""

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
"""A configuration of an RM module."""


class Config(te.TypedDict):
    """A configuration of an RM synchronization plan."""

    modules: cabc.Sequence[TrackerConfig]
    trackers: cabc.Sequence[TrackerConfig]


class InvalidTrackerConfig(Exception):
    """Raised when the given config is missing a non-optional key."""


class WorkItem(te.TypedDict, total=False):
    """A workitem from the snapshot."""

    id: te.Required[str]
    long_name: str
    text: str
    type: str
    attributes: cabc.Mapping[str, t.Any]
    children: cabc.Sequence[WorkItem]


class DataType(te.TypedDict):
    """A data_type from the snapshot."""

    long_name: str
    values: list[DataTypeValue]


class DataTypeValue(te.TypedDict):
    """An enum value/option from the snapshot."""

    id: str
    long_name: str


class MetaData(te.TypedDict):
    """Metadata of a snapshot."""

    tool: str
    revision: str
    connector: str


class TrackerSnapshot(te.TypedDict):
    """A snapshot of a whole module from the RM tool."""

    id: int
    version: int | float
    data_types: cabc.Mapping[str, cabc.Sequence[str]]
    requirement_types: cabc.Mapping[str, cabc.Sequence[cabc.Mapping[str, str]]]
    items: cabc.Sequence[WorkItem]


class Snapshot(te.TypedDict):
    """A whole snapshot from the RM tool that may have multiple modules."""

    metadata: MetaData
    modules: cabc.Sequence[TrackerSnapshot]


class RequirementType(t.TypedDict):
    """A requirement type from the snapshot."""

    long_name: str
    attributes: cabc.Mapping[
        str, t.Union[AttributeDefinition, EnumAttributeDefinition]
    ]


class AttributeDefinition(te.TypedDict):
    """An attribute definition from the snapshot."""

    long_name: str
    type: str


class EnumAttributeDefinition(AttributeDefinition, total=False):
    """An attribute definition with `type == enum` from the snapshot."""

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
