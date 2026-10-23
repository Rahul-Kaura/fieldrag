"""Plain text with numbered headings ("4.2 Exceptions", "SECTION 3 - SCOPE")."""

from __future__ import annotations

import re

from ..ir import Node, TreeBuilder

NUMBERED = re.compile(r"^(\d+(?:\.\d+){0,5})\.?\s+([A-Z][^.!?]{1,90})$")
SECTION_WORD = re.compile(r"^(?:SECTION|ARTICLE|PART)\s+(\d+)\s*[-:.]?\s*(.*)$", re.I)
BULLET = re.compile(r"^\s*(?:[-*•]|\(?[a-z0-9]\))\s+(.*)$")


def parse_text(text: str, title: str = "") -> Node:
    tb = TreeBuilder(title)
    para: list[str] = []

    def flush() -> None:
        if para:
            tb.block(Node("paragraph", text=" ".join(para)))
            para.clear()

    lines = text.splitlines()
    first = next((i for i, l in enumerate(lines) if l.strip()), None)
    if first is not None and lines[first].strip().isupper():
        tb.root.title = lines[first].strip().title()
        lines = lines[first + 1 :]
    for raw in lines:
        line = raw.strip()
        if not line:
            flush()
            continue
        if m := NUMBERED.match(line):
            flush()
            tb.heading(f"{m.group(1)} {m.group(2).strip()}", m.group(1).count(".") + 1)
        elif m := SECTION_WORD.match(line):
            flush()
            tb.heading(line, 1)
        elif line.isupper() and 3 < len(line) < 80 and not para:
            flush()
            tb.heading(line.title(), 1)
        elif m := BULLET.match(raw):
            flush()
            tb.block(Node("list_item", text=m.group(1).strip()))
        else:
            para.append(line)
    flush()
    return tb.root
