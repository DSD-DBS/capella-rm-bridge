# SPDX-FileCopyrightText: Copyright DB Netz AG and the rm-bridge contributors
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
from capellambse import helpers as cap_helpers
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


class _ChangeBuilder(t.NamedTuple):
    uuid: str
    attr_name: str
    value: t.Any
    element: str | None


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

    Securing writable context with the :func:`~rm_bridge.auditing.dump`
    function:

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
        self.classes = classes or cap_helpers.EverythingContainer()
        self.context = list[Change]()

        sys.addaudithook(self.__audit)

    def __enter__(self) -> list[Change]:
        return self.context

    def __exit__(self, *_: t.Any) -> None:
        self.detach()

    def detach(self) -> None:
        self.model = None

    def __audit(self, event: str, args: tuple[t.Any, ...]) -> None:
        if event in {"capellambse.set_item", "capellambse.set_attribute"}:
            if change := self._check_event(args):
                new_value, old_value = change.value
                uuid = new_value if change.attr_name == "uuid" else None

                self.context.append(
                    Modification(
                        uuid or change.uuid,
                        change.attr_name,
                        new_value,
                        old_value,
                    ),
                )
        elif event == "capellambse.delete_item":
            if change := self._check_event(args):
                assert change.element is not None
                self.context.append(
                    Deletion(
                        change.uuid,
                        change.attr_name,
                        change.element,
                        change.value.uuid,
                    )
                )
        elif event in {
            "capellambse.create",
            "capellambse.create_item",
            "capellambse.insert_item",
        }:
            if change := self._check_event(args):
                assert change.element is not None
                self.context.append(
                    Extension(
                        change.uuid,
                        change.attr_name,
                        change.element,
                        change.value.uuid,
                    )
                )
        else:
            return

    def _check_event(self, args: tuple[t.Any, ...]) -> _ChangeBuilder | None:
        if len(args) == 3:
            obj, attr_name, value = args
        else:
            obj, attr_name, new, old = args
            value = (new, old)

        class_name, attr_name = attr_name.split(".")
        if class_name in self.classes:
            if isinstance(value, common.GenericElement):
                element = value._short_repr_()
            else:
                element = None

            return _ChangeBuilder(obj.uuid, attr_name, value, element)
        return None


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
    def __init__(self, model: capellambse.MelodyModel) -> None:
        self.model = model
        self.store = dict[LiveDocID | TrackerID, list[Change]]()

        self.categories: dict[str, int] = collections.defaultdict(lambda: 0)

    def store_change(
        self,
        changes: cabc.Iterable[Change],
        module_id: str,
        module_category: str,
    ) -> None:
        """Assign the RequirementsModule to changes and store them."""
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

            self.store[parent_id].append(change)

    def _assign_module(self, change: Change) -> LiveDocID | TrackerID:
        try:
            obj = self.model.by_uuid(change.parent)
            while not isinstance(obj, reqif.RequirementsModule):
                obj = obj.parent
        except KeyError:
            ...

        return obj.identifier

    def create_commit_message(self, tool_metadata: dict[str, str]) -> str:
        """Return a commit message for the RM Bridge Bot.

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

        summary = (
            f"Updated model with RM content from rev."
            f"{tool_metadata['revision']} [skip ci]\n"
        )
        main_message = generate_main_message(self.categories.items())
        main = "\n".join((main_message, "\n".join(list_lines) + "\n"))
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
            elif isinstance(change, Extension):
                ext_count += 1
            elif isinstance(change, Modification):
                mod_count += 1
            elif isinstance(change, Deletion):  # type: ignore[unreachable]
                del_count += 1
            else:
                assert False
        return ext_count, mod_count, del_count, type_count

    def _is_reqtype_change(self, change: Change) -> bool:
        if isinstance(change, Modification):
            obj = self.model.by_uuid(change.parent)
        else:
            obj = self.model.by_uuid(change.uuid)

        return type(obj).__name__ in {
            "AttributeDefinition",
            "AttributeDefinitionEnumeration",
            "DataTypeDefinition",
            "EnumerationDataTypeDefinition",
            "EnumValue",
            "ModuleType",
            "RelationType",
            "RequirementsTypesFolder",
            "RequirementType",
        }

    def get_change_report(self) -> str:
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


def generate_main_message(iterable: cabc.Iterable[tuple[str, int]]) -> str:
    sorted_iterable = sorted(iterable, key=lambda x: x[0])
    assert sorted_iterable
    strings = [f"{x[1]} {x[0]}" for x in sorted_iterable]
    if len(strings) == 1:
        result = strings[0]
    else:
        result = ", ".join(strings[:-1])
        result += " and " + strings[-1]

    return "\n".join(textwrap.wrap(f"Synchronized {result}:", 72))


def get_dependencies() -> list[str]:
    py_version = sys.version.split(" ", maxsplit=1)[0]
    dependencies = [f"{dep} v{imm.version(dep)}" for dep in DEPENDENCIES]
    dependencies.insert(0, f"Python {py_version}")
    return dependencies


def formulate_statement(change: Change, obj: reqif.ReqIFElement) -> str:
    source = obj._short_repr_()
    if isinstance(change, Deletion):
        target = change.element
        return f"{source!r} deleted {target} from {change.attribute!r}."
    elif isinstance(change, Modification):
        return (
            f"{source!r} modified {change.attribute!r} from "
            f"{change.old!r} to {change.new!r}."
        )
    else:
        target = change.element
        return f"{source!r} extended {change.attribute!r} by {target!r}."
