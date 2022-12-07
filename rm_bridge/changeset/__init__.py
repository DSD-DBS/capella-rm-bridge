# SPDX-FileCopyrightText: Copyright DB Netz AG and the rm-bridge contributors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import collections.abc as cabc
import logging
import typing as t

import capellambse

from . import actiontypes, change

LOGGER = logging.getLogger(__name__)


def calculate_change_set(
    model: capellambse.MelodyModel,
    config: actiontypes.Config,
    snapshot: cabc.Sequence[actiontypes.TrackerSnapshot],
) -> list[dict[str, t.Any]]:
    r"""Return a list of actions for a given ``model`` and ``snapshot``.

    The ``ChangeSet`` stores the needed actions to synchronize the
    ``model`` with the ``snapshot``. The ``snapshot`` stores modules
    which correspond to ``reqif.RequirementsModule`` \s.
    """
    actions: list[dict[str, t.Any]] = []
    for tracker, tconfig in zip(snapshot, config["modules"]):
        try:
            tchange = change.TrackerChange(tracker, model, tconfig)
            actions.extend(tchange.actions)
        except (
            actiontypes.InvalidTrackerConfig,
            actiontypes.InvalidSnapshotModule,
            change.MissingRequirementsModule,
        ) as error:
            tid = tracker.get("id", "MISSING ID")
            LOGGER.error("Skipping module: %s", f"'{tid}'\n{error.args[0]}")
            continue

    return actions
