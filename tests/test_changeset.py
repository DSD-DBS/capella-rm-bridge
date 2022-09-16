# SPDX-FileCopyrightText: Copyright DB Netz AG and the rm-bridge contributors
# SPDX-License-Identifier: Apache-2.0

"""Test functionality for the RM Bridge model-modifier.

The main functions tested are ChangeSet calculation, application and
triggering of the t4c model update via git2t4c merge execution call.
"""
# pylint: disable=redefined-outer-name
from __future__ import annotations

import collections.abc as cabc
import copy
import datetime
import typing as t

import capellambse
import pytest
import yaml
from capellambse import ymol
from capellambse.extensions import reqif

from rm_bridge import types
from rm_bridge.model_modifier.changeset import calculate_change_set, change

from .conftest import TEST_CONFIG, TEST_DATA_PATH

TEST_SNAPSHOT: list[types.TrackerSnapshot] = yaml.safe_load(
    (TEST_DATA_PATH / "snapshot.yaml").read_text(encoding="utf-8")
)
TEST_SNAPSHOT_1 = yaml.safe_load(
    (TEST_DATA_PATH / "snapshot1.yaml").read_text(encoding="utf-8")
)
TEST_SNAPSHOT_2 = yaml.safe_load(
    (TEST_DATA_PATH / "snapshot2.yaml").read_text(encoding="utf-8")
)
TEST_MODULE_CHANGE = ymol.load(TEST_DATA_PATH / "changesets" / "create.yaml")
TEST_MODULE_CHANGE_1 = ymol.load(TEST_DATA_PATH / "changesets" / "mod.yaml")
TEST_MODULE_CHANGE_2 = ymol.load(TEST_DATA_PATH / "changesets" / "delete.yaml")
TEST_TRACKER_ID = "25093"
TEST_DATE = datetime.datetime(
    2022, 6, 30, 15, 7, 18, 664000, tzinfo=datetime.timezone.utc
)


class ActionsTest:
    """Base class for Test[Create|Mod|Delete]Actions."""

    tracker: cabc.Mapping[str, t.Any]
    tconfig = TEST_CONFIG["trackers"][0]

    def tracker_change(
        self,
        model: capellambse.MelodyModel,
        tracker: cabc.Mapping[str, t.Any] | None = None,
    ) -> change.TrackerChange:
        return change.TrackerChange(
            tracker or self.tracker, model, self.tconfig
        )


class TestCreateActions(ActionsTest):
    """UnitTests for all methods requesting creations."""

    tracker = TEST_SNAPSHOT[0]
    titem = tracker["items"][0]
    tracker_change_creations = TEST_MODULE_CHANGE[0]["create"]

    ATTR_DEF_CHANGE = tracker_change_creations["requirement_types_folders"][0]
    REQ_CHANGE = tracker_change_creations["folders"][0]

    def test_create_attribute_definition_actions(
        self, clean_model: capellambse.MelodyModel
    ) -> None:
        """Test producing ``CreateAction`` for a RequirementsTypeFolder."""
        tchange = self.tracker_change(clean_model)
        actions = tchange.create_requirement_types_folder_action()

        assert actions == self.ATTR_DEF_CHANGE

    def test_create_requirements_actions(
        self, clean_model: capellambse.MelodyModel
    ) -> None:
        """Test producing ``CreateAction``s for Requirements."""
        tchange = self.tracker_change(clean_model)
        identifiers = (
            "RequirementType-Requirement--3",
            "AttributeDefinition-Capella ID",
            "AttributeDefinitionEnumeration-Type",
            "AttributeDefinition-Submitted at",
        )
        for id in identifiers:
            promise = ymol.Promise(id)
            tchange.promises[promise.identifier] = promise

        actions = tchange.create_requirements_actions(self.titem)

        assert actions == self.REQ_CHANGE

    def test_create_requirements_attributes_with_none_values(
        self, clean_model: capellambse.MelodyModel
    ) -> None:
        """Test that default values are chosen instead of faulty values."""
        tracker = copy.deepcopy(self.tracker)
        titem = tracker["items"][0]
        titem["attributes"]["Type"] = []
        first_child = titem["children"][0]
        first_child["attributes"]["Capella ID"] = None
        first_child["attributes"]["Type"] = None
        first_child["attributes"]["Submitted at"] = None
        tchange = self.tracker_change(clean_model, tracker)
        identifiers = (
            "RequirementType-Requirement--3",
            "AttributeDefinition-Capella ID",
            "AttributeDefinitionEnumeration-Type",
            "AttributeDefinition-Submitted at",
        )
        for id in identifiers:
            promise = ymol.Promise(id)
            tchange.promises[promise.identifier] = promise

        actions = tchange.create_requirements_actions(titem)
        req_actions = actions["requirements"][0]["attributes"]  # type: ignore[typeddict-item]

        assert req_actions[0]["value"] == ""
        assert req_actions[1]["values"] == ["Unset"]
        assert req_actions[2]["value"] is None

    @pytest.mark.integtest
    def test_calculate_change_sets(
        self, clean_model: capellambse.MelodyModel
    ) -> None:
        """Test ChangeSet on clean model for first migration run."""
        change_set = calculate_change_set(
            clean_model, TEST_CONFIG, TEST_SNAPSHOT
        )

        assert change_set == TEST_MODULE_CHANGE


@pytest.mark.skip("Not ready yet")
class TestModActions(ActionsTest):
    """Tests all methods that request modifications."""

    tracker = TEST_SNAPSHOT_1[0]
    titem = tracker["items"][0]

    ENUM_DATA_TYPE_CHANGE = TEST_MODULE_CHANGE_1[0]
    NAME_CHANGE = TEST_MODULE_CHANGE_1[1]
    ATTR_DEF_CHANGE = TEST_MODULE_CHANGE_1[2]

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

    def test_mod_requirements_attributes_with_none_values(
        self, migration_model: capellambse.MelodyModel
    ) -> None:
        """Test that faulty values don't produce a ModAction if default."""
        tracker = copy.deepcopy(self.tracker)
        titem = tracker["items"][0]
        titem["attributes"]["Type"] = []
        first_child = titem["children"][0]
        first_child["attributes"]["Capella ID"] = None
        first_child["attributes"]["Type"] = None
        first_child["attributes"]["Submitted at"] = None
        tchange = self.tracker_change(migration_model, tracker)
        reqfolder = tchange.reqfinder.find_requirement_by_identifier(
            self.titem["id"]
        )
        assert isinstance(reqfolder, reqif.RequirementsFolder)

        actions = tchange.mod_requirements_actions(
            reqfolder, titem, tchange.req_module
        )
        req_actions = actions["requirements"][  # type: ignore[typeddict-item,index]
            "1cab372a-62cf-443b-b36d-77e66e5de97d"
        ]

        assert req_actions["attributes"][0]["value"] == ""
        assert req_actions["attributes"][1]["values"] == ["Unset"]
        assert req_actions["attributes"][2]["value"] is None

    @pytest.mark.integtest
    def test_calculate_change_sets(
        self, migration_model: capellambse.MelodyModel
    ) -> None:
        """Test ChangeSet on clean model for first migration run."""
        change_set = calculate_change_set(
            migration_model, TEST_CONFIG, TEST_SNAPSHOT_1
        )

        assert change_set == TEST_MODULE_CHANGE_1


@pytest.mark.skip("Not ready yet")
class TestDeleteActions(ActionsTest):
    """Test all methods that request deletions."""

    tracker = TEST_SNAPSHOT_2[0]
    titem = tracker["items"][0]

    REQ_TYPE_FOLDER_CHANGES = TEST_MODULE_CHANGE_2[:2]
    REQ_CHANGES = TEST_MODULE_CHANGE_2[2:-1]
    FOLDER_DEL = TEST_MODULE_CHANGE_2[-1]

    def test_mod_attribute_definition_actions(
        self, deletion_model: capellambse.MelodyModel
    ) -> None:
        """Test that RequirementsTypeFolderModActions are produced."""
        tchange = self.tracker_change(deletion_model)
        actions = tchange.mod_attribute_definition_actions()

        assert actions == self.REQ_TYPE_FOLDER_CHANGES

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

        assert actions == self.REQ_CHANGES

    @pytest.mark.integtest
    def test_calculate_change_sets(
        self, deletion_model: capellambse.MelodyModel
    ) -> None:
        """Test ChangeSet on clean model for first migration run."""
        change_set = calculate_change_set(
            deletion_model, TEST_CONFIG, TEST_SNAPSHOT_2
        )

        assert change_set == TEST_MODULE_CHANGE_2
