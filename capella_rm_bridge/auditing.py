# SPDX-FileCopyrightText: Copyright DB Netz AG and the capella-rm-bridge contributors
# SPDX-License-Identifier: Apache-2.0

"""Functionality for reporting changes during model modification."""
from __future__ import annotations

import collections
import collections.abc as cabc
import dataclasses
import logging
import sys
import textwrap
import typing as t
from importlib import metadata as imm

import capellambse
from capellambse import helpers
from capellambse.extensions import reqif
from capellambse.model import common

from . import __version__

LOGGER = logging.getLogger(__name__)
DEPENDENCIES = ("capellambse", "lxml", "pyYaml")


@dataclasses.dataclass
class _Change:
    """Base dataclass for changes."""

    parent: str
    attribute: str


@dataclasses.dataclass
class Modification(_Change):
    """Data that describes the context for a modification event."""

    new: t.Any
    old: t.Any


@dataclasses.dataclass
class Extension(_Change):
    """Data that describes the context for an extension event."""

    element: str
    uuid: str


class Deletion(Extension):
    """Data that describes the context for a deletion event."""


Change = t.Union[Modification, Extension, Deletion]


@dataclasses.dataclass
class _SafeChange:
    """Base dataclass for safe-dumpable changes."""

    _type: t.Literal["Modification"] | t.Literal["Extension"] | t.Literal[
        "Deletion"
    ]
    parent: str
    attribute: str


@dataclasses.dataclass
class _SafeExtensionOrDeletion(_SafeChange):
    """Safe data describing context for a non-modification event."""

    element: str
    uuid: str


@dataclasses.dataclass
class _SafeModification(_SafeChange):
    """Safe data describing context for a modification event."""

    new: str | list[str] | dict[str, t.Any]
    old: str | list[str] | dict[str, t.Any]


class ChangeAuditor:
    """Audits changes to ModelElements via its Accessors.

    .. warning::
        This will permanently add an audit hook to the global hook
        table. The auditor will keep the model alive, which may consume
        excessive memory. To avoid this, call the auditor object's
        ``detach()`` method once you are done with it. This is
        automatically done if you use it as a context manager.

    Examples
    --------
    >>> with ChangeAuditor(model) as changes:
    ...     comp = model.la.all_components.by_name("Hogwarts")
    ...     comp.name = "Not Hogwarts anymore"
    ...     comp.allocated_functions.insert(
    ...         0, model.la.all_functions[0]
    ...     )
    ...     del comp.components[0]
    ...
    >>> changes
    [
        Modification(
            parent="0d2edb8f-fa34-4e73-89ec-fb9a63001440",
            attribute="name",
            new="Not Hogwarts anymore",
            old="Hogwarts",
        ),
        Extension(
            parent="0d2edb8f-fa34-4e73-89ec-fb9a63001440",
            attribute="allocated_functions",
            element="<LogicalFunction 'Root Logical Function' (f2...)>",
            uuid="f28ec0f8-f3b3-43a0-8af7-79f194b29a2d",
        ),
        Deletion(
            parent="0d2edb8f-fa34-4e73-89ec-fb9a63001440",
            attribute="components",
            element="<LogicalComponent 'Campus' (6583b560-6d2f-...)>",
            uuid="6583b560-6d2f-4190-baa2-94eef179c8ea",
        )
    ]

    Filtering the context by class-names:

    >>> with ChangeAuditor(model, {"LogicalComponent"}) as changes:
    ...     comp = model.la.all_components.by_name("Hogwarts")
    ...     comp.name = "Not Hogwarts anymore"
    ...     fnc = model.la.all_functions[0]
    ...     fnc.name = "Not Hogwarts anymore"
    ...
    >>> changes
    [
        Modification(
            parent="0d2edb8f-fa34-4e73-89ec-fb9a63001440",
            attribute="name",
            new="Not Hogwarts anymore",
            old="Hogwarts",
        )
    ]

    Securing writable context with the
    :func:`~capella_rm_bridge.auditing.dump` function:

    >>> with ChangeAuditor(model) as changes:
    ...     comp = model.la.all_components.by_name("Hogwarts")
    ...     comp.name = "Not Hogwarts anymore"
    ...     comp.allocated_functions.insert(
    ...         0, model.la.all_functions[0]
    ...     )
    ...     del comp.components[0]
    ...
    >>> dump(changes)
    [
        {
            "_type": "Modification,
            "parent": "0d2edb8f-fa34-4e73-89ec-fb9a63001440",
            "attribute": "name",
            "new": "Not Hogwarts anymore",
            "old": "Hogwarts"
        },
        {
            "_type": "Extension",
            "parent": "0d2edb8f-fa34-4e73-89ec-fb9a63001440",
            "attribute": "allocated_functions",
            "element": "<LogicalFunction 'Fnc' (f28ec0f8-f3b3-43a...)>",
            "uuid": "f28ec0f8-f3b3-43a0-8af7-79f194b29a2d"
        },
        {
            "_type": "Deletion",
            "parent": "0d2edb8f-fa34-4e73-89ec-fb9a63001440",
            "attribute": "components",
            "element": "<LogicalComponent 'Comp' (6583b560-6d2f-4...)>",
            "uuid": "6583b560-6d2f-4190-baa2-94eef179c8ea"
        }
    ]
    """

    def __init__(
        self,
        model: capellambse.MelodyModel,
        classes: cabc.Container[str] = (),
    ) -> None:
        r"""Initialize a ChangeAuditor.

        Parameters
        ----------
        model
            A model instance to audit changes for.
        classes
            An optional class-name filter. Only changes to
            ``ModelObject``\ s with matching class-type are stored in
            context.
        """
        self.model: capellambse.MelodyModel | None = model
        self.classes = classes or helpers.EverythingContainer()
        self.context = list[Change]()

        sys.addaudithook(self.__audit)

    def __enter__(self) -> list[Change]:
        return self.context

    def __exit__(self, *_: t.Any) -> None:
        self.detach()

    def detach(self) -> None:
        """Delete the reference to the model instance."""
        self.model = None

    def __audit(self, event: str, args: tuple[t.Any, ...]) -> None:
        change_events: dict[str, type[Change]] = {
            "capellambse.setattr": Modification,
            "capellambse.setitem": Modification,
            "capellambse.delete": Deletion,
            "capellambse.create": Extension,
            "capellambse.insert": Extension,
        }
        if EventType := change_events.get(event):
            if args[0]._model is not self.model:
                return

            if type(args[0]).__name__ not in self.classes:
                return

            if event.endswith("setattr"):
                assert len(args) == 3
                obj, attr_name, value = args
                oval = getattr(obj, attr_name)
                nrepr = self._get_value_repr(value)
                orepr = self._get_value_repr(oval)
                events = [EventType(obj.uuid, attr_name, nrepr, orepr)]
            elif event.endswith("setitem"):
                assert len(args) == 4
                obj, attr_name, index, value = args
                nrepr = self._get_value_repr(value)
                oval = getattr(obj, attr_name)[index]
                orepr = self._get_value_repr(oval)
                events = [EventType(obj.uuid, attr_name, nrepr, orepr)]
            elif event.endswith("delete"):
                assert len(args) == 3
                obj, attr_name, index = args
                assert isinstance(index, int) or index is None
                oval = getattr(obj, attr_name)
                if index is not None:
                    oval = oval[index]

                if not isinstance(oval, common.GenericElement):
                    assert isinstance(oval, common.ElementList)
                    events = []
                    assert EventType is Deletion
                    for elt in oval:
                        event_type = EventType(
                            obj.uuid,
                            attr_name,
                            self._get_value_repr(elt),
                            elt.uuid,
                        )
                        events.append(event_type)
                else:
                    orepr = self._get_value_repr(oval)
                    events = [EventType(obj.uuid, attr_name, orepr, oval.uuid)]
            elif event.endswith("insert"):
                assert len(args) == 4
                obj, attr_name, _, value = args
                nrepr = self._get_value_repr(value)
                assert isinstance(value, common.GenericElement)
                events = [EventType(obj.uuid, attr_name, nrepr, value.uuid)]
            elif event.endswith("create"):
                assert len(args) == 3
                obj, attr_name, value = args
                repr = self._get_value_repr(value)
                events = [EventType(obj.uuid, attr_name, repr, value.uuid)]

            self.context.extend(events)

    def _get_value_repr(self, value: t.Any) -> str | t.Any:
        if hasattr(value, "_short_repr_"):
            return value._short_repr_()
        return value


def dump(context: list[Change]) -> list[dict[str, t.Any]]:
    """Convert a ``ChangeContext`` into something savely writable."""
    return [_convert_change(change) for change in context]


def _convert_change(change: _Change) -> dict[str, t.Any]:
    converted: _SafeExtensionOrDeletion | _SafeModification
    if isinstance(change, Modification):
        converted = _SafeModification(
            _type="Modification",
            parent=change.parent,
            attribute=change.attribute,
            new=_convert_obj(change.new),
            old=_convert_obj(change.old),
        )
    else:
        assert isinstance(change, (Extension, Deletion))
        assert isinstance(change.element, str)
        converted = _SafeExtensionOrDeletion(
            _type=change.__class__.__name__,  # type: ignore[arg-type]
            parent=change.parent,
            attribute=change.attribute,
            element=change.element,
            uuid=change.uuid,
        )

    return dataclasses.asdict(converted)


def _convert_obj(
    obj: common.GenericElement | common.ElementList | t.Any,
) -> str | list[str] | t.Any:
    if isinstance(obj, common.GenericElement):
        return obj.uuid
    elif isinstance(obj, common.ElementList):
        return [o.uuid for o in obj]
    return obj


LiveDocID = str
TrackerID = str
UUID = str


class RMReporter:
    """Stores and reports on all changes that were made to a model."""

    model: capellambse.MelodyModel
    """The model instance that was changed."""
    store: dict[LiveDocID | TrackerID, list[Change]]
    """A change-store that maps identifiers to a sequence of changes."""
    categories: dict[str, int]
    """A dictionary that maps the category name to its counter."""

    def __init__(self, model: capellambse.MelodyModel) -> None:
        self.model = model
        self.store = dict[t.Union[LiveDocID, TrackerID], list[Change]]()

        self.categories: dict[str, int] = collections.defaultdict(lambda: 0)

    def store_change(
        self,
        changes: cabc.Iterable[Change],
        module_id: str,
        module_category: str,
    ) -> None:
        """Assigns the RequirementsModule to changes and stores them."""
        self.categories[module_category] += 1

        for change in changes:
            parent_id = self._assign_module(change)
            if not parent_id:
                raise ValueError(  # XXX Maybe custom exception but what name?
                    f"Can't assign RequirementModule to change {change!r}"
                )

            if parent_id != module_id:
                LOGGER.warning(
                    "Found changes to an unexpected RequirementsModule: "
                    "%r to %s",
                    change,
                    parent_id,
                )

            if parent_id not in self.store:
                self.store[parent_id] = [change]
            else:
                self.store[parent_id].append(change)

    def _assign_module(self, change: Change) -> LiveDocID | TrackerID | None:
        try:
            obj = self.model.by_uuid(change.parent)
            while not isinstance(obj, reqif.CapellaModule):
                obj = obj.parent
            return obj.identifier
        except (KeyError, AttributeError):
            return None

    def create_commit_message(self, tool_metadata: dict[str, str]) -> str:
        """Return a commit message for all changes in the store.

        Parameters
        ----------
        config
            Configuration dictionary for the RM Bridge
        tool_metadata
            Metadata of the requirements management tool from the
            snapshot.

        Returns
        -------
        commit_message
        """
        list_lines = list[str]()
        for module_id, changes in self.store.items():
            ext_count, mod_count, del_count, type_count = self._count_changes(
                changes
            )
            counts = (
                f"created: {ext_count}",
                f"updated: {mod_count}",
                f"deleted: {del_count}",
                f"type-changes: {type_count}",
            )
            list_lines.append(f"- {module_id}: {'; '.join(counts)}")

        if not list_lines:
            summary = "No changes identified"
            main = (
                "There were no modifications, extensions or deletions from "
                "the previous revision of RM content.\n"
            )
        else:
            summary = "Updated model with RM content"
            main_message = generate_main_message(self.categories.items())
            main = "\n".join((main_message, "\n".join(list_lines) + "\n"))

        summary = f"{summary} from rev.{tool_metadata['revision']}\n"
        rm_bridge_dependencies = get_dependencies()
        dependencies = "\n".join(
            (
                "This was done using:",
                f"- {tool_metadata['tool']}",
                f"- {tool_metadata['connector']}",
                f"- RM-Bridge v{__version__}",
                *[f"- {dep}" for dep in rm_bridge_dependencies],
            )
        )
        return "\n".join((summary, main, dependencies))

    def _count_changes(
        self, changes: cabc.Iterable[Change]
    ) -> tuple[int, int, int, int]:
        ext_count = mod_count = del_count = type_count = 0
        for change in changes:
            if self._is_reqtype_change(change):
                type_count += 1
            elif isinstance(change, Deletion):  # type: ignore[unreachable]
                del_count += 1
            elif isinstance(change, Extension):
                ext_count += 1
            elif isinstance(change, Modification):
                mod_count += 1
            else:
                assert False
        return ext_count, mod_count, del_count, type_count

    def _is_reqtype_change(self, change: Change) -> bool:
        if isinstance(change, (Modification, Deletion)):
            obj = self.model.by_uuid(change.parent)
        elif isinstance(change, Extension):
            obj = self.model.by_uuid(change.uuid)

        return type(obj) in {
            reqif.AttributeDefinition,
            reqif.AttributeDefinitionEnumeration,
            reqif.DataTypeDefinition,
            reqif.EnumerationDataTypeDefinition,
            reqif.EnumValue,
            reqif.ModuleType,
            reqif.RelationType,
            reqif.CapellaTypesFolder,
            reqif.RequirementType,
        }

    def get_change_report(self) -> str:
        """Return an audit report of all changes in the store."""
        report_store = self._store_group_by("parent")
        change_statements = list[str]()
        for identifier, changes in report_store.items():
            ext_count = len([c for c in changes if isinstance(c, Extension)])
            mod_count = len(
                [c for c in changes if isinstance(c, Modification)]
            )
            del_count = len([c for c in changes if isinstance(c, Deletion)])
            obj = self.model.by_uuid(identifier)
            title = obj._short_repr_()
            overview = (
                f"Extensions: {ext_count}, Modifications: {mod_count}, "
                f"Deletions: {del_count}"
            )
            ov_title = "In-Depth"
            ov = (len(overview) - len(ov_title)) // 2
            indepth_title = "-" * ov + ov_title
            if len(overview) % 2 != 0:
                indepth_title += "-" * (ov + 1)
            else:
                indepth_title += "-" * ov

            statement = "\n".join(
                [title, "=" * len(title), overview, indepth_title]
                + [formulate_statement(change, obj) for change in changes]
            )
            change_statements.append(f"{statement}\n")

        return "\n".join(change_statements)

    def _store_group_by(self, group: str) -> dict[UUID, list[Change]]:
        grouped_store: dict[UUID, list[Change]] = collections.defaultdict(list)
        for changes in self.store.values():
            for change in changes:
                key = getattr(change, group)
                grouped_store[key].append(change)
        return grouped_store


def generate_main_message(categories: cabc.Iterable[tuple[str, int]]) -> str:
    """Return the main commit message corpus listing all categories."""
    assert (sorted_categories := sorted(categories))
    strings = [f"{x[1]} {x[0]}" for x in sorted_categories]
    if len(strings) == 1:
        result = strings[0]
    else:
        result = ", ".join(strings[:-1])
        result += " and " + strings[-1]

    return "\n".join(textwrap.wrap(f"Synchronized {result}:", 72))


def get_dependencies() -> list[str]:
    """Return all major dependencies with their current version."""
    py_version = sys.version.split(" ", maxsplit=1)[0]
    dependencies = [f"{dep} v{imm.version(dep)}" for dep in DEPENDENCIES]
    dependencies.insert(0, f"Python {py_version}")
    return dependencies


def formulate_statement(change: Change, obj: reqif.ReqIFElement) -> str:
    """Return an audit statement about the given change."""
    source = obj._short_repr_()
    if isinstance(change, Deletion):
        target = change.element
        return f"{source} deleted {target} from {change.attribute!r}."
    elif isinstance(change, Modification):
        return (
            f"{source} modified {change.attribute!r} from "
            f"{change.old!r} to {change.new!r}."
        )
    else:
        target = change.element
        return f"{source} extended {change.attribute!r} by {target}."
