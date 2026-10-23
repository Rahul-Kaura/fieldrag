"""Hierarchy-aligned extractive summaries, computed bottom-up.

Each section gets a short summary chosen from its own text plus its children's
summaries, so a parent summary covers its whole subtree in a bounded size. The
hierarchy is the document's own (unlike clustering-based trees such as RAPTOR),
which keeps every summary attached to a citable section. Extractive by design so
the pipeline runs fully offline; an abstractive model can be plugged in through
`Summarizer`.
"""

from __future__ import annotations

import math
from collections import Counter
from typing import Callable, Protocol

from .ir import Node
from .tables import serialize_row
from .textutil import sentences, tokenize


class Summarizer(Protocol):
    def __call__(self, section_title: str, texts: list[str], max_sentences: int) -> str: ...


def node_text(n: Node) -> str:
    if n.type == "table":
        rows = [serialize_row(r) for r in n.children]
        return ". ".join(r for r in rows if r)
    if n.type in ("paragraph", "list_item", "footnote"):
        return n.text
    return ""


def extractive(section_title: str, texts: list[str], max_sentences: int = 2) -> str:
    """Pick sentences that best cover the section's vocabulary (TF-IDF centroid), keep original order."""
    sents = [s for t in texts for s in sentences(t)]
    if len(sents) <= max_sentences:
        return " ".join(sents)
    toks = [tokenize(s) for s in sents]
    df = Counter(t for ts in toks for t in set(ts))
    n = len(sents)
    idf = {t: math.log((n + 1) / (c + 0.5)) for t, c in df.items()}
    centroid = Counter()
    for ts in toks:
        for t in ts:
            centroid[t] += idf[t]
    title_terms = set(tokenize(section_title))

    def score(i: int) -> float:
        ts = toks[i]
        if not ts:
            return 0.0
        base = sum(centroid[t] for t in set(ts)) / (1 + math.log(1 + len(ts)))
        bonus = 1.25 if title_terms & set(ts) else 1.0
        position = 1.1 if i == 0 else 1.0
        return base * bonus * position

    best = sorted(range(n), key=score, reverse=True)[:max_sentences]
    return " ".join(sents[i] for i in sorted(best))


def summarize_tree(root: Node, fn: Callable[..., str] = extractive, max_sentences: int = 2) -> None:
    """Write `attrs['summary']` on every section, children first."""
    def visit(n: Node) -> str:
        child_summaries = [visit(c) for c in n.children if c.type == "section"]
        if n.type not in ("section", "document"):
            return ""
        own = [node_text(c) for c in n.children if c.type != "section"]
        texts = [t for t in own if t] + [s for s in child_summaries if s]
        summary = fn(n.title, texts, max_sentences) if texts else ""
        if summary:
            n.attrs["summary"] = summary
        return summary
    visit(root)
