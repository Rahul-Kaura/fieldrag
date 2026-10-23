from __future__ import annotations

import json
from pathlib import Path

import pytest

from fieldrag.answer import answer
from fieldrag.bm25 import BM25
from fieldrag.chunk import fixed_window, path_aware
from fieldrag.cli import main
from fieldrag.evaluate import compare, load_questions
from fieldrag.index import Index, load_corpus
from fieldrag.ir import Node
from fieldrag.parsers import parse_file
from fieldrag.parsers.html import parse_html
from fieldrag.parsers.markdown import parse_markdown
from fieldrag.parsers.text import parse_text
from fieldrag.summarize import summarize_tree
from fieldrag.tables import RawCell, expand, resolve, serialize_row
from fieldrag.textutil import stem, tokenize

EX = Path(__file__).resolve().parent.parent / "examples"
CORPUS = EX / "corpus"


# ---------------------------------------------------------------- tables

def test_expand_handles_row_and_col_spans():
    rows = [
        [RawCell("Role", rowspan=2, header=True), RawCell("Prod", colspan=2, header=True)],
        [RawCell("Read", header=True), RawCell("Write", header=True)],
        [RawCell("SRE", header=True), RawCell("Yes"), RawCell("No")],
    ]
    g = expand(rows)
    assert (g.n_rows, g.n_cols) == (3, 3)
    assert g.cells[1][0].text == "Role" and g.cells[1][0].origin == (0, 0)
    assert g.cells[0][2].text == "Prod"


def test_resolve_attaches_full_header_path():
    rows = [
        [RawCell("Role", rowspan=2, header=True), RawCell("Prod", colspan=2, header=True)],
        [RawCell("Read", header=True), RawCell("Write", header=True)],
        [RawCell("SRE", header=True), RawCell("Yes"), RawCell("No")],
    ]
    t = resolve(rows)
    assert t.attrs["header_rows"] == 2 and t.attrs["header_cols"] == 1
    assert serialize_row(t.children[0]) == "SRE › Prod › Read: Yes; SRE › Prod › Write: No"


def test_label_column_inferred_without_markup():
    rows = [[RawCell("Data", header=True), RawCell("Days", header=True)], [RawCell("logs"), RawCell("30")]]
    t = resolve(rows)
    assert serialize_row(t.children[0]) == "logs › Days: 30"


def test_numeric_first_row_is_not_a_header():
    t = resolve([[RawCell("1"), RawCell("2")], [RawCell("3"), RawCell("4")]])
    assert t.attrs["header_rows"] == 0


# ---------------------------------------------------------------- parsers

def test_docx_merged_headers_and_footnotes():
    d = parse_file(CORPUS / "retention-policy.docx")
    assert d.root.title == "Example Corp Data Retention Policy"
    table = next(n for n in d.root.walk() if n.type == "table")
    assert (table.attrs["header_rows"], table.attrs["header_cols"]) == (2, 1)
    first = serialize_row(table.children[0])
    assert "Customer support transcripts › Backups › Region B: 35 days" in first
    assert any(n.type == "footnote" and "stricter" in n.text for n in d.root.walk())
    titles = [n.title for n in d.root.walk() if n.type == "section"]
    assert "4.2 Customer-requested deletion" in titles


def test_html_skips_chrome_and_reads_spans():
    root = parse_html((CORPUS / "access-control-standard.html").read_text())
    texts = " ".join(n.text for n in root.walk())
    assert "Home | Policies" not in texts and "internal" not in texts
    table = next(n for n in root.walk() if n.type == "table")
    rows = [serialize_row(r) for r in table.children]
    assert any("Data scientist › Staging › Write: No" in r for r in rows)
    assert table.text == "Default access by role and environment"


def test_markdown_sections_lists_tables_footnotes():
    root = parse_markdown("# T\n\n## A\n\npara one[^n]\n\n- x\n- y\n\n| k | v |\n|---|---|\n| a | 1 |\n\n[^n]: the note\n")
    sec = next(n for n in root.walk() if n.title == "A")
    types = [c.type for c in sec.children]
    assert types == ["paragraph", "list_item", "list_item", "table"]
    assert sec.children[0].attrs["footnotes"] == ["n"] and "[^" not in sec.children[0].text


def test_text_numbered_headings_nest():
    root = parse_text("TITLE HERE\n\n1. Scope\nBody.\n\n1.1 Detail\nMore.\n\n2. Other\n- item\n")
    assert root.title == "Title Here"
    detail = next(n for n in root.walk() if n.title == "1.1 Detail")
    assert detail.path() == ["1 Scope", "1.1 Detail"]


def test_node_type_is_validated():
    with pytest.raises(ValueError):
        Node("banana")


# ---------------------------------------------------------------- retrieval pieces

def test_stemming_and_stopwords():
    assert stem("backups") == "backup" and stem("policies") == "policy" and stem("process") == "process"
    assert tokenize("The backups are retained") == ["backup", "retain"]


def test_bm25_prefers_rare_term_and_shorter_doc():
    bm = BM25().fit([["region", "a", "days"], ["region", "b", "days"], ["region"] * 10 + ["b"]])
    top = bm.top_k(["b"], 3)
    assert top[0][0] == 1
    assert bm.idf("b") > bm.idf("region")


def test_path_aware_chunks_never_cross_sections_and_carry_context():
    d = parse_file(CORPUS / "incident-runbook.md")
    summarize_tree(d.root)
    chunks = path_aware(d, max_tokens=64)
    for c in chunks:
        secs = {(n.section().id if n.section() else "root") for n in d.root.walk() if n.id in c.node_ids}
        assert len(secs) <= 1
    mit = next(c for c in chunks if c.path[-1:] == ["3 Mitigation"] and "Prefer rollback" in c.text)
    assert "irreversible schema migration" in mit.text  # footnote inlined
    assert mit.context.startswith("Incident Response Runbook")


def test_fixed_window_baseline_loses_header_binding():
    d = parse_file(CORPUS / "access-control-standard.html")
    text = " ".join(c.text for c in fixed_window(d, max_tokens=64))
    assert "Data scientist" in text and "›" not in text


# ---------------------------------------------------------------- end to end

@pytest.fixture(scope="module")
def index() -> Index:
    return Index.build(load_corpus(CORPUS), "path")


def test_answer_is_cited_and_cell_level(index):
    a = answer(index, "How long are customer support transcript backups kept in Region B?")
    assert not a.abstained
    assert a.evidence[0].text == "Customer support transcripts › Backups › Region B: 35 days"
    assert a.evidence[0].citation == "retention-policy › 3 Retention Schedule"


def test_answer_abstains_off_corpus(index):
    assert answer(index, "What is the capital of France?").abstained


def test_index_round_trip(tmp_path, index):
    p = tmp_path / "i.json"
    index.save(p)
    again = Index.load(p)
    assert len(again.chunks) == len(index.chunks)
    assert again.search("break-glass")[0][0].chunk_id == index.search("break-glass")[0][0].chunk_id


def test_path_aware_beats_fixed_on_sample_questions():
    qs = load_questions(EX / "questions.jsonl")
    fixed, path = compare(lambda: load_corpus(CORPUS), qs, ("fixed", "path"), max_tokens=64)
    assert path.recall[1] > fixed.recall[1]
    assert path.recall[3] == 1.0


def test_cli_ingest_query_eval(tmp_path, capsys):
    out = tmp_path / "idx.json"
    assert main(["ingest", str(CORPUS), "-o", str(out)]) == 0
    assert json.loads(out.read_text())["strategy"] == "path"
    assert main(["query", str(out), "How often do database credentials rotate?"]) == 0
    assert "every 30 days" in capsys.readouterr().out
    assert main(["eval", str(CORPUS), str(EX / "questions.jsonl"), "--max-tokens", "64"]) == 0
    assert "| path |" in capsys.readouterr().out


def test_cli_reports_empty_corpus(tmp_path, capsys):
    assert main(["ingest", str(tmp_path)]) == 1
