"""Typed document tree: the contract between parsers and everything downstream.

Every parser emits a `Document`. Summarization, chunking and indexing only read
this structure, so parsers can be swapped or compared without touching the rest.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterator

NODE_TYPES = {"document", "section", "paragraph", "list_item", "table", "row", "cell", "footnote"}


@dataclass
class Node:
    type: str
    text: str = ""
    title: str = ""
    level: int = 0
    children: list["Node"] = field(default_factory=list)
    attrs: dict[str, Any] = field(default_factory=dict)
    id: str = ""
    parent: "Node | None" = field(default=None, repr=False, compare=False)

    def __post_init__(self) -> None:
        if self.type not in NODE_TYPES:
            raise ValueError(f"unknown node type {self.type!r}")

    def add(self, child: "Node") -> "Node":
        child.parent = self
        self.children.append(child)
        return child

    def walk(self) -> Iterator["Node"]:
        yield self
        for c in self.children:
            yield from c.walk()

    def path(self) -> list[str]:
        """Section titles from the root to the nearest enclosing section (inclusive)."""
        out: list[str] = []
        node: Node | None = self
        while node is not None:
            if node.type == "section" and node.title:
                out.append(node.title)
            node = node.parent
        return list(reversed(out))

    def section(self) -> "Node | None":
        node = self if self.type == "section" else self.parent
        while node is not None and node.type != "section":
            node = node.parent
        return node

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {"id": self.id, "type": self.type}
        if self.title:
            d["title"] = self.title
        if self.text:
            d["text"] = self.text
        if self.level:
            d["level"] = self.level
        if self.attrs:
            d["attrs"] = self.attrs
        if self.children:
            d["children"] = [c.to_dict() for c in self.children]
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Node":
        n = cls(type=d["type"], text=d.get("text", ""), title=d.get("title", ""), level=d.get("level", 0),
                attrs=d.get("attrs", {}), id=d.get("id", ""))
        for c in d.get("children", []):
            n.add(cls.from_dict(c))
        return n


@dataclass
class Document:
    doc_id: str
    root: Node
    source: str = ""
    format: str = ""

    def assign_ids(self) -> None:
        counters: dict[str, int] = {}
        for n in self.root.walk():
            counters[n.type] = counters.get(n.type, 0) + 1
            n.id = f"{self.doc_id}#{n.type[0]}{counters[n.type]}"

    def to_dict(self) -> dict[str, Any]:
        return {"doc_id": self.doc_id, "source": self.source, "format": self.format, "root": self.root.to_dict()}

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Document":
        return cls(d["doc_id"], Node.from_dict(d["root"]), d.get("source", ""), d.get("format", ""))


class TreeBuilder:
    """Assemble a section hierarchy from a flat stream of headings and blocks."""

    def __init__(self, title: str) -> None:
        self.root = Node("document", title=title)
        self.stack: list[Node] = [self.root]

    @property
    def current(self) -> Node:
        return self.stack[-1]

    def heading(self, title: str, level: int) -> Node:
        level = max(1, level)
        while len(self.stack) > 1 and self.stack[-1].level >= level:
            self.stack.pop()
        sec = self.current.add(Node("section", title=title.strip(), level=level))
        self.stack.append(sec)
        return sec

    def block(self, node: Node) -> Node:
        return self.current.add(node)


def promote_single_title(root: Node) -> None:
    """If a document has exactly one top-level section, it is the document title, not a section.

    Without this, every citation repeats the title ("Runbook › Runbook › 3 Mitigation")."""
    sections = [c for c in root.children if c.type == "section"]
    if len(sections) != 1:
        return
    top = sections[0]
    if any(c.type not in ("section", "footnote") for c in root.children if c is not top):
        return
    root.title = top.title
    idx = root.children.index(top)
    moved = top.children
    for c in moved:
        c.parent = root
    root.children[idx : idx + 1] = moved
