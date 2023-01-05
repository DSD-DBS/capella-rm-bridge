# SPDX-FileCopyrightText: Copyright DB Netz AG and the rm-bridge contributors
# SPDX-License-Identifier: Apache-2.0

"""Functionality for reporting changes during model modification."""
from __future__ import annotations

import collections.abc as cabc
import dataclasses
import sys
import typing as t

import capellambse
from capellambse import helpers
from capellambse.model import common


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
        self.classes = classes or helpers.EverythingContainer()
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
