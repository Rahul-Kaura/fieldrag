"""DOCX (Office Open XML) parsed with the standard library.

Headings come from paragraph styles (Title, Heading1..Heading9). Tables keep
horizontal merges (w:gridSpan) and vertical merges (w:vMerge restart/continue),
which is exactly where generic text extraction attaches values to the wrong header.
Footnotes are read from word/footnotes.xml and linked by id.
"""

from __future__ import annotations

import io
import re
import zipfile
import xml.etree.ElementTree as ET

from ..ir import Node, TreeBuilder
from ..tables import RawCell, resolve

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
HEADING_STYLE = re.compile(r"^(?:Heading|heading)\s?(\d)$")


def _text(el: ET.Element) -> str:
    parts: list[str] = []
    for node in el.iter():
        if node.tag == f"{W}t" and node.text:
            parts.append(node.text)
        elif node.tag in (f"{W}tab",):
            parts.append(" ")
        elif node.tag in (f"{W}br", f"{W}cr"):
            parts.append(" ")
    return " ".join("".join(parts).split())


def _style(p: ET.Element) -> str:
    ps = p.find(f"{W}pPr/{W}pStyle")
    return ps.get(f"{W}val", "") if ps is not None else ""


def _is_list(p: ET.Element) -> bool:
    return p.find(f"{W}pPr/{W}numPr") is not None or _style(p).lower().startswith("list")


def _footnote_refs(p: ET.Element) -> list[str]:
    return [r.get(f"{W}id", "") for r in p.iter(f"{W}footnoteReference")]


def _table(tbl: ET.Element) -> list[list[RawCell]]:
    """Convert w:tbl into RawCells, folding vMerge continuations into the cell above's rowspan."""
    grid_rows: list[list[tuple[int, RawCell | None]]] = []  # (start_col, cell or None if continuation)
    for tr in tbl.findall(f"{W}tr"):
        header_row = tr.find(f"{W}trPr/{W}tblHeader") is not None
        col = 0
        row: list[tuple[int, RawCell | None]] = []
        for tc in tr.findall(f"{W}tc"):
            pr = tc.find(f"{W}tcPr")
            span = 1
            vmerge = None
            if pr is not None:
                gs = pr.find(f"{W}gridSpan")
                if gs is not None:
                    span = int(gs.get(f"{W}val", "1"))
                vm = pr.find(f"{W}vMerge")
                if vm is not None:
                    vmerge = vm.get(f"{W}val", "continue")
            text = " ".join(_text(p) for p in tc.findall(f"{W}p")).strip()
            if vmerge == "continue":
                row.append((col, None))
            else:
                row.append((col, RawCell(text, colspan=span, header=header_row)))
            col += span
        grid_rows.append(row)

    # Resolve vertical merges: a continuation increases the rowspan of the cell above at the same column.
    owner: dict[int, RawCell] = {}
    out: list[list[RawCell]] = []
    for row in grid_rows:
        new_row: list[RawCell] = []
        for col, cell in row:
            if cell is None:
                if col in owner:
                    owner[col].rowspan += 1
            else:
                owner[col] = cell
                new_row.append(cell)
        out.append(new_row)
    return out


def parse_docx(data: bytes, title: str = "") -> Node:
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        body = ET.fromstring(z.read("word/document.xml")).find(f"{W}body")
        notes: dict[str, str] = {}
        if "word/footnotes.xml" in z.namelist():
            for fn in ET.fromstring(z.read("word/footnotes.xml")).findall(f"{W}footnote"):
                fid = fn.get(f"{W}id", "")
                text = _text(fn)
                if text and fid not in ("-1", "0"):
                    notes[fid] = text
        core_title = ""
        if "docProps/core.xml" in z.namelist():
            core = ET.fromstring(z.read("docProps/core.xml"))
            t = core.find("{http://purl.org/dc/elements/1.1/}title")
            core_title = (t.text or "").strip() if t is not None else ""

    tb = TreeBuilder(core_title or title)
    used_notes: list[str] = []
    for el in list(body) if body is not None else []:
        if el.tag == f"{W}p":
            text = _text(el)
            style = _style(el)
            if not text:
                continue
            if style == "Title":
                tb.root.title = text
                continue
            if m := HEADING_STYLE.match(style):
                tb.heading(text, int(m.group(1)))
                continue
            node = Node("list_item" if _is_list(el) else "paragraph", text=text)
            refs = _footnote_refs(el)
            if refs:
                node.attrs["footnotes"] = refs
                used_notes.extend(refs)
            tb.block(node)
        elif el.tag == f"{W}tbl":
            rows = _table(el)
            if rows:
                tb.block(resolve(rows))
    for fid in used_notes:
        if fid in notes:
            tb.root.add(Node("footnote", text=notes[fid], attrs={"label": fid}))
    return tb.root
