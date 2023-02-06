# SPDX-FileCopyrightText: Copyright DB Netz AG and the capella-rm-bridge contributors
# SPDX-License-Identifier: Apache-2.0

"""Test functionality for the RM Bridge model-modifier.

The main functions tested are ChangeSet calculation, application and
triggering of the t4c model update via git2t4c merge execution call.
"""
# pylint: disable=redefined-outer-name
from __future__ import annotations

import collections.abc as cabc
import copy
import logging
import operator
import typing as t

import capellambse
import pytest
import yaml
from capellambse import decl

from capella_rm_bridge.changeset import (
    actiontypes,
    calculate_change_set,
    change,
)

from .conftest import (
    TEST_CONFIG,
    TEST_DATA_PATH,
    TEST_MOD_CHANGESET_PATH,
    TEST_REQ_MODULE_UUID,
)

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
TEST_MODULE_CHANGE_1 = decl.load(TEST_MOD_CHANGESET_PATH)
TEST_MODULE_CHANGE_2 = decl.load(TEST_DATA_PATH / "changesets" / "delete.yaml")

INVALID_FIELD_VALUES = [
    ("Type", ["Not an option"], "values"),
    ("Capella ID", None, "value"),
    ("Type", None, "values"),
    ("Submitted at", 1, "value"),
]
INVALID_ATTR_DEF_ERROR_MSG = (
    "In RequirementType 'System Requirement': "
    "Invalid AttributeDefinitionEnumeration found: 'Not-Defined'. "
    "Missing its datatype definition in `data_types`."
)


class ActionsTest:
    """Base class for Test[Create|Mod|Delete]Actions."""

    tracker: cabc.Mapping[str, t.Any]
    tconfig: actiontypes.TrackerConfig = TEST_CONFIG["modules"][0]

    def tracker_change(
        self,
        model: capellambse.MelodyModel,
        tracker: cabc.Mapping[str, t.Any] | None = None,
        tracker_config: actiontypes.TrackerConfig | None = None,
        **kw: t.Any,
    ) -> change.TrackerChange:
        """Create a ``TrackerChange`` object."""
        return change.TrackerChange(
            tracker or self.tracker,
            model,
            tracker_config or self.tconfig,
            **kw,
        )


class TestTrackerChangeInit(ActionsTest):
    """UnitTests for init of ``TrackerChange``."""

    def test_init_on_missing_capella_UUID_raises_InvalidTrackerConfig(
        self, clean_model: capellambse.MelodyModel
    ) -> None:
        """Test that an invalid config raises InvalidTrackerConfig.

        A configuration file without all of the mandatory keys in the
        config of the RequirementsModule will lead to an
        ``InvalidTrackerConfig`` being raised during initialization of a
        ``TrackerChange`` object.
        """
        tconfig = copy.deepcopy(self.tconfig)
        del tconfig["capella-uuid"]  # type:ignore[misc]

        with pytest.raises(actiontypes.InvalidTrackerConfig):
            self.tracker_change(clean_model, TEST_SNAPSHOT[0], tconfig)

    def test_init_on_missing_module_raises_MissingRequirementsModule(
        self, clean_model: capellambse.MelodyModel
    ) -> None:
        """Test that a model w/o module raises MissingRequirementsModule.

        A :external:class:`~capellambse.model.MelodyModel` without a
        ``RequirementsModule`` with a matching UUID from the config will
        lead to a ``MissingRequirementsModule`` being raised during
        initialization of a ``TrackerChange`` object.
        """
        del clean_model.la.requirement_modules[0]

        with pytest.raises(change.MissingRequirementsModule):
            self.tracker_change(clean_model, TEST_SNAPSHOT[0])

    def test_init_on_missing_module_id_raises_InvalidSnapshotModule(
        self, clean_model: capellambse.MelodyModel
    ) -> None:
        snapshot = copy.deepcopy(TEST_SNAPSHOT[0])
        del snapshot["id"]  # type: ignore[misc]

        with pytest.raises(actiontypes.InvalidSnapshotModule):
            self.tracker_change(clean_model, snapshot)


class TestCreateActions(ActionsTest):
    """UnitTests for all methods requesting creations."""

    tracker = TEST_SNAPSHOT[0]
    titem = tracker["items"][0]
    tracker_change_creations = TEST_MODULE_CHANGE[0]["extend"]

    TYPES_FOLDER_CHANGE = tracker_change_creations[
        "requirement_types_folders"
    ][0]
    DATA_TYPES_CHANGE = TYPES_FOLDER_CHANGE["data_type_definitions"]
    REQ_TYPES_CHANGE = TYPES_FOLDER_CHANGE["requirement_types"]
    REQ_CHANGE = tracker_change_creations["folders"][0]

    def test_create_data_type_definition_actions(
        self, clean_model: capellambse.MelodyModel
    ) -> None:
        r"""Test producing ``CreateAction``\ s for EnumDataTypeDefinitions."""
        snapshot = copy.deepcopy(self.tracker)
        snapshot["requirement_types"] = {}
        snapshot["items"] = []

        tchange = self.tracker_change(clean_model, snapshot)
        action = tchange.actions[0]
        rtf_action = action["extend"]["requirement_types_folders"][0]

        assert rtf_action["data_type_definitions"] == self.DATA_TYPES_CHANGE

    def test_create_requirement_type_actions(
        self, clean_model: capellambse.MelodyModel
    ) -> None:
        r"""Test producing ``CreateAction``\ s for RequirementTypes."""
        snapshot = copy.deepcopy(self.tracker)
        snapshot["items"] = []

        tchange = self.tracker_change(clean_model, snapshot)
        action = tchange.actions[0]
        rtf_action = action["extend"]["requirement_types_folders"][0]

        assert rtf_action["requirement_types"] == self.REQ_TYPES_CHANGE

    def test_create_attribute_definition_actions(
        self, clean_model: capellambse.MelodyModel
    ) -> None:
        """Test producing ``CreateAction`` for a RequirementsTypeFolder."""
        snapshot = copy.deepcopy(self.tracker)
        snapshot["items"] = []

        tchange = self.tracker_change(clean_model, snapshot)
        action = tchange.actions[0]
        attr_def_action = action["extend"]["requirement_types_folders"][0]

        assert attr_def_action == self.TYPES_FOLDER_CHANGE

    def test_create_requirements_actions(
        self, clean_model: capellambse.MelodyModel
    ) -> None:
        r"""Test producing ``CreateAction``\ s for Requirements."""
        tchange = self.tracker_change(clean_model)

        action = next(tchange.yield_requirements_create_actions(self.titem))

        assert action == self.REQ_CHANGE

    @pytest.mark.parametrize("attr,faulty_value,key", INVALID_FIELD_VALUES)
    def test_faulty_attribute_values_log_InvalidFieldValue_as_error(
        self,
        clean_model: capellambse.MelodyModel,
        attr: str,
        faulty_value: actiontypes.Primitive,
        key: str,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Test logging ``InvalidFieldValue`` on faulty field data."""
        tracker = copy.deepcopy(self.tracker)
        titem = tracker["items"][0]
        first_child = titem["children"][0]
        first_child["attributes"][attr] = faulty_value  # type:ignore[index]
        message_end = (
            f"Invalid field found: {key} '{faulty_value}' for '{attr}'"
        )

        with caplog.at_level(logging.ERROR):
            self.tracker_change(clean_model, tracker, gather_logs=False)

        assert caplog.messages[0].endswith(message_end)

    def test_InvalidFieldValue_errors_are_gathered(
        self, clean_model: capellambse.MelodyModel
    ) -> None:
        """Test faulty field data are gathered in errors."""
        tracker = copy.deepcopy(self.tracker)
        titem = tracker["items"][0]
        first_child = titem["children"][0]
        messages = list[str]()
        for attr, faulty_value, key in INVALID_FIELD_VALUES[1:]:
            first_child["attributes"][
                attr
            ] = faulty_value  # type:ignore[index]
            messages.append(
                "Invalid workitem 'REQ-002'. "
                f"Invalid field found: {key} '{faulty_value}' for '{attr}'"
            )

        change = self.tracker_change(clean_model, tracker, gather_logs=True)

        assert change.errors == messages

    def test_faulty_data_types_log_InvalidAttributeDefinition_as_error(
        self,
        clean_model: capellambse.MelodyModel,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        tracker = copy.deepcopy(self.tracker)
        reqtype = tracker["requirement_types"]["system_requirement"]
        reqtype["attributes"]["Not-Defined"] = {  # type: ignore[call-overload]
            "type": "Enum",
            "data_type": "Not-Defined",
        }

        with caplog.at_level(logging.ERROR):
            self.tracker_change(clean_model, tracker, gather_logs=False)

        assert caplog.messages[0].endswith(INVALID_ATTR_DEF_ERROR_MSG)

    def test_InvalidAttributeDefinition_errors_are_gathered(
        self, clean_model: capellambse.MelodyModel
    ) -> None:
        """Test faulty field data are gathered in errors."""
        tracker = copy.deepcopy(self.tracker)
        reqtype = tracker["requirement_types"]["system_requirement"]
        reqtype["attributes"]["Not-Defined"] = {  # type: ignore[call-overload]
            "type": "Enum",
            "data_type": "Not-Defined",
        }

        change = self.tracker_change(clean_model, tracker, gather_logs=True)

        assert change.errors == [INVALID_ATTR_DEF_ERROR_MSG]

    @pytest.mark.integtest
    def test_calculate_change_sets(
        self, clean_model: capellambse.MelodyModel
    ) -> None:
        """Test ``ChangeSet`` on clean model for first migration run."""
        change_set, errors = calculate_change_set(
            clean_model, TEST_CONFIG["modules"][0], TEST_SNAPSHOT[0]
        )

        assert not errors
        assert change_set == TEST_MODULE_CHANGE


class TestModActions(ActionsTest):
    """Tests all methods that request modifications."""

    tracker = TEST_SNAPSHOT_1[0]
    titem = tracker["items"][0]

    ENUM_DATA_TYPE_MODS = TEST_MODULE_CHANGE_1[:2]
    REQ_TYPE_MODS = TEST_MODULE_CHANGE_1[2:4]
    REQ_CHANGE = TEST_MODULE_CHANGE_1[4:10]
    REQ_FOLDER_MOVE = TEST_MODULE_CHANGE_1[-1]

    def test_mod_data_type_definition_actions(
        self, migration_model: capellambse.MelodyModel
    ) -> None:
        r"""Test producing ``ModAction``\ s for EnumDataTypeDefinitions."""
        snapshot = copy.deepcopy(self.tracker)
        snapshot["requirement_types"] = TEST_SNAPSHOT[0]["requirement_types"]
        snapshot["items"] = []

        tchange = self.tracker_change(migration_model, snapshot)
        enum_data_type_actions = tchange.actions[:2]

        assert enum_data_type_actions == self.ENUM_DATA_TYPE_MODS

    def test_mod_requirement_type_actions(
        self, migration_model: capellambse.MelodyModel
    ) -> None:
        r"""Test producing ``ModAction``\ s for RequirementTypes."""
        snapshot = copy.deepcopy(self.tracker)
        snapshot["data_types"] = TEST_SNAPSHOT[0]["data_types"]
        snapshot["items"] = TEST_SNAPSHOT[0]["items"]

        tchange = self.tracker_change(migration_model, snapshot)

        assert tchange.actions == self.REQ_TYPE_MODS

    def test_mod_requirements_actions(
        self, migration_model: capellambse.MelodyModel
    ) -> None:
        """Test that RequirementsModActions are produced."""
        tchange = self.tracker_change(migration_model)

        assert tchange.actions[4:] == self.REQ_CHANGE + [self.REQ_FOLDER_MOVE]

    @pytest.mark.parametrize("attr,faulty_value,key", INVALID_FIELD_VALUES)
    def test_faulty_attribute_values_log_InvalidFieldValue_as_error(
        self,
        migration_model: capellambse.MelodyModel,
        attr: str,
        faulty_value: actiontypes.Primitive,
        key: str,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Test logging ``InvalidFieldValue`` on faulty field data."""
        tracker = copy.deepcopy(self.tracker)
        titem = tracker["items"][0]
        first_child = titem["children"][0]
        first_child["attributes"][attr] = faulty_value
        message_end = (
            f"Invalid field found: {key} '{faulty_value}' for '{attr}'"
        )

        with caplog.at_level(logging.ERROR):
            self.tracker_change(migration_model, tracker, gather_logs=False)

        assert caplog.messages[0].endswith(message_end)

    @pytest.mark.integtest
    def test_calculate_change_sets(
        self, migration_model: capellambse.MelodyModel
    ) -> None:
        """Test ChangeSet on clean model for first migration run."""
        change_set, errors = calculate_change_set(
            migration_model, TEST_CONFIG["modules"][0], TEST_SNAPSHOT_1[0]
        )

        assert not errors
        assert change_set == TEST_MODULE_CHANGE_1


class TestDeleteActions(ActionsTest):
    """Test all methods that request deletions."""

    tracker = TEST_SNAPSHOT_2[0]
    titem = tracker["items"][0]

    REQ_TYPE_FOLDER_DEL = TEST_MODULE_CHANGE_2[0]
    ENUM_DATA_TYPE_DEL = TEST_MODULE_CHANGE_2[1]
    ATTR_DEF_DEL = TEST_MODULE_CHANGE_2[2]
    REQ_DEL, FOLDER_DEL = TEST_MODULE_CHANGE_2[-2:]

    def resolve_ChangeSet(
        self,
        model: capellambse.MelodyModel,
        change_set: cabc.MutableMapping[str, t.Any],
    ) -> cabc.MutableMapping[str, t.Any]:
        """Fix promised objects in the ``ChangeSet``.

        Some objects are created dynamically in the ``deletion_model``
        fixture. Therefore the UUIDs needed for reference in the
        deletion ``ChangeSet`` can't be fixated and notated.
        """
        new_set = copy.deepcopy(change_set)
        obj = model.by_uuid(change_set["parent"].uuid)
        for origin, deletions in change_set["delete"].items():
            for i, d in enumerate(deletions):
                if isinstance(d, decl.UUIDReference):
                    continue

                split = d.split(" ")
                getter, value = split[0], " ".join(split[1:])
                elements = operator.attrgetter(f"{origin}.by_{getter}")(obj)
                new_set["delete"][origin][i] = decl.UUIDReference(
                    elements(value, single=True).uuid
                )

        return new_set

    def test_delete_data_type_definition_actions(
        self, deletion_model: capellambse.MelodyModel
    ) -> None:
        """Test that EnumDataTypeDefinitions are deleted."""
        snapshot = copy.deepcopy(self.tracker)
        snapshot["requirement_types"] = TEST_SNAPSHOT_1[0]["requirement_types"]
        snapshot["items"] = []
        data_type_del = copy.deepcopy(self.REQ_TYPE_FOLDER_DEL)
        del data_type_del["delete"]["requirement_types"]
        data_type_del = self.resolve_ChangeSet(deletion_model, data_type_del)
        expected_actions = [data_type_del, self.ENUM_DATA_TYPE_DEL]

        tchange = self.tracker_change(deletion_model, snapshot)
        enum_data_type_actions = tchange.actions[:2]

        assert enum_data_type_actions == expected_actions

    def test_delete_requirement_type_actions(
        self, deletion_model: capellambse.MelodyModel
    ) -> None:
        """Test that RequirementTypes are deleted."""
        snapshot = copy.deepcopy(self.tracker)
        snapshot["data_types"] = TEST_SNAPSHOT_1[0]["data_types"]
        snapshot["items"] = []
        req_type_del = copy.deepcopy(self.REQ_TYPE_FOLDER_DEL)
        del req_type_del["delete"]["data_type_definitions"]
        attr_def_del = copy.deepcopy(self.ATTR_DEF_DEL)
        attr_def_del = self.resolve_ChangeSet(deletion_model, attr_def_del)

        tchange = self.tracker_change(deletion_model, snapshot)

        assert tchange.actions[:2] == [req_type_del, attr_def_del]

    def test_delete_requirements_actions(
        self, deletion_model: capellambse.MelodyModel
    ) -> None:
        """Test that RequirementsModActions are produced."""
        snapshot = copy.deepcopy(self.tracker)
        snapshot["data_types"] = TEST_SNAPSHOT_1[0]["data_types"]
        snapshot["requirement_types"] = TEST_SNAPSHOT_1[0]["requirement_types"]
        requirement_del = self.resolve_ChangeSet(deletion_model, self.REQ_DEL)

        tchange = self.tracker_change(deletion_model, snapshot)

        assert tchange.actions == [requirement_del, self.FOLDER_DEL]

    @pytest.mark.integtest
    def test_calculate_change_sets(
        self, deletion_model: capellambse.MelodyModel
    ) -> None:
        """Test ChangeSet on clean model for first migration run."""
        expected_change_set = copy.deepcopy(TEST_MODULE_CHANGE_2)
        expected_change_set[2] = self.resolve_ChangeSet(
            deletion_model, TEST_MODULE_CHANGE_2[2]
        )
        expected_change_set[3] = self.resolve_ChangeSet(
            deletion_model, TEST_MODULE_CHANGE_2[3]
        )

        change_set, errors = calculate_change_set(
            deletion_model, TEST_CONFIG["modules"][0], TEST_SNAPSHOT_2[0]
        )

        assert not errors
        assert change_set == expected_change_set


@pytest.mark.integtest
class TestCalculateChangeSet(ActionsTest):
    """Integration tests for ``calculate_change_set``."""

    SKIP_MESSAGE = "Skipping module: project/space/example title"

    def test_missing_module_UUID_logs_InvalidTrackerConfig_error(
        self,
        clean_model: capellambse.MelodyModel,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Test that an invalid config logs an error."""
        config = copy.deepcopy(TEST_CONFIG["modules"][0])
        del config["capella-uuid"]  # type:ignore[misc]
        message = (
            "The given module configuration is missing 'UUID' of the target "
            "RequirementsModule"
        )

        with caplog.at_level(logging.ERROR):
            calculate_change_set(
                clean_model, config, TEST_SNAPSHOT[0], gather_logs=False
            )

        assert caplog.messages[0] == f"{self.SKIP_MESSAGE}. {message}"

    def test_missing_module_logs_MissingRequirementsModule_error(
        self,
        clean_model: capellambse.MelodyModel,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Test that a model w/o module raises MissingRequirementsModule."""
        tconfig = TEST_CONFIG["modules"][0]
        del clean_model.la.requirement_modules[0]
        message = (
            f"No RequirementsModule with UUID '{TEST_REQ_MODULE_UUID}' found "
            f"in {clean_model.info!r}"
        )

        with caplog.at_level(logging.ERROR):
            calculate_change_set(
                clean_model, tconfig, TEST_SNAPSHOT[0], gather_logs=False
            )

        assert caplog.messages[0] == f"{self.SKIP_MESSAGE}. {message}"

    def test_missing_module_id_logs_InvalidSnapshotModule_error(
        self,
        clean_model: capellambse.MelodyModel,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        snapshot = copy.deepcopy(TEST_SNAPSHOT[0])
        del snapshot["id"]  # type: ignore[misc]
        tconfig = TEST_CONFIG["modules"][0]
        message = (
            "Skipping module: MISSING ID. "
            "In the snapshot the module is missing an 'id' key"
        )

        with caplog.at_level(logging.ERROR):
            calculate_change_set(
                clean_model, tconfig, snapshot, gather_logs=False
            )

        assert caplog.messages[0] == message

    def test_init_errors_are_gathered(
        self, clean_model: capellambse.MelodyModel
    ) -> None:
        """Test that errors from an invalid config are gathered."""
        config = copy.deepcopy(TEST_CONFIG["modules"][0])
        del config["capella-uuid"]  # type:ignore[misc]
        message = (
            "The given module configuration is missing 'UUID' of the target "
            "RequirementsModule"
        )

        _, errors = calculate_change_set(
            clean_model, config, TEST_SNAPSHOT[0], gather_logs=True
        )

        assert errors[0].startswith(self.SKIP_MESSAGE)
        assert message in errors[0]

    def test_snapshot_errors_from_ChangeSet_calculation_are_gathered(
        self, clean_model: capellambse.MelodyModel
    ) -> None:
        snapshot = copy.deepcopy(TEST_SNAPSHOT[0])
        titem = snapshot["items"][0]
        first_child = titem["children"][0]
        titem["attributes"]["Test"] = 1  # type: ignore[index]
        messages = [
            "Invalid workitem 'REQ-001'. "
            "Invalid field found: field name 'Test' not defined in "
            "attributes of requirement type 'system_requirement'"
        ]
        for attr, faulty_value, key in INVALID_FIELD_VALUES[1:]:
            first_child["attributes"][
                attr
            ] = faulty_value  # type:ignore[index]
            messages.append(
                "Invalid workitem 'REQ-002'. "
                + f"Invalid field found: {key} '{faulty_value}' for '{attr}'"
            )
        del titem["children"][1]["type"]
        tconfig = TEST_CONFIG["modules"][0]
        messages.append(
            "Invalid workitem 'REQ-003'. Missing type but attributes found"
        )

        _, errors = calculate_change_set(
            clean_model, tconfig, snapshot, gather_logs=True
        )

        assert errors[0].splitlines()[2:-1] == messages
