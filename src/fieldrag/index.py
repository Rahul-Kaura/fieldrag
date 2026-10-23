"""Build, persist and query an index over a corpus."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path

from . import __version__
from .bm25 import BM25
from .chunk import STRATEGIES, Chunk
from .ir import Document
from .parsers import parse_file, supported
from .summarize import summarize_tree
from .textutil import tokenize

INDEX_VERSION = 1


@dataclass
class Index:
    chunks: list[Chunk]
    bm25: BM25
    strategy: str
    docs: list[dict] = field(default_factory=list)

    @classmethod
    def build(cls, documents: list[Document], strategy: str = "path", max_tokens: int = 180) -> "Index":
        chunks: list[Chunk] = []
        for d in documents:
            summarize_tree(d.root)
            chunks.extend(STRATEGIES[strategy](d, max_tokens=max_tokens))
        bm25 = BM25().fit([tokenize(c.retrieval_text) for c in chunks])
        docs = [{"doc_id": d.doc_id, "title": d.root.title, "source": d.source, "format": d.format} for d in documents]
        return cls(chunks, bm25, strategy, docs)

    def search(self, query: str, k: int = 5) -> list[tuple[Chunk, float]]:
        return [(self.chunks[i], s) for i, s in self.bm25.top_k(tokenize(query), k)]

    def save(self, path: str | Path) -> None:
        payload = {
            "fieldrag": __version__,
            "index_version": INDEX_VERSION,
            "built_at": int(time.time()),
            "strategy": self.strategy,
            "docs": self.docs,
            "chunks": [c.to_dict() for c in self.chunks],
            "bm25": self.bm25.to_dict(),
        }
        Path(path).write_text(json.dumps(payload), encoding="utf-8")

    @classmethod
    def load(cls, path: str | Path) -> "Index":
        d = json.loads(Path(path).read_text(encoding="utf-8"))
        if d.get("index_version") != INDEX_VERSION:
            raise ValueError(f"index version {d.get('index_version')} is not supported; rebuild with `fieldrag ingest`")
        return cls([Chunk(**c) for c in d["chunks"]], BM25.from_dict(d["bm25"]), d["strategy"], d["docs"])


def load_corpus(path: str | Path) -> list[Document]:
    root = Path(path)
    files = [root] if root.is_file() else sorted(p for p in root.rglob("*") if p.is_file() and supported(p))
    return [parse_file(p) for p in files]
