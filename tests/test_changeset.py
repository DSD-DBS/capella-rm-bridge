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
import typing as t

import capellambse
import pytest
import yaml
from capellambse.extensions import reqif

from rm_bridge import types
from rm_bridge.model_modifier.changeset import calculate_change_set, change

from .conftest import TEST_CONFIG, TEST_DATA_PATH

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
TEST_MODULE_CHANGE = yaml.load(
    (TEST_DATA_PATH / "changesets" / "create.yaml").read_text(
        encoding="utf-8"
    ),
    Loader=yaml.Loader,
)
TEST_MODULE_CHANGE_1 = yaml.load(
    (TEST_DATA_PATH / "changesets" / "mod.yaml").read_text(encoding="utf-8"),
    Loader=yaml.Loader,
)
TEST_MODULE_CHANGE_2 = yaml.load(
    (TEST_DATA_PATH / "changesets" / "delete.yaml").read_text(
        encoding="utf-8"
    ),
    Loader=yaml.Loader,
)
TEST_TRACKER_ID = "25093"
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

    ATTR_DEF_CHANGE, REQ_CHANGE = TEST_MODULE_CHANGE[TEST_TRACKER_ID]

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

        assert change_set == TEST_MODULE_CHANGE


class TestModActions(ActionsTest):
    """Tests all methods that request modifications."""

    tracker = TEST_SNAPSHOT_1[0]
    titem = tracker["items"][0]

    ATTR_DEF_CHANGE, REQ_CHANGE, FOLDER_CHANGE = TEST_MODULE_CHANGE_1[
        TEST_TRACKER_ID
    ]

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

        assert change_set == TEST_MODULE_CHANGE_1


class TestDeleteActions(ActionsTest):
    """Test all methods that request deletions."""

    tracker = TEST_SNAPSHOT_2[0]
    titem = tracker["items"][0]

    ATTR_DEF_CHANGE, REQ_CHANGE, FOLDER_DEL = TEST_MODULE_CHANGE_2[
        TEST_TRACKER_ID
    ]

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

        assert change_set == TEST_MODULE_CHANGE_2
