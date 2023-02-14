# SPDX-FileCopyrightText: Copyright DB Netz AG and the capella-rm-bridge contributors
# SPDX-License-Identifier: Apache-2.0

"""Main entry point into the RM Bridge Bot."""
from __future__ import annotations

import collections.abc as cabc
import logging
import pathlib
import sys
import typing as t

import capellambse
import click
import yaml
from capellambse import decl

from capella_rm_bridge import changeset

from . import auditing

CHANGE_FOLDER_PATH = pathlib.Path("change-sets")
CHANGE_FILENAME = "change-set.yaml"
CHANGE_HISTORY_PATH = pathlib.Path("change.history")
COMMIT_MSG_PATH = pathlib.Path("commit-message.txt")
ERROR_PATH = pathlib.Path("change-errors.txt")
LOGGER = logging.getLogger(__name__)


def create_errors_statement(errors: cabc.Iterable[str]) -> str:
    """Return a commit message for errors from the ``ChangeSet`` calc."""
    return "\n".join(errors)


def write_change_set(change: str, module: dict[str, t.Any]) -> pathlib.Path:
    """Create a change-set.yaml underneath the change-sets folder."""
    CHANGE_FOLDER_PATH.mkdir(parents=True, exist_ok=True)
    mid = module["id"].replace("/", "~")
    path = CHANGE_FOLDER_PATH / f"{mid}-{CHANGE_FILENAME}"
    if path.is_file():
        path.unlink(missing_ok=True)

    path.write_text(change, encoding="utf8")
    LOGGER.info("Change-set file %s written.", str(path))
    return path


@click.command()
@click.option(
    "-c",
    "--config",
    "conffile",
    type=click.File(encoding="utf8"),
    required=True,
    help="Configuration file",
)
@click.option(
    "-s",
    "--snapshot",
    "snapshotfile",
    type=click.File(encoding="utf8"),
    required=True,
    help="Snapshot file of RM content to migrate.",
)
@click.option(
    "-n",
    "--dry-run",
    is_flag=True,
    default=False,
    help="Prohibit writing model modifications and output commit message to "
    "stdout.",
)
@click.option(
    "--push",
    is_flag=True,
    default=False,
    help="Push made model modifications back to the remote.",
)
@click.option(
    "--pull/--no-pull",
    is_flag=True,
    default=True,
    help="Pull the latest changes from remote.",
)
@click.option(
    "--force",
    is_flag=True,
    default=False,
    help="If a non RequirementModule-error was encountered only the object "
    "and all related objects will be skipped. Intact objects will still be "
    "synchronized",
)
@click.option(
    "--gather-logs/--no-gather-logs",
    is_flag=True,
    default=True,
    help="Gather logging messages, instead of printing them on events "
    "immediatly.",
)
@click.option(
    "--save-change-history/--no-save-change-history",
    is_flag=True,
    default=True,
    help="Export summarizing report of all changes into a .history file. "
    "Implies --gather-logs.",
)
@click.option(
    "--save-error-log/--no-save-error-log",
    is_flag=True,
    default=True,
    help="Export all errors during ChangeSet calculation into a .log file.",
)
@click.option(
    "--verbose", "-v", count=True, help="Show logging entries on info-level."
)
def main(
    conffile: t.TextIO,
    snapshotfile: t.TextIO,
    dry_run: bool,
    push: bool,
    pull: bool,
    force: bool,
    gather_logs: bool,
    save_change_history: bool,
    save_error_log: bool,
    verbose: bool,
) -> None:
    """RM Bridge synchronization CLI.

    ░█▀▀░█▀▀░▀█▀░░░░░░░░░█▀▄░█▀▄░░░█▀█░█▀▀░▀█▀░▀▀█░░░█▀█░█▀▀
    ░▀▀█░█▀▀░░█░░░░▄▄▄░░░█░█░█▀▄░░░█░█░█▀▀░░█░░▄▀░░░░█▀█░█░█
    ░▀▀▀░▀▀▀░░▀░░░░░░░░░░▀▀░░▀▀░░░░▀░▀░▀▀▀░░▀░░▀▀▀░░░▀░▀░▀▀▀

    This is the command-line-interface for the RM Bridge synchronization
    of requirements managed in an external Requirements Management Tool
    to Capella.
    """
    if save_change_history:
        gather_logs = True

    if verbose == 1:
        logging.basicConfig(level=logging.INFO)
    elif verbose >= 2:
        logging.basicConfig(level=logging.DEBUG)
    else:
        logging.basicConfig(level=logging.WARNING)

    config = yaml.safe_load(conffile)
    params = config["model"]
    if "git" in config["model"]["path"]:
        params["update_cache"] = pull

    model = capellambse.MelodyModel(**params)

    snapshot = yaml.safe_load(snapshotfile)
    reporter = auditing.RMReporter(model)
    for module, tconfig in zip(snapshot["modules"], config["live-docs"]):
        change_set, errors = changeset.calculate_change_set(
            model,
            tconfig,
            module,
            force=force,
            gather_logs=gather_logs,
        )

        if change_set:
            change = decl.dump(change_set)
            change_path = write_change_set(change, module)
            with auditing.ChangeAuditor(model) as changed_objs:
                decl.apply(model, change_path)

            reporter.store_change(
                changed_objs, module["id"], module["category"]
            )

    if force or not errors:
        commit_message = reporter.create_commit_message(snapshot["metadata"])
        COMMIT_MSG_PATH.write_text(commit_message, encoding="utf8")
        print(commit_message)
        if reporter.store and not dry_run:
            model.save(
                push=push, commit_msg=commit_message, push_options=["skip.ci"]
            )

    if errors:
        error_statement = create_errors_statement(errors)
        print(error_statement)
        if save_error_log:
            ERROR_PATH.write_text(error_statement, encoding="utf8")
            LOGGER.info("Change-errors file %s written.", ERROR_PATH)

        sys.exit(1)

    report = reporter.get_change_report()
    if report and save_change_history:
        CHANGE_HISTORY_PATH.write_text(report, encoding="utf8")
        LOGGER.info("Change-history file %s written.", CHANGE_HISTORY_PATH)
    else:
        print(report)


if __name__ == "__main__":
    main()  # pylint: disable=no-value-for-parameter
