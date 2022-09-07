# SPDX-FileCopyrightText: Copyright DB Netz AG and the rm-bridge contributors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import collections.abc as cabc
import datetime
import enum
import typing as t

import typing_extensions as te
from capellambse.extensions import reqif

Primitive = t.Union[int, float, str, list[str], bool, datetime.datetime]


class ActionType(enum.Enum):
    CREATE = enum.auto()
    MOD = enum.auto()
    DELETE = enum.auto()


class WorkItem(te.TypedDict, total=False):
    id: te.Required[int]
    long_name: str
    text: str
    attributes: dict[str, t.Any]
    # <https://github.com/python/mypy/issues/731>
    children: list[WorkItem]  # type: ignore[misc]


class AttributeDefinition(te.TypedDict):
    type: str


class EnumAttributeDefinition(AttributeDefinition, total=False):
    values: list[str]
    multi_values: bool


class Action(te.TypedDict):
    """Base for Create/Mod and Delete Actions."""

    _type: ActionType


class CreateAction(Action, total=False):
    """Action for Element creation with the following attributes."""

    long_name: te.Required[str]
    cls: te.Required[type[reqif.ReqIFElement]]
    identifier: str  # Only for Tracker/ReqModule & Work items/Reqs
    type: str  # Only for Tracker/ReqModule right now
    text: str


class AttributeValueCreateAction(CreateAction):
    definition: str
    value: Primitive


class EnumAttributeValueCreateAction(CreateAction):
    definition: str
    values: list[str]


class RequirementCreateAction(CreateAction):
    attributes: list[
        AttributeValueCreateAction | EnumAttributeValueCreateAction
    ]


class RequirementFolderCreateAction(CreateAction, total=False):
    attributes: list[
        AttributeValueCreateAction | EnumAttributeValueCreateAction
    ]
    folders: list[RequirementFolderCreateAction]  # type: ignore[misc]
    requirements: list[RequirementCreateAction]


class AttributeDefinitionCreateAction(CreateAction):
    pass


class EnumAttributeDefinitionCreateAction(CreateAction):
    data_type: str
    multi_valued: te.NotRequired[bool]


class RequirementTypesFolderCreateAction(CreateAction, total=False):
    parent: te.Required[str]
    data_type_definitions: list[EnumerationDataTypeDefinitionCreateAction]
    requirement_types: list[RequirementTypeCreateAction]


class EnumerationDataTypeDefinitionCreateAction(CreateAction):
    values: list[str]


class RequirementTypeCreateAction(CreateAction):
    attribute_definitions: list[CreateAction | EnumAttributeDefinition]


class ModAction(Action, total=False):
    """Action for Modification of ModelElements"""

    uuid: te.Required[str]
    long_name: str


class AttributeValueModAction(ModAction, total=False):
    value: Primitive


class EnumAttributeValueModAction(ModAction, total=False):
    values: list[str]


class RequirementFolderModAction(ModAction, total=False):
    attributes: list[
        AttributeValueCreateAction
        | EnumAttributeValueCreateAction
        | AttributeValueModAction
        | EnumAttributeValueModAction
    ]
    folders: list[RequirementFolderCreateAction | RequirementFolderModAction]  # type: ignore[misc]
    requirements: list[RequirementCreateAction | RequirementModAction]


class RequirementModAction(ModAction, total=False):
    attributes: list[
        AttributeValueCreateAction
        | EnumAttributeValueCreateAction
        | AttributeValueModAction
        | EnumAttributeValueModAction
    ]


class RequirementTypesFolderModAction(ModAction, total=False):
    data_type_definitions: list[
        EnumerationDataTypeDefinitionCreateAction
        | EnumerationDataTypeDefinitionModAction
    ]
    requirement_types: list[
        RequirementTypeCreateAction | RequirementTypeModAction
    ]


class EnumerationDataTypeDefinitionModAction(ModAction, total=False):
    values: list[str]


class RequirementTypeModAction(ModAction, total=False):
    attribute_definitions: list[
        AttributeDefinitionNonDeleteAction | DeleteAction
    ]


class AttributeDefinitionModAction(ModAction):
    """Action for Modification of AttributeDefinitions."""


class EnumAttributeDefinitionModAction(ModAction, total=False):
    data_type: str
    multi_valued: bool


AttributeDefinitionNonDeleteAction = t.Union[
    AttributeDefinitionCreateAction,
    EnumAttributeDefinitionCreateAction,
    AttributeDefinitionModAction,
    EnumAttributeDefinitionModAction,
]
AttributeValueNonDeleteActions = t.Union[
    AttributeValueModAction,
    EnumAttributeValueModAction,
    AttributeValueCreateAction,
    EnumAttributeValueCreateAction,
]


class DeleteAction(Action):
    """Action for Deletion of ModelElements"""

    uuid: str


class MoveAction(Action):
    """Action for moving a ModelElement to a different location."""
