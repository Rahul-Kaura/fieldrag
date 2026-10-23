"""Markdown: ATX headings, paragraphs, list items, pipe tables and footnotes."""

from __future__ import annotations

import re

from ..ir import Node, TreeBuilder
from ..tables import RawCell, resolve

HEADING = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")
LIST_ITEM = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+(.*)$")
FOOTNOTE_DEF = re.compile(r"^\[\^([^\]]+)\]:\s*(.*)$")
FOOTNOTE_REF = re.compile(r"\[\^([^\]]+)\]")
TABLE_SEP = re.compile(r"^\s*\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)*\|?\s*$")


def _split_row(line: str) -> list[str]:
    line = line.strip()
    if line.startswith("|"):
        line = line[1:]
    if line.endswith("|"):
        line = line[:-1]
    return [c.strip() for c in line.split("|")]


def parse_markdown(text: str, title: str = "") -> Node:
    lines = text.splitlines()
    tb = TreeBuilder(title)
    para: list[str] = []
    footnotes: list[Node] = []

    def flush() -> None:
        if para:
            text = " ".join(s.strip() for s in para)
            refs = FOOTNOTE_REF.findall(text)
            node = Node("paragraph", text=FOOTNOTE_REF.sub("", text).strip())
            if refs:
                node.attrs["footnotes"] = refs
            tb.block(node)
            para.clear()

    i = 0
    while i < len(lines):
        line = lines[i]
        if m := HEADING.match(line):
            flush()
            tb.heading(m.group(2), len(m.group(1)))
        elif m := FOOTNOTE_DEF.match(line):
            flush()
            footnotes.append(Node("footnote", text=m.group(2).strip(), attrs={"label": m.group(1)}))
        elif "|" in line and i + 1 < len(lines) and TABLE_SEP.match(lines[i + 1]):
            flush()
            header = [RawCell(c, header=True) for c in _split_row(line)]
            rows = [header]
            i += 2
            while i < len(lines) and "|" in lines[i] and lines[i].strip():
                rows.append([RawCell(c) for c in _split_row(lines[i])])
                i += 1
            tb.block(resolve(rows))
            continue
        elif m := LIST_ITEM.match(line):
            flush()
            tb.block(Node("list_item", text=m.group(1).strip()))
        elif not line.strip():
            flush()
        else:
            para.append(line)
        i += 1
    flush()
    root = tb.root
    for fn in footnotes:
        root.add(fn)
    if not root.title:
        first = next((n for n in root.walk() if n.type == "section"), None)
        root.title = first.title if first else ""
    return root
