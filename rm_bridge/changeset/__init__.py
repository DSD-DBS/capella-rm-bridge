# SPDX-FileCopyrightText: Copyright DB Netz AG and the rm-bridge contributors
# SPDX-License-Identifier: Apache-2.0
"""A ``ChangeSet`` is a sequence of actions to be applied to a model.

The :py:func:`~rm_bridge.changeset.calculate_change_set` function
calculates these actions from a given snapshot of supported Requirement
Management tools and config YAML file. With the
:ref:`declarative modelling <declarative-modelling>` feature of
capellambse a :external:class:`~capellambse.model.MelodyModel` can be
altered with :external:func:`capellambse.decl.apply`.
"""
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

    Parameters
    ----------
    model
        The ``model`` for comparison with the given ``snapshot``.
    config
        A configuration dictionary that stores the information on which
        :external:class:`~capellambse.extensions.reqif.elements.RequirementsModule`\
        s are taken for comparison.
    snapshot
        A sequence of module snapshots based on the content from the
        external RM tool.

    Returns
    -------
    actions
        The sequence of actions to synchronize Requirements of the RM
        tool to a Capela model.

    See Also
    --------
    rm_bridge.changeset.actiontypes.TrackerConfig :
        The expected keys and value types of a module.
    rm_bridge.changeset.actiontypes.TrackerSnapshot :
        The expected keys and value types of a snapshot.

    """
    actions: list[dict[str, t.Any]] = []
    for tracker, tconfig in zip(snapshot, config["modules"]):
        try:
            tchange = change.TrackerChange(tracker, model, tconfig)
            actions.extend(tchange.actions)
        except change.MissingRequirementsModule:
            continue

    return actions
