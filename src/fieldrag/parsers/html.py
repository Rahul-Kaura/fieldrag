"""HTML: h1-h6, p, li, tables with colspan/rowspan and th, caption. Standard library only."""

from __future__ import annotations

from html.parser import HTMLParser

from ..ir import Node, TreeBuilder
from ..tables import RawCell, resolve

BLOCK_TEXT = {"p", "li", "td", "th", "caption", "h1", "h2", "h3", "h4", "h5", "h6", "dd", "dt", "blockquote"}
SKIP = {"script", "style", "nav", "footer", "head"}


class _Parser(HTMLParser):
    def __init__(self, title: str) -> None:
        super().__init__(convert_charrefs=True)
        self.tb = TreeBuilder(title)
        self.buf: list[str] = []
        self.capture: str | None = None
        self.skip_depth = 0
        self.table_rows: list[list[RawCell]] | None = None
        self.caption = ""
        self.cell_attrs: dict[str, str] = {}
        self.doc_title = ""
        self.in_title = False

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag in SKIP:
            self.skip_depth += 1
            if tag == "head":
                self.skip_depth -= 1  # we still want <title>
        if tag == "title":
            self.in_title = True
        if self.skip_depth:
            return
        if tag == "table":
            self.table_rows, self.caption = [], ""
        elif tag == "tr" and self.table_rows is not None:
            self.table_rows.append([])
        elif tag in BLOCK_TEXT:
            self.capture, self.buf = tag, []
            if tag in ("td", "th"):
                self.cell_attrs = a
        elif tag == "br" and self.capture:
            self.buf.append(" ")

    def handle_endtag(self, tag):
        if tag in SKIP and tag != "head":
            self.skip_depth = max(0, self.skip_depth - 1)
            return
        if tag == "title":
            self.in_title = False
        if self.skip_depth:
            return
        if tag == "table" and self.table_rows is not None:
            rows = [r for r in self.table_rows if r]
            if rows:
                self.tb.block(resolve(rows, caption=self.caption))
            self.table_rows = None
        elif tag == self.capture:
            text = " ".join("".join(self.buf).split())
            self.capture = None
            if tag in ("td", "th") and self.table_rows is not None:
                if not self.table_rows:
                    self.table_rows.append([])
                self.table_rows[-1].append(RawCell(
                    text,
                    colspan=int(self.cell_attrs.get("colspan") or 1),
                    rowspan=int(self.cell_attrs.get("rowspan") or 1),
                    header=(tag == "th"),
                ))
            elif tag == "caption":
                self.caption = text
            elif not text:
                return
            elif tag[0] == "h" and tag[1:].isdigit():
                self.tb.heading(text, int(tag[1:]))
            elif tag == "li":
                self.tb.block(Node("list_item", text=text))
            elif self.table_rows is None:
                self.tb.block(Node("paragraph", text=text))

    def handle_data(self, data):
        if self.in_title:
            self.doc_title += data
        if self.capture and not self.skip_depth:
            self.buf.append(data)


def parse_html(text: str, title: str = "") -> Node:
    p = _Parser(title)
    p.feed(text)
    p.close()
    if p.doc_title.strip():
        p.tb.root.title = " ".join(p.doc_title.split())
    return p.tb.root
