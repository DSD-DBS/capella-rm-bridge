# SPDX-FileCopyrightText: Copyright DB Netz AG and the rm-bridge contributors
# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import json

import capellambse
import pytest
import yaml
from capellambse.model import common

from rm_bridge import auditing


class TestChangeAuditor:
    TEST_UUID = "f8e2195d-b5f5-4452-a12b-79233d943d5e"

    def test_modification_tracking(self, clean_model: capellambse.MelodyModel):
        obj = clean_model.by_uuid(self.TEST_UUID)
        new_name = "Not Test Module anymore"

        with auditing.ChangeAuditor(clean_model) as changes:
            obj.name = new_name

        assert len(changes) == 1
        assert isinstance((change := changes[0]), auditing.Modification)
        assert change.parent == self.TEST_UUID
        assert change.attribute == "name"
        assert change.new == new_name
        assert change.old == "Test Module"

    def test_item_extension_tracking(
        self, clean_model: capellambse.MelodyModel
    ):
        obj = clean_model.by_uuid(self.TEST_UUID)
        folder = obj.folders.pop()

        with auditing.ChangeAuditor(clean_model) as changes:
            obj.folders.insert(0, folder)

        assert len(changes) == 1
        assert isinstance((change := changes[0]), auditing.Extension)
        assert change.parent == self.TEST_UUID
        assert change.attribute == "folders"
        assert (
            change.element == f"<RequirementsFolder 'Folder' ({folder.uuid})>"
        )
        assert change.uuid == folder.uuid

    def test_create_extension_tracking(
        self, clean_model: capellambse.MelodyModel
    ):
        obj = clean_model.by_uuid(self.TEST_UUID)
        long_name = "Test ChangeAudit Requirement"

        with pytest.raises(KeyError):
            obj.requirements.by_name(long_name)

        with auditing.ChangeAuditor(clean_model) as changes:
            new_req = obj.requirements.create(long_name=long_name)

        assert len(changes) == 1
        assert isinstance((change := changes[0]), auditing.Extension)
        assert change.parent == self.TEST_UUID
        assert change.attribute == "requirements"
        assert (
            change.element == f"<Requirement '{long_name}' ({new_req.uuid})>"
        )
        assert change.uuid == new_req.uuid

    def test_create_singleattr_extension_tracking(
        self, clean_model: capellambse.MelodyModel
    ):
        r"""Currently only  for ``reqif.EnumValue``\ s."""
        uuid = "67bba9cf-953c-4f0b-9986-41991c68d241"
        reqtypesfolder = clean_model.by_uuid(uuid)
        name = "Test ChangeAudit"
        assert len(reqtypesfolder.data_type_definitions) == 2
        assert name not in reqtypesfolder.data_type_definitions.by_name
        values = [f"{name} enum_val"]

        with auditing.ChangeAuditor(clean_model) as changes:
            new_enum_data_def = reqtypesfolder.data_type_definitions.create(
                "EnumerationDataTypeDefinition", long_name=name, values=values
            )

        ev = new_enum_data_def.values[0]

        assert len(changes) == 3
        assert isinstance(changes[0], auditing.Modification)
        assert changes[0].parent == new_enum_data_def.uuid
        assert changes[0].attribute == "values"
        assert changes[0].new == common.ElementList(clean_model, [])
        assert changes[0].old == common.ElementList(clean_model, [])
        assert isinstance(changes[1], auditing.Extension)
        assert changes[1].parent == new_enum_data_def.uuid
        assert changes[1].attribute == "values"
        assert (
            changes[1].element == f"<EnumValue '{name} enum_val' ({ev.uuid})>"
        )
        assert changes[1].uuid == ev.uuid
        assert isinstance(changes[2], auditing.Extension)
        assert changes[2].parent == uuid
        assert changes[2].attribute == "data_type_definitions"
        assert (
            changes[2].element
            == f"<EnumDataTypeDefinition {name!r} ({new_enum_data_def.uuid})>"
        )
        assert changes[2].uuid == new_enum_data_def.uuid

    def test_deletion_tracking(self, clean_model: capellambse.MelodyModel):
        obj = clean_model.by_uuid(self.TEST_UUID)
        folder = obj.folders[0]

        with auditing.ChangeAuditor(clean_model) as changes:
            del obj.folders[0]

        assert len(changes) == 1
        assert isinstance(changes[0], auditing.Deletion)
        assert changes[0].parent == self.TEST_UUID
        assert changes[0].attribute == "folders"
        assert (
            changes[0].element
            == f"<RequirementsFolder 'Folder' ({folder.uuid})>"
        )
        assert changes[0].uuid == folder.uuid

    def test_multiple_changes_are_tracked(
        self, clean_model: capellambse.MelodyModel
    ):
        obj = clean_model.by_uuid(self.TEST_UUID)
        new_name = "Not Module anymore"
        req = clean_model.oa.all_requirements[0]

        with auditing.ChangeAuditor(clean_model) as changes:
            obj.long_name = new_name
            obj.requirements.insert(0, req)
            del obj.requirements[0]

        assert len(changes) == 3
        assert isinstance(changes[0], auditing.Modification)
        assert changes[0].parent == self.TEST_UUID
        assert changes[0].attribute == "long_name"
        assert changes[0].new == new_name
        assert changes[0].old == "Module"
        assert isinstance(changes[1], auditing.Extension)
        assert changes[1].parent == self.TEST_UUID
        assert changes[1].attribute == "requirements"
        assert changes[1].element == f"<Requirement 'TestReq1' ({req.uuid})>"
        assert changes[1].uuid == req.uuid
        assert isinstance(changes[2], auditing.Deletion)
        assert changes[1].parent == self.TEST_UUID
        assert changes[1].attribute == "requirements"
        assert changes[1].element == f"<Requirement 'TestReq1' ({req.uuid})>"
        assert changes[1].uuid == req.uuid

    def test_filtering_changes_works(
        self, clean_model: capellambse.MelodyModel
    ):
        obj = clean_model.by_uuid(self.TEST_UUID)
        new_name = "Not Module anymore"
        req = clean_model.oa.all_requirements[0]

        with auditing.ChangeAuditor(clean_model, {"Requirement"}) as changes:
            obj.long_name = new_name
            obj.requirements.insert(0, req)
            del obj.requirements[0]

            req.long_name = "2"

        assert len(changes) == 1
        assert isinstance(changes[0], auditing.Modification)
        assert changes[0].parent == req.uuid
        assert changes[0].attribute == "long_name"
        assert changes[0].new == req.long_name
        assert changes[0].old == "1"

    def test_safe_dump_context_is_writable(
        self, clean_model: capellambse.MelodyModel
    ):
        obj = clean_model.by_uuid(self.TEST_UUID)

        with auditing.ChangeAuditor(clean_model) as changes:
            obj.long_name = "Not Module anymore"
            obj.requirements.insert(0, clean_model.oa.all_requirements[0])
            del obj.requirements[0]

        assert (dump := auditing.dump(changes))
        json.dumps(dump)
        yaml.dump(dump)

    def test_destroys_model_reference_when_detach(
        self, clean_model: capellambse.MelodyModel
    ):
        auditor = auditing.ChangeAuditor(clean_model)

        auditor.detach()

        assert auditor.model is None


@pytest.mark.parametrize(
    ["iterable", "expected"],
    [
        ([("dogs", 2)], "Synchronized 2 dogs:"),
        ([("dogs", 2), ("cats", 1)], "Synchronized 1 cats and 2 dogs:"),
        (
            [("dogs", 2), ("cats", 1), ("birds", 3)],
            "Synchronized 3 birds, 1 cats and 2 dogs:",
        ),
    ],
)
def test_generate_main_message(iterable: list[tuple[str, int]], expected: str):
    assert auditing.generate_main_message(iterable) == expected
