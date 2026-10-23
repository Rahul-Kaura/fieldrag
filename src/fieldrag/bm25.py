"""Okapi BM25, implemented directly so the index is inspectable and has no dependencies.

score(q, d) = sum over terms t in q of
    idf(t) * f(t, d) * (k1 + 1) / (f(t, d) + k1 * (1 - b + b * |d| / avgdl))
with idf(t) = ln(1 + (N - n(t) + 0.5) / (n(t) + 0.5)).
"""

from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass, field


@dataclass
class BM25:
    k1: float = 1.5
    b: float = 0.75
    doc_freq: dict[str, int] = field(default_factory=dict)
    doc_len: list[int] = field(default_factory=list)
    tf: list[dict[str, int]] = field(default_factory=list)

    @property
    def n_docs(self) -> int:
        return len(self.doc_len)

    @property
    def avgdl(self) -> float:
        return sum(self.doc_len) / self.n_docs if self.n_docs else 0.0

    def fit(self, corpus: list[list[str]]) -> "BM25":
        self.tf = [dict(Counter(toks)) for toks in corpus]
        self.doc_len = [len(toks) for toks in corpus]
        df: Counter[str] = Counter()
        for counts in self.tf:
            df.update(counts.keys())
        self.doc_freq = dict(df)
        return self

    def idf(self, term: str) -> float:
        n = self.doc_freq.get(term, 0)
        return math.log(1 + (self.n_docs - n + 0.5) / (n + 0.5))

    def score(self, query: list[str], i: int) -> float:
        tf, dl, avg = self.tf[i], self.doc_len[i], self.avgdl or 1.0
        s = 0.0
        for t in set(query):
            f = tf.get(t, 0)
            if f:
                s += self.idf(t) * f * (self.k1 + 1) / (f + self.k1 * (1 - self.b + self.b * dl / avg))
        return s

    def top_k(self, query: list[str], k: int = 5) -> list[tuple[int, float]]:
        scored = [(i, self.score(query, i)) for i in range(self.n_docs)]
        scored = [x for x in scored if x[1] > 0]
        scored.sort(key=lambda x: (-x[1], x[0]))
        return scored[:k]

    def to_dict(self) -> dict:
        return {"k1": self.k1, "b": self.b, "doc_freq": self.doc_freq, "doc_len": self.doc_len, "tf": self.tf}

    @classmethod
    def from_dict(cls, d: dict) -> "BM25":
        return cls(d["k1"], d["b"], d["doc_freq"], d["doc_len"], d["tf"])
