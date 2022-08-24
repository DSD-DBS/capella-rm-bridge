# SPDX-FileCopyrightText: Copyright DB Netz AG and the rm-bridge contributors
# SPDX-License-Identifier: Apache-2.0

import pathlib

from rm_bridge import load

TEST_DATA_PATH = pathlib.Path(__file__).parent / "data"
TEST_CONFIG = load.load_yaml(TEST_DATA_PATH / "config.yaml")
