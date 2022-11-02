# SPDX-FileCopyrightText: Copyright DB Netz AG and the rm-bridge contributors
# SPDX-License-Identifier: Apache-2.0
"""Test functionality of applying computed ``ChangeSet``\ s to a model."""
import collections.abc as cabc

# pylint: disable=redefined-outer-name
import logging
import pathlib
import shutil

import capellambse
import pytest
from capellambse import decl

from . import conftest as ct

TEST_CHANGESETS_PATH = ct.TEST_DATA_PATH / "changesets"
TEST_MODULE_CREATE_CHANGE = decl.load(TEST_CHANGESETS_PATH / "create.yaml")
TEST_MODULE_MOD_CHANGE = decl.load(TEST_CHANGESETS_PATH / "mod.yaml")
TEST_MODULE_DEL_CHANGE = decl.load(TEST_CHANGESETS_PATH / "delete.yaml")


@pytest.fixture
def clean_tmp_model(tmp_path: pathlib.Path) -> capellambse.MelodyModel:
    shutil.copytree(ct.TEST_MODEL_PATH.parent, tmp_dest := tmp_path / "model")
    model = capellambse.MelodyModel(path=tmp_dest / ct.TEST_MODEL_PATH.name)
    reqmodule = model.by_uuid(ct.TEST_REQ_MODULE_UUID)
    del reqmodule.requirement_types_folders[0]
    del reqmodule.folders[0]
    yield model
    model.save()


@pytest.fixture
def migration_tmp_model(tmp_path: pathlib.Path) -> capellambse.MelodyModel:
    shutil.copytree(ct.TEST_MODEL_PATH.parent, tmp_dest := tmp_path / "model")
    model = capellambse.MelodyModel(path=tmp_dest / ct.TEST_MODEL_PATH.name)
    yield model
    model.save()


@pytest.mark.skip("Not ready yet")
@pytest.mark.integtest
@pytest.mark.parametrize(
    "change_set,expected_messages",
    [
        pytest.param(
            TEST_MODULE_CREATE_CHANGE,
            (
                "No RequirementsTypeFolder found.",
                "Created <RequirementsTypesFolder 'Types'",
                "Created <RequirementsFolder 'System Requirement Specifications/"
                "Created <p>Test Description</p>'",
            ),
            id="Create",
        ),
        pytest.param(
            TEST_MODULE_MOD_CHANGE,
            (
                "Created <EnumerationDataTypeDefinition 'Release'",
                "Created <AttributeDefinitionEnumeration 'Release'",
                "Created <AttributeDefinition 'Test after migration'",
                "Created <StringValueAttribute 'Capella ID'",
                "Created <EnumerationValueAttribute 'Release'",
                "Created <StringValueAttribute 'Test after migration'",
                (
                    "Moved '<RequirementsFolder 'System Requirement Specifications/"
                    "<p>Brand new</p>' (04574907-fa9f-423a-b9fd-fc22dc975dc8)>'"
                ),
            ),
            id="Modify",
        ),
        pytest.param(
            TEST_MODULE_DEL_CHANGE,
            (
                f"Deleting <EnumerationDataTypeDefinition 'Release' ({ct.TEST_UUID_PREFIX}1)>",
                f"Deleting <AttributeDefinitionEnumeration 'Release' ({ct.TEST_UUID_PREFIX}2)>",
                f"Deleting <AttributeDefinition 'Test after migration' ({ct.TEST_UUID_PREFIX}3)>",
                f"Deleting <EnumerationValueAttribute ({ct.TEST_UUID_PREFIX}4)>",
                f"Deleting <StringValueAttribute ({ct.TEST_UUID_PREFIX}5)>",
                f"Deleting <RequirementsFolder 'Kinds' ({ct.TEST_UUID_PREFIX}6)>",
            ),
            id="Delete",
        ),
    ],
)
def test_apply_changes(
    clean_tmp_model: capellambse.MelodyModel,
    caplog: pytest.LogCaptureFixture,
    change_set,
    expected_messages: cabc.Sequence[str],
) -> None:
    with caplog.at_level(logging.INFO):
        decl.apply(clean_tmp_model, change_set)

    assert len(caplog.messages) == len(expected_messages)
    for actual, exp in zip(caplog.messages, expected_messages):
        assert actual.startswith(exp)
