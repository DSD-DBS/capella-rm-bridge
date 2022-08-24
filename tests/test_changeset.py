# SPDX-FileCopyrightText: Copyright DB Netz AG and the rm-bridge contributors
# SPDX-License-Identifier: Apache-2.0

"""Test functionality for the RM Bridge model-modifier.

The main functions tested are ChangeSet calculation, application and
triggering of the t4c model update via git2t4c merge execution call.
"""
# pylint: disable=redefined-outer-name
from __future__ import annotations

import collections.abc as cabc
import datetime
import pathlib
import typing as t

import capellambse
import pytest
import yaml
from capellambse.extensions import reqif

from rm_bridge import load, types
from rm_bridge.model_modifier.changeset import actiontypes as act
from rm_bridge.model_modifier.changeset import calculate_change_set, change

TEST_DATA_PATH = pathlib.Path(__file__).parent / "data"
TEST_CONFIG = load.load_yaml(TEST_DATA_PATH / "config.yaml")
TEST_MODEL_PATH = TEST_DATA_PATH / TEST_CONFIG["model"]["path"]
TEST_SNAPSHOT: list[types.TrackerSnapshot] = yaml.safe_load(
    (TEST_DATA_PATH / "snapshot.yaml").read_text(encoding="utf-8")
)
TEST_SNAPSHOT_1 = yaml.safe_load(
    (TEST_DATA_PATH / "snapshot1.yaml").read_text(encoding="utf-8")
)
TEST_SNAPSHOT_2 = yaml.safe_load(
    (TEST_DATA_PATH / "snapshot2.yaml").read_text(encoding="utf-8")
)
TEST_REQ_MODULE_UUID = "3be8d0fc-c693-4b9b-8fa1-d59a9eec6ea4"
TEST_DATE = datetime.datetime(
    2022, 6, 30, 15, 7, 18, 664000, tzinfo=datetime.timezone.utc
)
TEST_UUID_PREFIX = "00000000-0000-0000-0000-00000000000"


@pytest.fixture
def migration_model() -> capellambse.MelodyModel:
    return capellambse.MelodyModel(path=TEST_MODEL_PATH)


@pytest.fixture
def clean_model() -> capellambse.MelodyModel:
    model = capellambse.MelodyModel(path=TEST_MODEL_PATH)
    reqmodule = model.by_uuid(TEST_REQ_MODULE_UUID)
    del reqmodule.requirement_types_folders[0]
    del reqmodule.folders[0]
    return model


@pytest.fixture
def deletion_model(
    migration_model: capellambse.MelodyModel,
) -> capellambse.MelodyModel:
    dtdef = migration_model.by_uuid("f4b62994-37ac-45d6-add7-d320890e2969")
    dtdef.values[-1].long_name = "Non-Functional"
    reqtfolder = migration_model.by_uuid(
        "487eca4d-8e98-4598-8ec0-4cdbdcbebd03"
    )
    enum_dtdef = reqtfolder.data_type_definitions.create(
        reqif.XT_REQ_TYPE_ENUM,
        long_name="Release",
        values=["Rel. 1", "Rel. 2"],
        uuid=f"{TEST_UUID_PREFIX}1",
    )
    reqtype = migration_model.by_uuid("e941a947-54ac-48e4-a383-af0b6994076d")
    enum_def = reqtype.attribute_definitions.create(
        "AttributeDefinitionEnumeration",
        long_name="Release",
        data_type=enum_dtdef,
        multi_valued=True,
        uuid=f"{TEST_UUID_PREFIX}2",
    )
    definition = reqtype.attribute_definitions.create(
        reqif.XT_REQ_TYPE_ATTR_DEF,
        long_name="Test after migration",
        uuid=f"{TEST_UUID_PREFIX}3",
    )
    reqfolder = migration_model.by_uuid("8a814f64-70d1-4fe1-a648-54c83c03d05b")
    reqfolder.long_name = "Non-Functional Requirements"
    reqfolder.text = "<p>Changed Test Description</p>"
    iddef = reqtype.attribute_definitions.by_long_name(
        "Capella ID", single=True
    )
    reqfolder.attributes.create(
        "String", value="RF-NFNC-00001", definition=iddef
    )
    reqfolder.attributes.create(
        "Enum",
        values=enum_dtdef.values,
        definition=enum_def,
        uuid=f"{TEST_UUID_PREFIX}4",
    )
    attr = migration_model.by_uuid("8848878e-faf3-4b9a-b5fb-b99df5faf588")
    attr.value = "R-NFNC-00001"
    req = migration_model.by_uuid("1cab372a-62cf-443b-b36d-77e66e5de97d")
    req.attributes.create(
        "String",
        definition=definition,
        value="New",
        uuid=f"{TEST_UUID_PREFIX}5",
    )
    assert isinstance(reqmodule := reqfolder.parent, reqif.RequirementsModule)
    subfolder = reqmodule.folders.create(
        identifier="5442",
        long_name="Kinds",
        type=reqtype,
        uuid=f"{TEST_UUID_PREFIX}6",
    )
    del reqfolder.folders[0]
    subf_req = subfolder.requirements.create(
        identifier="5443", long_name="Kind Requirement", type=reqtype
    )
    subf_req.attributes.create("String", value="R-FNC-00002", definition=iddef)
    subf_req.attributes.create(
        "Enum", values=dtdef.values[:1], definition=dtdef
    )
    return migration_model


class ActionsTest:
    """Base class for Test[Create|Mod|Delete]Actions."""

    tracker: cabc.Mapping[str, t.Any]
    tconfig = TEST_CONFIG["trackers"][0]

    def tracker_change(
        self, model: capellambse.MelodyModel
    ) -> change.TrackerChange:
        return change.TrackerChange(self.tracker, model, self.tconfig)


class TestCreateActions(ActionsTest):
    """Tests all methods for request creations."""

    tracker = TEST_SNAPSHOT[0]
    titem = tracker["items"][0]

    ATTR_DEF_CHANGE = {
        "_type": act.ActionType.CREATE,
        "parent": TEST_REQ_MODULE_UUID,
        "identifier": -2,
        "long_name": "Types",
        "cls": reqif.RequirementsTypesFolder,
        "data_type_definitions": [
            {
                "_type": act.ActionType.CREATE,
                "long_name": "Type",
                "cls": reqif.EnumDataTypeDefinition,
                "values": ["Unset", "Folder", "Functional"],
            }
        ],
        "requirement_types": [
            {
                "_type": act.ActionType.CREATE,
                "identifier": -3,
                "long_name": "Requirement",
                "cls": reqif.RequirementType,
                "attribute_definitions": [
                    {
                        "_type": act.ActionType.CREATE,
                        "long_name": "Capella ID",
                        "cls": reqif.AttributeDefinition,
                    },
                    {
                        "_type": act.ActionType.CREATE,
                        "long_name": "Type",
                        "cls": reqif.AttributeDefinitionEnumeration,
                        "multi_valued": False,
                        "data_type": "Type",
                    },
                    {
                        "_type": act.ActionType.CREATE,
                        "long_name": "Submitted at",
                        "cls": reqif.AttributeDefinition,
                    },
                ],
            }
        ],
    }
    REQ_CHANGE = {
        "_type": act.ActionType.CREATE,
        "identifier": "5440",
        "long_name": "Functional Requirements",
        "cls": reqif.RequirementsFolder,
        "type": "Requirement",
        "text": "<p>Test Description</p>",
        "attributes": [],
        "requirements": [
            {
                "_type": act.ActionType.CREATE,
                "identifier": "5441",
                "long_name": "Function Requirement",
                "cls": reqif.Requirement,
                "text": "...",
                "type": "Requirement",
                "attributes": [
                    {
                        "_type": act.ActionType.CREATE,
                        "cls": reqif.StringValueAttribute,
                        "value": "R-FNC-00001",
                        "definition": "Capella ID",
                    },
                    {
                        "_type": act.ActionType.CREATE,
                        "cls": reqif.EnumerationValueAttribute,
                        "values": ["Functional"],
                        "definition": "Type",
                    },
                    {
                        "_type": act.ActionType.CREATE,
                        "cls": reqif.DateValueAttribute,
                        "value": TEST_DATE,
                        "definition": "Submitted at",
                    },
                ],
            }
        ],
        "folders": [
            {
                "_type": act.ActionType.CREATE,
                "identifier": "5442",
                "long_name": "Kinds",
                "cls": reqif.RequirementsFolder,
                "text": "",
                "type": "Requirement",
                "attributes": [],
                "folders": [],
                "requirements": [
                    {
                        "_type": act.ActionType.CREATE,
                        "identifier": "5443",
                        "long_name": "Kind Requirement",
                        "cls": reqif.Requirement,
                        "text": "",
                        "type": "Requirement",
                        "attributes": [
                            {
                                "_type": act.ActionType.CREATE,
                                "cls": reqif.StringValueAttribute,
                                "value": "R-FNC-00002",
                                "definition": "Capella ID",
                            },
                            {
                                "_type": act.ActionType.CREATE,
                                "cls": reqif.EnumerationValueAttribute,
                                "values": ["Unset"],
                                "definition": "Type",
                            },
                        ],
                    }
                ],
            }
        ],
    }
    MODULE_CHANGE = {"25093": [ATTR_DEF_CHANGE, REQ_CHANGE]}

    def test_create_attribute_definition_actions(
        self, clean_model: capellambse.MelodyModel
    ) -> None:
        """Test that RequirementsTypeFolderCreateActions are produced."""
        tchange = self.tracker_change(clean_model)
        actions = tchange.create_attribute_definition_actions()

        assert actions == self.ATTR_DEF_CHANGE

    def test_create_requirements_actions(
        self, clean_model: capellambse.MelodyModel
    ) -> None:
        """Test that RequirementsCreateActions are produced."""
        tchange = self.tracker_change(clean_model)
        actions = tchange.create_requirements_actions(self.titem)

        assert actions == self.REQ_CHANGE

    @pytest.mark.integtest
    def test_calculate_change_sets(
        self, clean_model: capellambse.MelodyModel
    ) -> None:
        """Test ChangeSet on clean model for first migration run."""
        change_set = calculate_change_set(
            clean_model, TEST_CONFIG, TEST_SNAPSHOT
        )

        assert change_set == self.MODULE_CHANGE


class TestModActions(ActionsTest):
    """Tests all methods that request modifications."""

    tracker = TEST_SNAPSHOT_1[0]
    titem = tracker["items"][0]

    ATTR_DEF_CHANGE = {
        "_type": act.ActionType.MOD,
        "uuid": "487eca4d-8e98-4598-8ec0-4cdbdcbebd03",
        "data_type_definitions": [
            {
                "_type": act.ActionType.MOD,
                "uuid": "f4b62994-37ac-45d6-add7-d320890e2969",
                "values": ["Unset", "Folder", "Non-Functional"],
            },
            {
                "_type": act.ActionType.CREATE,
                "long_name": "Release",
                "cls": reqif.EnumDataTypeDefinition,
                "values": ["Rel. 1", "Rel. 2"],
            },
        ],
        "requirement_types": [
            {
                "_type": act.ActionType.MOD,
                "uuid": "e941a947-54ac-48e4-a383-af0b6994076d",
                "attribute_definitions": [
                    {
                        "_type": act.ActionType.CREATE,
                        "long_name": "Release",
                        "cls": reqif.AttributeDefinitionEnumeration,
                        "multi_valued": True,
                        "data_type": "Release",
                    },
                    {
                        "_type": act.ActionType.CREATE,
                        "long_name": "Test after migration",
                        "cls": reqif.AttributeDefinition,
                    },
                ],
            }
        ],
    }
    REQ_CHANGE = {
        "_type": act.ActionType.MOD,
        "uuid": "8a814f64-70d1-4fe1-a648-54c83c03d05b",
        "long_name": "Non-Functional Requirements",
        "text": "<p>Changed Test Description</p>",
        "attributes": [
            {
                "_type": act.ActionType.CREATE,
                "cls": reqif.StringValueAttribute,
                "value": "RF-NFNC-00001",
                "definition": "Capella ID",
            },
            {
                "_type": act.ActionType.CREATE,
                "cls": reqif.EnumerationValueAttribute,
                "values": ["Rel. 1", "Rel. 2"],
                "definition": "Release",
            },
        ],
        "requirements": [
            {
                "_type": act.ActionType.MOD,
                "uuid": "1cab372a-62cf-443b-b36d-77e66e5de97d",
                "long_name": "Non-Function Requirement",
                "attributes": [
                    {
                        "_type": act.ActionType.MOD,
                        "uuid": "8848878e-faf3-4b9a-b5fb-b99df5faf588",
                        "value": "R-NFNC-00001",
                    },
                    {
                        "_type": act.ActionType.MOD,
                        "uuid": "1ebdb9ae-db83-4672-acc9-cd52ec671fab",
                        "values": ["Non-Functional"],
                    },
                    {
                        "_type": act.ActionType.CREATE,
                        "cls": reqif.StringValueAttribute,
                        "definition": "Test after migration",
                        "value": "New",
                    },
                ],
            }
        ],
        "folders": [
            {
                "_type": act.ActionType.DELETE,
                "uuid": "04574907-fa9f-423a-b9fd-fc22dc975dc8",
            }
        ],
    }
    FOLDER_CHANGE = {
        "_type": act.ActionType.MOD,
        "parent": TEST_REQ_MODULE_UUID,
        "uuid": "04574907-fa9f-423a-b9fd-fc22dc975dc8",
        "long_name": "Functional Requirements",
        "text": "<p>Brand new</p>",
        "attributes": [],
        "folders": [],
        "requirements": [
            {
                "_type": act.ActionType.MOD,
                "uuid": "94e00375-d52c-4ca6-8c06-225ab13e9afb",
                "long_name": "Function Requirement",
                "attributes": [
                    {
                        "_type": act.ActionType.MOD,
                        "uuid": "f26dc00f-5a5d-4431-8e0a-96eb319af096",
                        "value": "R-FNC-00001",
                    },
                ],
            }
        ],
    }
    MODULE_CHANGE = {"25093": [ATTR_DEF_CHANGE, REQ_CHANGE, FOLDER_CHANGE]}

    def test_mod_attribute_definition_actions(
        self, migration_model: capellambse.MelodyModel
    ) -> None:
        """Test that RequirementsTypeFolderModActions are produced."""
        tchange = self.tracker_change(migration_model)
        actions = tchange.mod_attribute_definition_actions()

        assert actions == self.ATTR_DEF_CHANGE

    def test_mod_requirements_actions(
        self, migration_model: capellambse.MelodyModel
    ) -> None:
        """Test that RequirementsModActions are produced."""
        tchange = self.tracker_change(migration_model)
        reqfolder = tchange.reqfinder.find_requirement_by_identifier(
            self.titem["id"]
        )
        assert isinstance(reqfolder, reqif.RequirementsFolder)
        actions = tchange.mod_requirements_actions(
            reqfolder, self.titem, tchange.req_module
        )

        assert actions == self.REQ_CHANGE

    @pytest.mark.integtest
    def test_calculate_change_sets(
        self, migration_model: capellambse.MelodyModel
    ) -> None:
        """Test ChangeSet on clean model for first migration run."""
        change_set = calculate_change_set(
            migration_model, TEST_CONFIG, TEST_SNAPSHOT_1
        )

        assert change_set == self.MODULE_CHANGE


class TestDeleteActions(ActionsTest):
    """Test all methods that request deletions."""

    tracker = TEST_SNAPSHOT_2[0]
    titem = tracker["items"][0]

    ATTR_DEF_CHANGE = {
        "_type": act.ActionType.MOD,
        "uuid": "487eca4d-8e98-4598-8ec0-4cdbdcbebd03",
        "data_type_definitions": [
            {
                "_type": act.ActionType.DELETE,
                "uuid": f"{TEST_UUID_PREFIX}1",
            },
        ],
        "requirement_types": [
            {
                "_type": act.ActionType.MOD,
                "uuid": "e941a947-54ac-48e4-a383-af0b6994076d",
                "attribute_definitions": [
                    {
                        "_type": act.ActionType.DELETE,
                        "uuid": f"{TEST_UUID_PREFIX}2",
                    },
                    {
                        "_type": act.ActionType.DELETE,
                        "uuid": f"{TEST_UUID_PREFIX}3",
                    },
                ],
            }
        ],
    }
    REQ_CHANGE = {
        "_type": act.ActionType.MOD,
        "uuid": "8a814f64-70d1-4fe1-a648-54c83c03d05b",
        "attributes": [
            {"_type": act.ActionType.DELETE, "uuid": f"{TEST_UUID_PREFIX}4"},
        ],
        "requirements": [
            {
                "_type": act.ActionType.MOD,
                "uuid": "1cab372a-62cf-443b-b36d-77e66e5de97d",
                "long_name": "Non-Function Requirement",
                "attributes": [
                    {
                        "_type": act.ActionType.DELETE,
                        "uuid": f"{TEST_UUID_PREFIX}5",
                    },
                ],
            }
        ],
        "folders": [],
    }
    FOLDER_DEL = {
        "_type": act.ActionType.DELETE,
        "uuid": f"{TEST_UUID_PREFIX}6",
    }
    MODULE_CHANGE = {"25093": [ATTR_DEF_CHANGE, REQ_CHANGE, FOLDER_DEL]}

    def test_mod_attribute_definition_actions(
        self, deletion_model: capellambse.MelodyModel
    ) -> None:
        """Test that RequirementsTypeFolderModActions are produced."""
        tchange = self.tracker_change(deletion_model)
        actions = tchange.mod_attribute_definition_actions()

        assert actions == self.ATTR_DEF_CHANGE

    def test_mod_requirements_actions(
        self, deletion_model: capellambse.MelodyModel
    ) -> None:
        """Test that RequirementsModActions are produced."""
        tchange = self.tracker_change(deletion_model)
        reqfolder = tchange.reqfinder.find_requirement_by_identifier(
            self.titem["id"]
        )
        assert isinstance(reqfolder, reqif.RequirementsFolder)
        actions = tchange.mod_requirements_actions(
            reqfolder, self.titem, tchange.req_module
        )

        assert actions == self.REQ_CHANGE

    @pytest.mark.integtest
    def test_calculate_change_sets(
        self, deletion_model: capellambse.MelodyModel
    ) -> None:
        """Test ChangeSet on clean model for first migration run."""
        change_set = calculate_change_set(
            deletion_model, TEST_CONFIG, TEST_SNAPSHOT_2
        )

        assert change_set == self.MODULE_CHANGE
