# SPDX-FileCopyrightText: Copyright DB Netz AG and the rm-bridge contributors
# SPDX-License-Identifier: Apache-2.0

import capellambse
import pytest
import yaml

from rm_bridge.model_modifier import apply_change
from rm_bridge.model_modifier.changeset import find

from .conftest import TEST_CONFIG, TEST_DATA_PATH

TEST_CHANGESETS_PATH = TEST_DATA_PATH / "changesets"
TEST_MODULE_CHANGE = yaml.load(
    (TEST_CHANGESETS_PATH / "create.yaml").read_text(encoding="utf-8"),
    Loader=yaml.Loader,
)


class ModelChangeTest:
    def modelchange(
        self, model: capellambse.MelodyModel, reqfinder: find.ReqFinder
    ) -> apply_change.ModelChange:
        return apply_change.ModelChange(model, reqfinder)


class TestCreateModelChange(ModelChangeTest):
    @pytest.mark.integtest
    def test_apply_changes(self, clean_model: capellambse.MelodyModel):
        tracker = TEST_CONFIG["trackers"][0]
        modelchange = self.modelchange(
            clean_model, find.ReqFinder(clean_model)
        )

        modelchange.apply_changes(
            tracker["external-id"],
            tracker["capella-uuid"],
            TEST_MODULE_CHANGE[tracker["external-id"]],
        )
