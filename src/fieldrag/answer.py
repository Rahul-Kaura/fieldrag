"""Cited answers from retrieved chunks.

The default answerer is extractive: it returns the sentences that best match the
question, each with a citation to the section it came from. Nothing leaves the
machine. A generative model can be plugged in through `Generator`; the retrieved
context and citation list are the same either way, so answers stay auditable.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from .chunk import Chunk
from .index import Index
from .textutil import sentences, tokenize


@dataclass
class Evidence:
    text: str
    citation: str
    chunk_id: str
    score: float


@dataclass
class Answer:
    question: str
    text: str
    evidence: list[Evidence] = field(default_factory=list)
    abstained: bool = False

    def render(self) -> str:
        if self.abstained:
            return f"No supported answer found in the corpus for: {self.question}"
        lines = [self.text, ""]
        for i, e in enumerate(self.evidence, 1):
            lines.append(f"[{i}] {e.citation}  ({e.chunk_id}, score {e.score:.2f})")
        return "\n".join(lines)


class Generator(Protocol):
    def __call__(self, question: str, context: list[Chunk]) -> str: ...


def _sentence_units(chunk: Chunk) -> list[str]:
    out: list[str] = []
    for line in chunk.text.split("\n"):
        if " › " in line and "; " in line:  # a serialized table row: answer at cell granularity
            out.extend(part.strip() for part in line.split("; "))
        else:
            out.extend(sentences(line) if len(line) > 200 else [line])
    return [s for s in out if s.strip()]


def answer(index: Index, question: str, k: int = 4, max_sentences: int = 3, min_score: float = 1.0,
           generator: Generator | None = None) -> Answer:
    hits = index.search(question, k)
    if not hits or hits[0][1] < min_score:
        return Answer(question, "", abstained=True)
    q = set(tokenize(question))
    candidates: list[tuple[float, int, str, Chunk, float]] = []
    for rank, (chunk, score) in enumerate(hits):
        for s in _sentence_units(chunk):
            toks = set(tokenize(s))
            if not toks:
                continue
            overlap = len(q & toks) / len(q) if q else 0.0
            candidates.append((overlap * (1 + score / (hits[0][1] or 1)), rank, s, chunk, score))
    candidates.sort(key=lambda c: (-c[0], c[1]))
    chosen, seen = [], set()
    best = candidates[0][0] if candidates else 0.0
    for c in candidates:
        if c[0] >= 0.75 * best and c[0] > 0 and c[2] not in seen:
            seen.add(c[2])
            chosen.append(c)
        if len(chosen) == max_sentences:
            break
    if not chosen:
        return Answer(question, "", abstained=True)
    evidence = [Evidence(s, ch.citation(), ch.chunk_id, sc) for _, _, s, ch, sc in chosen]
    if generator is not None:
        text = generator(question, [h[0] for h in hits])
    else:
        text = " ".join(f"{e.text} [{i}]" for i, e in enumerate(evidence, 1))
    return Answer(question, text, evidence)
