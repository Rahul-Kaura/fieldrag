"""Tokenization and sentence splitting. Deterministic, dependency-free."""

from __future__ import annotations

import re

STOPWORDS = frozenset(
    """a an and are as at be been but by can did do does for from had has have how i if in into is it its
    may must not of on or our shall should so such than that the their them then there these they this
    to was we were what when where which who why will with within without would you your""".split()
)
_TOKEN = re.compile(r"[a-z0-9]+(?:[.\-][a-z0-9]+)*")
_SENT = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9(\"'])")


def stem(tok: str) -> str:
    """A light suffix stripper: enough to match 'backups'/'backup', 'retained'/'retain', not a full stemmer."""
    if len(tok) <= 4 or tok[0].isdigit():
        return tok
    for suf, rep in (("ies", "y"), ("sses", "ss"), ("ing", ""), ("ed", ""), ("es", ""), ("s", "")):
        if tok.endswith(suf) and len(tok) - len(suf) >= 3:
            if suf == "es" and not tok[:-2].endswith(("s", "x", "z", "ch", "sh")):
                continue
            if suf == "s" and tok.endswith("ss"):
                continue
            return tok[: -len(suf)] + rep
    return tok


def tokenize(text: str, keep_stopwords: bool = False) -> list[str]:
    toks = _TOKEN.findall(text.lower())
    return [stem(t) for t in toks if keep_stopwords or t not in STOPWORDS]


def sentences(text: str) -> list[str]:
    return [s.strip() for s in _SENT.split(text) if s.strip()]


def approx_tokens(text: str) -> int:
    """Rough subword estimate used for chunk budgets (about 0.75 words per token)."""
    return int(len(text.split()) / 0.75) + 1
