# SPDX-FileCopyrightText: Copyright DB Netz AG and the rm-bridge contributors
# SPDX-License-Identifier: Apache-2.0

import pathlib

import capellambse
import pytest
from capellambse.extensions import reqif

from rm_bridge import load

TEST_DATA_PATH = pathlib.Path(__file__).parent / "data"
TEST_CONFIG = load.load_yaml(TEST_DATA_PATH / "config.yaml")
TEST_MODEL_PATH = TEST_DATA_PATH / TEST_CONFIG["model"]["path"]
TEST_REQ_MODULE_UUID = "3be8d0fc-c693-4b9b-8fa1-d59a9eec6ea4"
TEST_UUID_PREFIX = "00000000-0000-0000-0000-00000000000"


@pytest.fixture
def migration_model() -> capellambse.MelodyModel:
    return capellambse.MelodyModel(path=TEST_MODEL_PATH)


@pytest.fixture
def clean_model() -> capellambse.MelodyModel:
    model = capellambse.MelodyModel(path=TEST_MODEL_PATH)
    reqmodule = model.by_uuid(TEST_REQ_MODULE_UUID)
    del reqmodule.requirement_types_folders[0]
    del reqmodule.folders[0]
    return model


@pytest.fixture
def deletion_model(
    migration_model: capellambse.MelodyModel,
) -> capellambse.MelodyModel:
    dtdef = migration_model.by_uuid("f4b62994-37ac-45d6-add7-d320890e2969")
    dtdef.values[-1].long_name = "Non-Functional"
    reqtfolder = migration_model.by_uuid(
        "487eca4d-8e98-4598-8ec0-4cdbdcbebd03"
    )
    enum_dtdef = reqtfolder.data_type_definitions.create(
        "EnumerationDataTypeDefinition",
        long_name="Release",
        values=["Rel. 1", "Rel. 2"],
        uuid=f"{TEST_UUID_PREFIX}1",
    )
    reqtype = migration_model.by_uuid("e941a947-54ac-48e4-a383-af0b6994076d")
    enum_def = reqtype.attribute_definitions.create(
        "AttributeDefinitionEnumeration",
        long_name="Release",
        data_type=enum_dtdef,
        multi_valued=True,
        uuid=f"{TEST_UUID_PREFIX}2",
    )
    definition = reqtype.attribute_definitions.create(
        "AttributeDefinition",
        long_name="Test after migration",
        uuid=f"{TEST_UUID_PREFIX}3",
    )
    reqfolder = migration_model.by_uuid("8a814f64-70d1-4fe1-a648-54c83c03d05b")
    reqfolder.long_name = "Non-Functional Requirements"
    reqfolder.text = "<p>Changed Test Description</p>"
    iddef = reqtype.attribute_definitions.by_long_name(
        "Capella ID", single=True
    )
    reqfolder.attributes.create(
        "String", value="RF-NFNC-00001", definition=iddef
    )
    reqfolder.attributes.create(
        "Enum",
        values=enum_dtdef.values,
        definition=enum_def,
        uuid=f"{TEST_UUID_PREFIX}4",
    )
    attr = migration_model.by_uuid("8848878e-faf3-4b9a-b5fb-b99df5faf588")
    attr.value = "R-NFNC-00001"
    req = migration_model.by_uuid("1cab372a-62cf-443b-b36d-77e66e5de97d")
    req.attributes.create(
        "String",
        definition=definition,
        value="New",
        uuid=f"{TEST_UUID_PREFIX}5",
    )
    assert isinstance(reqmodule := reqfolder.parent, reqif.RequirementsModule)
    subfolder = reqmodule.folders.create(
        identifier="5442",
        long_name="Kinds",
        type=reqtype,
        uuid=f"{TEST_UUID_PREFIX}6",
    )
    del reqfolder.folders[0]
    subf_req = subfolder.requirements.create(
        identifier="5443", long_name="Kind Requirement", type=reqtype
    )
    subf_req.attributes.create("String", value="R-FNC-00002", definition=iddef)
    subf_req.attributes.create(
        "Enum", values=dtdef.values[:1], definition=dtdef
    )
    return migration_model
