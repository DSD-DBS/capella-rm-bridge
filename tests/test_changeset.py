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
TEST_DATE = datetime.datetime(
    2022, 6, 30, 15, 7, 18, 664000, tzinfo=datetime.timezone.utc
)


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
