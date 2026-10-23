"""Chunking strategies.

`path_aware` (default) forms chunks from tree nodes inside one section, never across
section boundaries, and prefixes each with its outline path and the section summary.
`fixed_window` is the common baseline: flatten the document and cut every N tokens.
Both produce the same `Chunk` type so they can be evaluated side by side.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field

from .ir import Document, Node
from .summarize import node_text
from .tables import serialize_row
from .textutil import approx_tokens


@dataclass
class Chunk:
    chunk_id: str
    doc_id: str
    path: list[str]
    text: str
    node_ids: list[str] = field(default_factory=list)
    context: str = ""  # path + summary prefix used for retrieval and shown to a model

    @property
    def retrieval_text(self) -> str:
        return f"{self.context}\n{self.text}" if self.context else self.text

    def citation(self) -> str:
        return f"{self.doc_id} › " + " › ".join(self.path) if self.path else self.doc_id

    def to_dict(self) -> dict:
        return asdict(self)


def _units(section: Node, notes: dict[str, str] | None = None) -> list[tuple[str, list[str]]]:
    """Retrievable units directly inside a section: paragraphs, list runs, and table rows.
    Footnotes are inlined into the paragraph that cites them, so an exception never gets
    separated from the rule it qualifies."""
    notes = notes or {}
    units: list[tuple[str, list[str]]] = []
    list_run: list[Node] = []

    def flush_list() -> None:
        if list_run:
            units.append(("; ".join(n.text for n in list_run), [n.id for n in list_run]))
            list_run.clear()

    for child in section.children:
        if child.type == "section":
            continue
        if child.type == "list_item":
            list_run.append(child)
            continue
        flush_list()
        if child.type == "table":
            caption = f"{child.text}: " if child.text else ""
            for row in child.children:
                line = serialize_row(row)
                if line:
                    units.append((caption + line, [row.id]))
        elif child.type == "footnote" and child.attrs.get("label") in notes:
            continue  # already inlined where it is cited
        else:
            t = node_text(child)
            refs = [notes[r] for r in child.attrs.get("footnotes", []) if r in notes]
            if refs:
                t = t + " " + " ".join(f"(Note: {r})" for r in refs)
            if t:
                units.append((t, [child.id]))
    flush_list()
    return units


def path_aware(doc: Document, max_tokens: int = 180, with_summary: bool = True) -> list[Chunk]:
    chunks: list[Chunk] = []
    sections = [n for n in doc.root.walk() if n.type in ("document", "section")]
    notes = {n.attrs["label"]: n.text for n in doc.root.children if n.type == "footnote" and "label" in n.attrs}
    for sec in sections:
        units = _units(sec, notes)
        if not units:
            continue
        path = sec.path()
        summary = ""
        if with_summary and sec.type == "section":
            parent = sec.parent if sec.parent is not None and sec.parent.type == "section" else None
            summary = (parent.attrs.get("summary") if parent else "") or ""
        context = " › ".join([doc.root.title or doc.doc_id] + path)
        if summary:
            context += f"\n[{' › '.join(path[:-1]) or 'Overview'}] {summary}"
        buf: list[str] = []
        ids: list[str] = []
        size = 0
        for text, node_ids in units:
            t = approx_tokens(text)
            if buf and size + t > max_tokens:
                chunks.append(Chunk(f"{doc.doc_id}:c{len(chunks)+1}", doc.doc_id, path, "\n".join(buf), ids, context))
                buf, ids, size = [], [], 0
            buf.append(text)
            ids.extend(node_ids)
            size += t
        if buf:
            chunks.append(Chunk(f"{doc.doc_id}:c{len(chunks)+1}", doc.doc_id, path, "\n".join(buf), ids, context))
    # footnotes are attached to the document root
    return chunks


def fixed_window(doc: Document, max_tokens: int = 180, overlap: int = 30) -> list[Chunk]:
    """Baseline that mirrors a typical text-extraction pipeline: flatten in reading order
    (headings inline, table cells as plain text with headers printed once) and cut fixed windows."""
    words: list[tuple[str, str, list[str]]] = []  # (word, node_id, path)
    for n in doc.root.walk():
        if n.type == "table" and n.children:
            headers = []
            for row in n.children:
                for cell in row.children:
                    for h in cell.attrs.get("col_header", []):
                        if h not in headers:
                            headers.append(h)
            for w in " ".join(headers).split():
                words.append((w, n.id, n.path()))
        if n.type == "section":
            for w in n.title.split():
                words.append((w, n.id, n.path()))
        elif n.type in ("paragraph", "list_item", "footnote"):
            for w in n.text.split():
                words.append((w, n.id, n.path()))
        elif n.type == "row":
            labels = (n.children[0].attrs.get("row_header", []) if n.children else []) or ([n.text] if n.text else [])
            flat = " ".join(labels + [c.text for c in n.children if c.text])
            for w in flat.split():
                words.append((w, n.id, n.path()))
    step_words = max(1, int(max_tokens * 0.75))
    ov_words = int(overlap * 0.75)
    chunks: list[Chunk] = []
    i = 0
    while i < len(words):
        window = words[i : i + step_words]
        ids = list(dict.fromkeys(w[1] for w in window))
        path = window[0][2]
        chunks.append(Chunk(f"{doc.doc_id}:w{len(chunks)+1}", doc.doc_id, path, " ".join(w[0] for w in window), ids))
        if i + step_words >= len(words):
            break
        i += step_words - ov_words
    return chunks


STRATEGIES = {"path": path_aware, "fixed": fixed_window}
