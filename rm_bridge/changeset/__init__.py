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
    which correspond to ``reqif.RequirementsModule``\ s.
    """
    trackers = config["trackers"]
    actions: list[dict[str, t.Any]] = []
    for tracker in snapshot:
        tconfig = next(
            ctracker
            for ctracker in trackers
            if str(ctracker["external-id"]) == str(tracker["id"])
        )
        tchange = change.TrackerChange(tracker, model, tconfig)
        tchange.calculate_change()
        actions.extend(tchange.actions)  # type: ignore[arg-type]
    return actions
