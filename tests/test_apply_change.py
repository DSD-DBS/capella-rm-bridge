# SPDX-FileCopyrightText: Copyright DB Netz AG and the rm-bridge contributors
# SPDX-License-Identifier: Apache-2.0
"""Test functionality of applying computed ``ChangeSet``s to a model."""
# pylint: disable=redefined-outer-name
import pathlib
import shutil

import capellambse
import pytest
import yaml

from rm_bridge.model_modifier import apply_change
from rm_bridge.model_modifier.changeset import find

from . import conftest as ct

TEST_CHANGESETS_PATH = ct.TEST_DATA_PATH / "changesets"
TEST_MODULE_CREATE_CHANGE = yaml.load(
    (TEST_CHANGESETS_PATH / "create.yaml").read_text(encoding="utf-8"),
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


class ModelChangeTest:
    def modelchange(
        self, model: capellambse.MelodyModel, reqfinder: find.ReqFinder
    ) -> apply_change.ModelChange:
        return apply_change.ModelChange(model, reqfinder)


class TestCreateModelChange(ModelChangeTest):
    @pytest.mark.integtest
    def test_apply_changes(self, clean_tmp_model: capellambse.MelodyModel):
        tracker = ct.TEST_CONFIG["trackers"][0]
        modelchange = self.modelchange(
            clean_tmp_model, find.ReqFinder(clean_tmp_model)
        )

        modelchange.apply_changes(
            tracker["external-id"],
            tracker["capella-uuid"],
            TEST_MODULE_CREATE_CHANGE[tracker["external-id"]],
        )
