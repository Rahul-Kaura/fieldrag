"""Retrieval evaluation: compare chunking strategies on a labeled question set.

Each line of the question file is JSON:
    {"q": "How long are backups kept in Region B?", "doc": "retention-policy", "answer": "35 days"}
A retrieved chunk counts as a hit if it comes from `doc` and contains `answer`
(case-insensitive). We report recall@k and mean reciprocal rank.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from .index import Index
from .ir import Document
from .textutil import approx_tokens


@dataclass
class Question:
    q: str
    doc: str
    answer: str


@dataclass
class Result:
    strategy: str
    n: int
    recall: dict[int, float]
    mrr: float
    n_chunks: int
    misses: list[str]
    context_tokens: float = 0.0  # mean tokens handed to a model when taking the top 3 chunks


def load_questions(path: str | Path) -> list[Question]:
    out = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            d = json.loads(line)
            out.append(Question(d["q"], d["doc"], d["answer"]))
    return out


def _norm(s: str) -> str:
    return " ".join(s.lower().replace("›", " ").split())


def evaluate(index: Index, questions: list[Question], ks: tuple[int, ...] = (1, 3, 5)) -> Result:
    kmax = max(ks)
    hits_at = {k: 0 for k in ks}
    rr = 0.0
    ctx = 0
    misses: list[str] = []
    for q in questions:
        results = index.search(q.q, kmax)
        ctx += sum(approx_tokens(c.retrieval_text) for c, _ in results[:3])
        rank = next(
            (i + 1 for i, (c, _) in enumerate(results) if c.doc_id == q.doc and _norm(q.answer) in _norm(c.text)),
            None,
        )
        if rank is None:
            misses.append(q.q)
            continue
        rr += 1 / rank
        for k in ks:
            if rank <= k:
                hits_at[k] += 1
    n = len(questions) or 1
    return Result(index.strategy, len(questions), {k: hits_at[k] / n for k in ks}, rr / n, len(index.chunks), misses, ctx / n)


def compare(documents_factory, questions: list[Question], strategies=("fixed", "path"), max_tokens: int = 180) -> list[Result]:
    results = []
    for s in strategies:
        docs: list[Document] = documents_factory()
        results.append(evaluate(Index.build(docs, s, max_tokens), questions))
    return results


def format_table(results: list[Result]) -> str:
    ks = sorted(results[0].recall)
    head = "| strategy | chunks | " + " | ".join(f"recall@{k}" for k in ks) + " | MRR | tokens in top-3 |"
    sep = "|---|---:|" + "---:|" * len(ks) + "---:|---:|"
    rows = [
        f"| {r.strategy} | {r.n_chunks} | " + " | ".join(f"{r.recall[k]:.2f}" for k in ks)
        + f" | {r.mrr:.3f} | {r.context_tokens:.0f} |"
        for r in results
    ]
    return "\n".join([head, sep, *rows])
