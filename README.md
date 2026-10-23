# fieldrag

**Structure-preserving document retrieval with citations that runs fully offline.** No external APIs, no model downloads, no runtime dependencies: just Python's standard library. Built for environments where documents cannot leave the network (regulated, on-prem and air-gapped deployments) and where every answer has to point to the exact section it came from.

```
$ fieldrag ingest examples/corpus
indexed 4 document(s) into 27 chunk(s) [path] -> fieldrag.index.json

$ fieldrag query fieldrag.index.json "Can a data scientist write to staging?"
Data scientist › Staging › Write: No [1] ...

[1] access-control-standard › 2 Environment access matrix  (access-control-standard:c3, score 12.72)
```

That answer comes from a merged-header table in an HTML page. A typical text extractor flattens the same table to `Data scientist Aggregated views only No Yes No`, and the fact that the last "No" means *staging write* is gone.

## Why

Retrieval-augmented generation assumes a retrieved passage carries the information needed to answer. Policies, runbooks and standards break that assumption: a clause depends on its section heading, a table value depends on merged headers two rows up, and an exception lives in a footnote. Fixed-size chunking discards all three. fieldrag keeps them.

## Pipeline

```
 .docx .html .md .txt ─► parser ─► document tree ─► table header resolution ─► section summaries ─► path-aware chunks ─► BM25 ─► cited answer
```

| Stage | What it does |
|---|---|
| **Parsers** | DOCX (read directly from the Office Open XML, including `gridSpan`/`vMerge` merged cells and `footnotes.xml`), HTML (`colspan`/`rowspan`, `<th>`, captions; nav and footer skipped), Markdown (headings, lists, pipe tables, footnotes) and plain text with numbered headings (`4.2 Exceptions`). |
| **Document tree** | A typed tree (`document`, `section`, `paragraph`, `list_item`, `table`, `row`, `cell`, `footnote`) that is the only contract between parsing and everything else, so parsers can be swapped or compared without touching retrieval. |
| **Tables** | Spanning cells are expanded into every grid slot they cover, header rows and label columns are detected (from markup, or inferred from content), and every value is serialized with its full header path: `Customer support transcripts › Backups › Region B: 35 days`. |
| **Summaries** | Extractive, bottom-up along the document's own hierarchy: a parent's summary is built from its text and its children's summaries. Pluggable for an abstractive model. |
| **Chunking** | Chunks never cross a section boundary, footnotes are inlined into the paragraph that cites them, and each chunk carries its outline path plus the parent section's summary as retrieval context. |
| **Retrieval** | Okapi BM25 implemented in about 60 lines so the scoring is inspectable. |
| **Answers** | Extractive and cell-level, each piece with a citation to document and section. Abstains when nothing in the corpus supports an answer. A generator can be plugged in; citations stay the same. |

## Evaluation

`examples/questions.jsonl` has 26 labeled questions over the four example documents. A retrieved chunk counts as a hit if it comes from the right document and contains the expected answer text. The baseline (`fixed`) is what most pipelines do: flatten text in reading order, print table headers once, cut fixed windows with overlap.

```
$ fieldrag eval examples/corpus examples/questions.jsonl --max-tokens 128
```

| strategy | chunks | recall@1 | recall@3 | recall@5 | MRR | tokens in top-3 |
|---|---:|---:|---:|---:|---:|---:|
| fixed | 12 | 0.77 | 0.92 | 0.92 | 0.846 | 333 |
| path | 28 | 0.96 | 1.00 | 1.00 | 0.981 | 237 |

At a 64-token budget the gap at recall@1 is 0.73 vs 0.96. Structure-aware chunks find the answer first more often while handing the model less text.

**Read these numbers carefully.** The corpus is small and was written for this repository. Two of the 26 questions ask for a header-value relationship ("Can a data scientist write to staging?") that the flat baseline cannot represent at all, so it can never get them right; those two account for most of the recall@3 gap. The recall@1 gap on the remaining questions comes from section-bounded chunks and path context ranking the right passage first. Run the harness on your own documents and questions before trusting either strategy.

## Usage

```bash
pip install git+https://github.com/Rahul-Kaura/fieldrag

fieldrag tree policy.docx --summaries          # inspect the parsed structure
fieldrag ingest ./docs -o docs.index.json       # build an index
fieldrag query docs.index.json "How long are backups kept?"
fieldrag query docs.index.json "break-glass" --raw   # ranked chunks with scores
fieldrag eval ./docs questions.jsonl --strategies fixed path --max-tokens 128 -v
```

```python
from fieldrag.index import Index, load_corpus
from fieldrag.answer import answer

idx = Index.build(load_corpus("docs/"))
print(answer(idx, "Who appoints the incident commander?").render())
```

## Design notes

- **Why BM25 and not embeddings by default?** It needs no model weights, is deterministic, and is easy to audit, which matters in restricted environments. The `Index` keeps chunk text and retrieval context separately, so a dense retriever can be added alongside it.
- **Why the document's own hierarchy instead of clustering?** Clustering-based trees (for example RAPTOR) are the right call when a corpus has no structure. Policies and runbooks do, and readers cite it ("section 4.2"), so every summary and citation stays attached to a real section.
- **Why extractive answers?** In the default configuration, nothing the system says is text the source documents do not contain.

## Limits

- Scanned PDFs and images are out of scope (no OCR). Convert to DOCX or HTML first.
- Header detection is heuristic when a table has no header markup; `fieldrag tree` shows what was inferred.
- The light stemmer is English-only.

## Development

```bash
pip install -e ".[dev]"
pytest
python examples/make_docx.py   # regenerate the sample Word file
```

## License

MIT
