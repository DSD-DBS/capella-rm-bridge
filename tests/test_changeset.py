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
import typing as t

import capellambse
import pytest
import yaml
from capellambse import decl
from capellambse.extensions import reqif

from rm_bridge.changeset import actiontypes, calculate_change_set, change

from .conftest import TEST_CONFIG, TEST_DATA_PATH

TEST_SNAPSHOT_PATH = TEST_DATA_PATH / "snapshots"
TEST_SNAPSHOT: list[actiontypes.TrackerSnapshot] = yaml.safe_load(
    (TEST_SNAPSHOT_PATH / "snapshot.yaml").read_text(encoding="utf-8")
)
TEST_SNAPSHOT_1 = yaml.safe_load(
    (TEST_SNAPSHOT_PATH / "snapshot1.yaml").read_text(encoding="utf-8")
)
TEST_SNAPSHOT_2 = yaml.safe_load(
    (TEST_SNAPSHOT_PATH / "snapshot2.yaml").read_text(encoding="utf-8")
)
TEST_MODULE_CHANGE = decl.load(TEST_DATA_PATH / "changesets" / "create.yaml")
TEST_MODULE_CHANGE_1 = decl.load(TEST_DATA_PATH / "changesets" / "mod.yaml")
TEST_MODULE_CHANGE_2 = decl.load(TEST_DATA_PATH / "changesets" / "delete.yaml")


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
    tracker_change_creations = TEST_MODULE_CHANGE[0]["extend"]

    ATTR_DEF_CHANGE = tracker_change_creations["requirement_types_folders"][0]
    REQ_CHANGE = tracker_change_creations["folders"][0]

    def test_create_attribute_definition_actions(
        self, clean_model: capellambse.MelodyModel
    ) -> None:
        """Test producing ``CreateAction`` for a RequirementsTypeFolder."""
        tchange = self.tracker_change(clean_model)
        actions = tchange.create_requirement_types_folder_action()
        attr_def_action = actions["extend"]["requirement_types_folders"][0]

        assert attr_def_action == self.ATTR_DEF_CHANGE

    def test_create_requirements_actions(
        self, clean_model: capellambse.MelodyModel
    ) -> None:
        """Test producing ``CreateAction``s for Requirements."""
        tchange = self.tracker_change(clean_model)

        action = next(tchange.create_requirements_actions(self.titem))

        assert action == self.REQ_CHANGE

    @pytest.mark.parametrize(
        "attr,faulty_value",
        [
            ("Type", ["Not an option"]),
            ("Type", None),
            ("Capella ID", None),
            ("Submitted at", 1),
        ],
    )
    def test_faulty_attribute_values_raise_InvalidFieldValue(
        self,
        clean_model: capellambse.MelodyModel,
        attr: str,
        faulty_value: actiontypes.Primitive,
    ) -> None:
        """Test raising an ``InvalidFieldValue`` on faulty field data."""
        tracker = copy.deepcopy(self.tracker)
        titem = tracker["items"][0]
        first_child = titem["children"][0]
        first_child["attributes"][attr] = faulty_value
        tchange = self.tracker_change(clean_model, tracker)

        with pytest.raises(actiontypes.InvalidFieldValue):
            next(tchange.create_requirements_actions(titem))

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

    ENUM_DATA_TYPE_CHANGE = TEST_MODULE_CHANGE_1[0]
    ENUM_VALUE_CHANGE = TEST_MODULE_CHANGE_1[1]
    ATTR_DEF_CHANGE = TEST_MODULE_CHANGE_1[2]
    REQ_CHANGE, REQ_CHANGE1 = TEST_MODULE_CHANGE_1[3:5]

    def test_mod_attribute_definition_actions(
        self, migration_model: capellambse.MelodyModel
    ) -> None:
        """Test that RequirementsTypeFolderModActions are produced."""
        tchange = self.tracker_change(migration_model)
        attr_def_actions = next(
            tchange.yield_mod_attribute_definition_actions()
        )
        reqtype_actions = next(tchange.yield_reqtype_mod_actions())
        actions = [attr_def_actions, reqtype_actions]

        assert actions == [self.ENUM_DATA_TYPE_CHANGE, self.ATTR_DEF_CHANGE]

    def test_mod_requirements_actions(
        self, migration_model: capellambse.MelodyModel
    ) -> None:
        """Test that RequirementsModActions are produced."""
        tchange = self.tracker_change(migration_model)
        reqfolder = tchange.reqfinder.work_item_by_identifier(self.titem["id"])
        req_change = {
            **self.REQ_CHANGE,
            "delete": {
                "folders": [
                    decl.UUIDReference("04574907-fa9f-423a-b9fd-fc22dc975dc8")
                ]
            },
        }
        assert isinstance(reqfolder, reqif.RequirementsFolder)

        actions = tchange.yield_mod_requirements_actions(reqfolder, self.titem)

        assert list(actions) == [req_change, self.REQ_CHANGE1]

    @pytest.mark.parametrize(
        "attr,faulty_value",
        [
            ("Type", ["Not an option"]),
            ("Type", None),
            ("Capella ID", None),
            ("Submitted at", 1),
        ],
    )
    def test_faulty_attribute_values_raise_InvalidFieldValue(
        self,
        migration_model: capellambse.MelodyModel,
        attr: str,
        faulty_value: actiontypes.Primitive,
    ) -> None:
        """Test raising an ``InvalidFieldValue`` on faulty field data."""
        tracker = copy.deepcopy(self.tracker)
        titem = tracker["items"][0]
        first_child = titem["children"][0]
        first_child["attributes"][attr] = faulty_value
        tchange = self.tracker_change(migration_model, tracker)
        reqfolder = tchange.reqfinder.work_item_by_identifier(self.titem["id"])
        assert isinstance(reqfolder, reqif.RequirementsFolder)
        # Run these to populate promises lookup for new Release attribute
        next(tchange.yield_mod_attribute_definition_actions())
        next(tchange.yield_reqtype_mod_actions())

        with pytest.raises(actiontypes.InvalidFieldValue):
            list(tchange.yield_mod_requirements_actions(reqfolder, titem))

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

    REQ_TYPE_FOLDER_CHANGES = TEST_MODULE_CHANGE_2[:2]
    REQ_CHANGES = TEST_MODULE_CHANGE_2[2:-1]
    FOLDER_DEL = TEST_MODULE_CHANGE_2[-1]

    def test_mod_attribute_definition_actions(
        self, deletion_model: capellambse.MelodyModel
    ) -> None:
        """Test that RequirementsTypeFolderModActions are produced."""
        tchange = self.tracker_change(deletion_model)
        attr_def_actions = next(
            tchange.yield_mod_attribute_definition_actions()
        )
        reqtype_actions = next(tchange.yield_reqtype_mod_actions())
        actions = [attr_def_actions, reqtype_actions]

        assert actions == self.REQ_TYPE_FOLDER_CHANGES

    def test_mod_requirements_actions(
        self, deletion_model: capellambse.MelodyModel
    ) -> None:
        """Test that RequirementsModActions are produced."""
        tchange = self.tracker_change(deletion_model)
        reqfolder = tchange.reqfinder.work_item_by_identifier(self.titem["id"])
        assert isinstance(reqfolder, reqif.RequirementsFolder)

        actions = tchange.yield_mod_requirements_actions(reqfolder, self.titem)

        assert list(actions) == self.REQ_CHANGES

    @pytest.mark.integtest
    def test_calculate_change_sets(
        self, deletion_model: capellambse.MelodyModel
    ) -> None:
        """Test ChangeSet on clean model for first migration run."""
        change_set = calculate_change_set(
            deletion_model, TEST_CONFIG, TEST_SNAPSHOT_2
        )

        assert change_set == TEST_MODULE_CHANGE_2
