# SPDX-FileCopyrightText: Copyright DB Netz AG and the capella-rm-bridge contributors
# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import io
import json
import logging

import capellambse
import pytest
import yaml
from capellambse import decl

from capella_rm_bridge import __version__, auditing

TEST_REQMODULE_UUID = "f8e2195d-b5f5-4452-a12b-79233d943d5e"
TEST_REQMODULE_REPR = f"<CapellaModule 'Test Module' ({TEST_REQMODULE_UUID})>"
TEST_REQFOLDER_UUID = "e16f5cc1-3299-43d0-b1a0-82d31a137111"
TEST_REQFOLDER_REPR = f"<Folder 'Folder' ({TEST_REQFOLDER_UUID})>"
TEST_MODIFICATION = auditing.Modification(
    TEST_REQFOLDER_UUID, attribute="long_name", new="New", old="1"
)
TEST_EXTENSION = auditing.Extension(
    TEST_REQMODULE_UUID,
    attribute="folders",
    element=TEST_REQFOLDER_REPR,
    uuid=TEST_REQFOLDER_UUID,
)
TEST_DELETION = auditing.Deletion(
    TEST_REQMODULE_UUID,
    attribute="folders",
    element=TEST_REQFOLDER_REPR,
    uuid=TEST_REQFOLDER_UUID,
)


class TestChangeAuditor:
    def test_modification_tracking(self, clean_model: capellambse.MelodyModel):
        obj = clean_model.by_uuid(TEST_REQMODULE_UUID)
        new_name = "Not Test Module anymore"

        with auditing.ChangeAuditor(clean_model) as changes:
            obj.name = new_name

        assert len(changes) == 1
        assert isinstance((change := changes[0]), auditing.Modification)
        assert change.parent == TEST_REQMODULE_UUID
        assert change.attribute == "name"
        assert change.new == new_name
        assert change.old == "Test Module"

    def test_item_extension_tracking(
        self, clean_model: capellambse.MelodyModel
    ):
        obj = clean_model.by_uuid(TEST_REQMODULE_UUID)
        folder = obj.folders.pop()

        with auditing.ChangeAuditor(clean_model) as changes:
            obj.folders.insert(0, folder)

        assert len(changes) == 1
        assert isinstance((change := changes[0]), auditing.Extension)
        assert change.parent == TEST_REQMODULE_UUID
        assert change.attribute == "folders"
        assert change.element == f"<Folder 'Folder' ({folder.uuid})>"
        assert change.uuid == folder.uuid

    def test_create_extension_tracking(
        self, clean_model: capellambse.MelodyModel
    ):
        obj = clean_model.by_uuid(TEST_REQMODULE_UUID)
        long_name = "Test ChangeAudit Requirement"

        with pytest.raises(KeyError):
            obj.requirements.by_name(long_name)

        with auditing.ChangeAuditor(clean_model) as changes:
            new_req = obj.requirements.create(long_name=long_name)

        assert len(changes) == 1
        assert isinstance((change := changes[0]), auditing.Extension)
        assert change.parent == TEST_REQMODULE_UUID
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
        declarative = [
            {
                "parent": decl.UUIDReference(reqtypesfolder.uuid),
                "extend": {
                    "data_type_definitions": [
                        {
                            "long_name": name,
                            "values": [{"long_name": f"{name} enum_val"}],
                            "_type": "EnumerationDataTypeDefinition",
                        }
                    ]
                },
            }
        ]

        with auditing.ChangeAuditor(clean_model) as changes:
            decl.apply(clean_model, io.StringIO(decl.dump(declarative)))

        new_enum_data_def = reqtypesfolder.data_type_definitions[-1]
        ev = new_enum_data_def.values[0]

        assert len(changes) == 2
        assert isinstance(changes[0], auditing.Extension)
        assert changes[0].parent == uuid
        assert changes[0].attribute == "data_type_definitions"
        assert (
            changes[0].element
            == f"<EnumerationDataTypeDefinition {name!r} ({new_enum_data_def.uuid})>"
        )
        assert changes[0].uuid == new_enum_data_def.uuid
        assert isinstance(changes[1], auditing.Extension)
        assert changes[1].parent == new_enum_data_def.uuid
        assert changes[1].attribute == "values"
        assert (
            changes[1].element == f"<EnumValue '{name} enum_val' ({ev.uuid})>"
        )
        assert changes[1].uuid == ev.uuid

    def test_deletion_tracking(self, clean_model: capellambse.MelodyModel):
        obj = clean_model.by_uuid(TEST_REQMODULE_UUID)
        folder = obj.folders[0]

        with auditing.ChangeAuditor(clean_model) as changes:
            del obj.folders[0]

        assert len(changes) == 1
        assert isinstance(changes[0], auditing.Deletion)
        assert changes[0].parent == TEST_REQMODULE_UUID
        assert changes[0].attribute == "folders"
        assert changes[0].element == f"<Folder 'Folder' ({folder.uuid})>"
        assert changes[0].uuid == folder.uuid

    def test_multiple_changes_are_tracked(
        self, clean_model: capellambse.MelodyModel
    ):
        obj = clean_model.by_uuid(TEST_REQMODULE_UUID)
        new_name = "Not Module anymore"
        req = clean_model.oa.all_requirements[0]

        with auditing.ChangeAuditor(clean_model) as changes:
            obj.long_name = new_name
            obj.requirements.insert(0, req)
            del obj.requirements[0]

        assert len(changes) == 3
        assert isinstance(changes[0], auditing.Modification)
        assert changes[0].parent == TEST_REQMODULE_UUID
        assert changes[0].attribute == "long_name"
        assert changes[0].new == new_name
        assert changes[0].old == "Module"
        assert isinstance(changes[1], auditing.Extension)
        assert changes[1].parent == TEST_REQMODULE_UUID
        assert changes[1].attribute == "requirements"
        assert changes[1].element == f"<Requirement 'TestReq1' ({req.uuid})>"
        assert changes[1].uuid == req.uuid
        assert isinstance(changes[2], auditing.Deletion)
        assert changes[1].parent == TEST_REQMODULE_UUID
        assert changes[1].attribute == "requirements"
        assert changes[1].element == f"<Requirement 'TestReq1' ({req.uuid})>"
        assert changes[1].uuid == req.uuid

    def test_filtering_changes_works(
        self, clean_model: capellambse.MelodyModel
    ):
        obj = clean_model.by_uuid(TEST_REQMODULE_UUID)
        new_name = "Not Module anymore"
        req = clean_model.oa.all_requirements[0]

        with auditing.ChangeAuditor(clean_model, {"Requirement"}) as changes:
            obj.long_name = new_name
            del obj.requirements[0]
            obj.requirements.insert(0, req)

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
        obj = clean_model.by_uuid(TEST_REQMODULE_UUID)

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


class TestRMReporter:
    CHANGES: list[auditing.Change] = [
        TEST_MODIFICATION,
        TEST_EXTENSION,
        TEST_DELETION,
    ]

    def test_store_change(self, clean_model: capellambse.MelodyModel):
        reporter = auditing.RMReporter(clean_model)

        reporter.store_change(self.CHANGES, "1", "category")

        assert reporter.store == {"1": self.CHANGES}
        assert reporter.categories["category"] == 1

    def test_store_change_raises_ValueError_if_change_cant_be_assigned_to_module(
        self, clean_model: capellambse.MelodyModel
    ):
        reporter = auditing.RMReporter(clean_model)
        change = auditing.Modification(
            "ddbef16d-ddb9-4162-934c-f1e40e6f8bed",
            attribute="name",
            new="New",
            old="Operational Analysis",
        )

        with pytest.raises(ValueError):
            reporter.store_change([change], "1", "category")

    def test_store_change_warns_about_change_to_unexpected_module(
        self,
        clean_model: capellambse.MelodyModel,
        caplog: pytest.LogCaptureFixture,
    ):
        reporter = auditing.RMReporter(clean_model)
        module_id = "different"

        with caplog.at_level(logging.WARNING):
            reporter.store_change(self.CHANGES, module_id, "category")

        assert len(caplog.records) == 3
        assert caplog.records[0].levelname == "WARNING"
        assert (
            f"Found changes to an unexpected RequirementsModule: "
            f"{self.CHANGES[0]} to 1"
        ) in caplog.text


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


def test_get_dependencies():
    dependencies = auditing.get_dependencies()

    assert dependencies[0].startswith("Python")
    assert dependencies[1].startswith("capellambse v")
    assert dependencies[2].startswith("lxml v")
    assert dependencies[3].startswith("pyYaml v")


@pytest.mark.parametrize(
    ["change", "uuid", "expected"],
    (
        pytest.param(
            TEST_MODIFICATION,
            TEST_REQFOLDER_UUID,
            f"{TEST_REQFOLDER_REPR} modified 'long_name' from '1' to 'New'.",
            id="Modification",
        ),
        pytest.param(
            TEST_EXTENSION,
            TEST_REQMODULE_UUID,
            f"{TEST_REQMODULE_REPR} extended 'folders' by "
            f"{TEST_REQFOLDER_REPR}.",
            id="Extension",
        ),
        pytest.param(
            TEST_DELETION,
            TEST_REQMODULE_UUID,
            f"{TEST_REQMODULE_REPR} deleted {TEST_REQFOLDER_REPR} from "
            "'folders'.",
            id="Deletion",
        ),
    ),
)
def test_formulate_statement(
    clean_model: capellambse.MelodyModel,
    change: auditing.Change,
    uuid: str,
    expected: str,
):
    obj = clean_model.by_uuid(uuid)

    statement = auditing.formulate_statement(change, obj)

    assert statement == expected


@pytest.mark.integtest
def test_create_commit_message(migration_model: capellambse.MelodyModel):
    req_uuid = "163394f5-c1ba-4712-a238-b0b143c66aed"
    reqtypesfolder_uuid = "a15e8b60-bf39-47ba-b7c7-74ceecb25c9c"
    dtdef_uuid = "686e198b-8baf-49f9-9d85-24571bd05d93"
    req = migration_model.by_uuid(req_uuid)
    req.parent.requirements.remove(req)
    changes: list[auditing.Change] = [
        auditing.Deletion(
            parent="9a9b5a8f-a6ad-4610-9e88-3b5e9c943c19",
            attribute="requirements",
            element=f"<Requirement 'Kind Requirement' ({req_uuid})>",
            uuid=req_uuid,
        ),
        auditing.Modification(
            parent=reqtypesfolder_uuid,
            attribute="identifier",
            new="Types",
            old="-2",
        ),
        auditing.Extension(
            parent=reqtypesfolder_uuid,
            attribute="data_type_definitions",
            element=f"<EnumerationDataTypeDefinition '' ({dtdef_uuid})>",
            uuid=dtdef_uuid,
        ),
    ]
    context = [
        (TestRMReporter.CHANGES, "1", "category1"),
        (changes, "project/space/example title", "category2"),
    ]
    tool_metadata = {
        "revision": "123",
        "tool": "tool version 1",
        "connector": "connector v1",
    }

    reporter = auditing.RMReporter(migration_model)
    for changes, module_id, module_category in context:
        reporter.store_change(changes, module_id, module_category)
    commit_message = reporter.create_commit_message(tool_metadata)

    assert commit_message.startswith(
        "Updated model with RM content from rev.123\n"
        "\n"
        "Synchronized 1 category1 and 1 category2:\n"
        "- 1: created: 1; updated: 1; deleted: 1; type-changes: 0\n"
        "- project/space/example title: created: 0; updated: 0; deleted: 1; type-changes: 2\n"
        "\n"
        "This was done using:\n"
        "- tool version 1\n"
        "- connector v1\n"
        f"- RM-Bridge v{__version__}\n"
    )
