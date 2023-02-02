# SPDX-FileCopyrightText: Copyright DB Netz AG and the capella-rm-bridge contributors
# SPDX-License-Identifier: Apache-2.0

"""A ``ChangeSet`` is a sequence of actions to be applied to a model.

The :py:func:`~capella_rm_bridge.changeset.calculate_change_set`
function calculates these actions from a given snapshot of supported
Requirement Management tools and config YAML file. With the
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
ERROR_MESSAGE_PREFIX = "Skipping module: {module_id}"


def _wrap_errors(module_id: int | str, errors: cabc.Sequence[str]) -> str:
    start = ERROR_MESSAGE_PREFIX.format(module_id=module_id)
    first_sep = len(start) * "="
    last_sep = len(errors[-1]) * "="
    return "\n".join((start, first_sep, *errors, last_sep))


def calculate_change_set(
    model: capellambse.MelodyModel,
    config: actiontypes.TrackerConfig,
    snapshot: actiontypes.TrackerSnapshot,
    safe_mode: bool = True,
    gather_logs: bool = True,
) -> tuple[list[dict[str, t.Any]], list[str]]:
    r"""Return a list of actions for a given ``model`` and ``snapshot``.

    The returned list (``ChangeSet``) stores the needed actions to
    synchronize the ``model`` with the content of the ``snapshot``. The
    ``snapshot`` stores a tracker or live-document which correspond to a
    ``reqif.RequirementsModule``.

    Parameters
    ----------
    model
        The Capella model to compare the snapshot against.
    config
        A configuration of the tracker or live-document for the
        calculated ``ChangeSet``.
    snapshot
        A snapshot of a tracker or live-document from the external tool.
    safe_mode
        If ``True`` no ``ChangeSet`` will be rendered iff atleast one
        error occurred during the change-calculation loop. If ``False``
        all change-actions of modules where errors occurred are
        dismissed.
    gather_logs
        If ``True`` all error messages are gathered in
        :attribute:`~capella_rm_bridge.changeset.change.TrackerChange.errors`
        instead of being immediately logged.

    Returns
    -------
    ChangeSet, errors

    See Also
    --------
    capella_rm_bridge.changeset.actiontypes.TrackerConfig :
        The expected keys and value types of a module.
    capella_rm_bridge.changeset.actiontypes.TrackerSnapshot :
        The expected keys and value types of a snapshot.
    """
    actions = list[dict[str, t.Any]]()
    errors = list[str]()
    module_id = snapshot.get("id", "MISSING ID")
    try:
        tchange = change.TrackerChange(
            snapshot, model, config, gather_logs=gather_logs
        )
        if tchange.errors:
            message = _wrap_errors(module_id, tchange.errors)
            errors.append(message)
        else:
            actions.extend(tchange.actions)
    except (
        actiontypes.InvalidTrackerConfig,
        actiontypes.InvalidSnapshotModule,
        change.MissingRequirementsModule,
    ) as error:
        if gather_logs:
            message = _wrap_errors(module_id, [error.args[0]])
            errors.append(message)
        else:
            prefix = ERROR_MESSAGE_PREFIX.format(module_id=module_id)
            LOGGER.error("%s. %s", prefix, error.args[0])

    if safe_mode and any(errors):
        actions = []
    return actions, errors
