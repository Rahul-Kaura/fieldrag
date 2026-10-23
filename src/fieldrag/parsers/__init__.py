"""Parsers turn source files into a `Document`. Dispatch is by file extension."""

from __future__ import annotations

from pathlib import Path

from ..ir import Document, promote_single_title
from .docx import parse_docx
from .html import parse_html
from .markdown import parse_markdown
from .text import parse_text

PARSERS = {
    ".md": ("markdown", lambda p: parse_markdown(p.read_text(encoding="utf-8"), p.stem)),
    ".markdown": ("markdown", lambda p: parse_markdown(p.read_text(encoding="utf-8"), p.stem)),
    ".html": ("html", lambda p: parse_html(p.read_text(encoding="utf-8"), p.stem)),
    ".htm": ("html", lambda p: parse_html(p.read_text(encoding="utf-8"), p.stem)),
    ".txt": ("text", lambda p: parse_text(p.read_text(encoding="utf-8"), p.stem)),
    ".docx": ("docx", lambda p: parse_docx(p.read_bytes(), p.stem)),
}


def supported(path: Path) -> bool:
    return path.suffix.lower() in PARSERS


def parse_file(path: str | Path) -> Document:
    p = Path(path)
    fmt, fn = PARSERS[p.suffix.lower()]
    root = fn(p)
    promote_single_title(root)
    doc = Document(doc_id=p.stem, root=root, source=str(p), format=fmt)
    doc.assign_ids()
    return doc
