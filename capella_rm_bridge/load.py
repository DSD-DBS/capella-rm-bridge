# SPDX-FileCopyrightText: Copyright DB Netz AG and the capella-rm-bridge contributors
# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import pathlib
import typing as t

import yaml


def load_yaml(config_path: pathlib.Path | str) -> dict[str, t.Any]:
    """Return Requirements Management (RM) Bridge YAML configuration.

    .. code-block::
        :caption: Example for config_path.yaml

        trackers: # List all trackers for which a snapshot should be exported
          - external-id : 25093
            capella-uuid: 3be8d0fc-c693-4b9b-8fa1-d59a9eec6ea4
            fields:
              - Capella ID
              - Type
              - Status
              - Color
              - Submitted at

        model:
            path: PATH/TO/YOUR_MODEL.aird

        # Additional sections which configure the snapshot importer
        # may also appear here

    Returns
    -------
    config
        The whole RM Bridge configuration.
    """
    return yaml.safe_load(
        pathlib.Path(config_path).read_text(encoding="utf-8")
    )
