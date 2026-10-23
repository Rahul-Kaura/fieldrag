"""fieldrag command line."""

from __future__ import annotations

import argparse
import json
import sys

from . import __version__
from .answer import answer
from .evaluate import compare, format_table, load_questions
from .index import Index, load_corpus
from .summarize import summarize_tree


def cmd_ingest(a: argparse.Namespace) -> int:
    docs = load_corpus(a.corpus)
    if not docs:
        print("fieldrag: no supported files found (.md .html .txt .docx)", file=sys.stderr)
        return 1
    idx = Index.build(docs, a.strategy, a.max_tokens)
    idx.save(a.output)
    print(f"indexed {len(docs)} document(s) into {len(idx.chunks)} chunk(s) [{a.strategy}] -> {a.output}")
    return 0


def cmd_query(a: argparse.Namespace) -> int:
    idx = Index.load(a.index)
    if a.raw:
        for chunk, score in idx.search(a.question, a.k):
            print(f"{score:6.2f}  {chunk.citation()}\n        {chunk.text[:240]}")
        return 0
    print(answer(idx, a.question, k=a.k).render())
    return 0


def cmd_eval(a: argparse.Namespace) -> int:
    questions = load_questions(a.questions)
    results = compare(lambda: load_corpus(a.corpus), questions, tuple(a.strategies), a.max_tokens)
    print(format_table(results))
    if a.verbose:
        for r in results:
            for m in r.misses:
                print(f"miss [{r.strategy}]: {m}")
    return 0


def cmd_tree(a: argparse.Namespace) -> int:
    docs = load_corpus(a.file)
    for d in docs:
        summarize_tree(d.root)
        if a.json:
            print(json.dumps(d.to_dict(), indent=2))
            continue
        print(f"{d.doc_id} [{d.format}] {d.root.title}")
        for n in d.root.walk():
            if n.type == "section":
                indent = "  " * n.level
                print(f"{indent}§ {n.title}")
                if a.summaries and n.attrs.get("summary"):
                    print(f"{indent}  ↳ {n.attrs['summary'][:160]}")
            elif n.type == "table":
                print(f"{'  ' * ((n.section().level if n.section() else 0) + 1)}▦ table {n.attrs['rows']}x{n.attrs['cols']} "
                      f"(header rows {n.attrs['header_rows']}, header cols {n.attrs['header_cols']})")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="fieldrag", description="Structure-preserving, offline document retrieval with citations.")
    p.add_argument("--version", action="version", version=f"fieldrag {__version__}")
    sub = p.add_subparsers(dest="cmd", required=True)

    i = sub.add_parser("ingest", help="parse a corpus and build an index")
    i.add_argument("corpus")
    i.add_argument("-o", "--output", default="fieldrag.index.json")
    i.add_argument("--strategy", choices=["path", "fixed"], default="path")
    i.add_argument("--max-tokens", type=int, default=180)
    i.set_defaults(fn=cmd_ingest)

    q = sub.add_parser("query", help="answer a question with citations")
    q.add_argument("index")
    q.add_argument("question")
    q.add_argument("-k", type=int, default=4)
    q.add_argument("--raw", action="store_true", help="show ranked chunks instead of an answer")
    q.set_defaults(fn=cmd_query)

    e = sub.add_parser("eval", help="compare chunking strategies on a labeled question set")
    e.add_argument("corpus")
    e.add_argument("questions")
    e.add_argument("--strategies", nargs="+", default=["fixed", "path"])
    e.add_argument("--max-tokens", type=int, default=180)
    e.add_argument("-v", "--verbose", action="store_true")
    e.set_defaults(fn=cmd_eval)

    t = sub.add_parser("tree", help="print the parsed document tree")
    t.add_argument("file")
    t.add_argument("--summaries", action="store_true")
    t.add_argument("--json", action="store_true")
    t.set_defaults(fn=cmd_tree)
    return p


def main(argv: list[str] | None = None) -> int:
    a = build_parser().parse_args(argv)
    try:
        return a.fn(a)
    except (OSError, ValueError, KeyError) as exc:
        print(f"fieldrag: error: {exc}", file=sys.stderr)
        return 1
