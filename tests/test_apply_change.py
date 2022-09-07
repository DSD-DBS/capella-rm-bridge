# SPDX-FileCopyrightText: Copyright DB Netz AG and the rm-bridge contributors
# SPDX-License-Identifier: Apache-2.0
"""Test functionality of applying computed ``ChangeSet``s to a model."""
# pylint: disable=redefined-outer-name
import logging
import pathlib
import shutil

import capellambse
import pytest
import yaml

from rm_bridge.model_modifier import apply_change

from . import conftest as ct

TEST_CHANGESETS_PATH = ct.TEST_DATA_PATH / "changesets"
TEST_MODULE_CREATE_CHANGE = yaml.load(
    (TEST_CHANGESETS_PATH / "create.yaml").read_text(encoding="utf-8"),
    Loader=yaml.Loader,
)
TEST_MODULE_MOD_CHANGE = yaml.load(
    (TEST_CHANGESETS_PATH / "mod.yaml").read_text(encoding="utf-8"),
    Loader=yaml.Loader,
)
TEST_MODULE_DEL_CHANGE = yaml.load(
    (TEST_CHANGESETS_PATH / "delete.yaml").read_text(encoding="utf-8"),
    Loader=yaml.Loader,
)


@pytest.fixture
def clean_tmp_model(tmp_path: pathlib.Path) -> capellambse.MelodyModel:
    shutil.copytree(ct.TEST_MODEL_PATH.parent, tmp_dest := tmp_path / "model")
    model = capellambse.MelodyModel(path=tmp_dest / ct.TEST_MODEL_PATH.name)
    reqmodule = model.by_uuid(ct.TEST_REQ_MODULE_UUID)
    del reqmodule.requirement_types_folders[0]
    del reqmodule.folders[0]
    yield model
    model.save()


class TestCreateModelChange:
    @pytest.mark.integtest
    def test_apply_changes(
        self,
        clean_tmp_model: capellambse.MelodyModel,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        tracker = ct.TEST_CONFIG["trackers"][0]
        modelchange = apply_change.ModelChange(clean_tmp_model)
        expected_creations = (
            "<RequirementsTypesFolder 'Types'",
            "<RequirementsFolder 'System Requirement Specifications/"
            "<p>Test Description</p>'",
        )

        with caplog.at_level(logging.INFO):
            modelchange.apply_changes(
                tracker["external-id"],
                tracker["capella-uuid"],
                TEST_MODULE_CREATE_CHANGE[tracker["external-id"]],
            )

        assert len(caplog.messages) == 3
        assert "No RequirementsTypeFolder found." in caplog.messages
        for actual, exp in zip(caplog.messages[1:], expected_creations):
            assert actual.startswith(f"Created '{exp}")


@pytest.fixture
def migration_tmp_model(tmp_path: pathlib.Path) -> capellambse.MelodyModel:
    shutil.copytree(ct.TEST_MODEL_PATH.parent, tmp_dest := tmp_path / "model")
    model = capellambse.MelodyModel(path=tmp_dest / ct.TEST_MODEL_PATH.name)
    yield model
    model.save()


class TestModModelChange:
    @pytest.mark.integtest
    def test_apply_changes(
        self,
        migration_tmp_model: capellambse.MelodyModel,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        tracker = ct.TEST_CONFIG["trackers"][0]
        modelchange = apply_change.ModelChange(migration_tmp_model)
        creations = (
            "<EnumerationDataTypeDefinition 'Release'",
            "<AttributeDefinitionEnumeration 'Release'",
            "<AttributeDefinition 'Test after migration'",
            "<StringValueAttribute 'Capella ID'",
            "<EnumerationValueAttribute 'Release'",
            "<StringValueAttribute 'Test after migration'",
        )
        req_module = migration_tmp_model.by_uuid(
            "3be8d0fc-c693-4b9b-8fa1-d59a9eec6ea4"
        )
        moved_folder = migration_tmp_model.by_uuid(
            "04574907-fa9f-423a-b9fd-fc22dc975dc8"
        )
        moved = (
            "Moved '<RequirementsFolder 'System Requirement Specifications/"
            "<p>Brand new</p>' (04574907-fa9f-423a-b9fd-fc22dc975dc8)>'"
        )
        expected_messages = [f"Created '{c}" for c in creations] + [moved]

        with caplog.at_level(logging.INFO):
            modelchange.apply_changes(
                tracker["external-id"],
                tracker["capella-uuid"],
                TEST_MODULE_MOD_CHANGE[tracker["external-id"]],
            )

        assert len(caplog.messages) == 7
        assert caplog.messages[-1] == moved
        assert moved_folder.parent == req_module
        for actual, exp in zip(caplog.messages[:-1], expected_messages):
            assert actual.startswith(exp)


class TestDeleteModelChange:
    @pytest.mark.integtest
    def test_apply_changes(
        self,
        deletion_model: capellambse.MelodyModel,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        tracker = ct.TEST_CONFIG["trackers"][0]
        modelchange = apply_change.ModelChange(deletion_model)
        puuid = ct.TEST_UUID_PREFIX
        expected = (
            f"<EnumerationDataTypeDefinition 'Release' ({puuid}1)>",
            f"<AttributeDefinitionEnumeration 'Release' ({puuid}2)>",
            f"<AttributeDefinition 'Test after migration' ({puuid}3)>",
            f"<EnumerationValueAttribute ({puuid}4)>",
            f"<StringValueAttribute ({puuid}5)>",
            f"<RequirementsFolder 'Kinds' ({puuid}6)>",
        )

        with caplog.at_level(logging.INFO):
            modelchange.apply_changes(
                tracker["external-id"],
                tracker["capella-uuid"],
                TEST_MODULE_DEL_CHANGE[tracker["external-id"]],
            )

        assert caplog.messages == [f"Deleting '{exp}'" for exp in expected]
