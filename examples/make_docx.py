"""Generate examples/corpus/retention-policy.docx with only the standard library.

The table deliberately uses horizontal merges (gridSpan) and vertical merges (vMerge)
in its header, the layout that breaks naive text extraction.
Run: python examples/make_docx.py
"""

from __future__ import annotations

import zipfile
from pathlib import Path
from xml.sax.saxutils import escape

OUT = Path(__file__).parent / "corpus" / "retention-policy.docx"


def p(text: str, style: str | None = None, footnote: int | None = None) -> str:
    ppr = f'<w:pPr><w:pStyle w:val="{style}"/></w:pPr>' if style else ""
    fn = f'<w:r><w:footnoteReference w:id="{footnote}"/></w:r>' if footnote else ""
    return f'<w:p>{ppr}<w:r><w:t xml:space="preserve">{escape(text)}</w:t></w:r>{fn}</w:p>'


def li(text: str) -> str:
    return (f'<w:p><w:pPr><w:pStyle w:val="ListParagraph"/><w:numPr><w:ilvl w:val="0"/><w:numId w:val="1"/></w:numPr></w:pPr>'
            f'<w:r><w:t xml:space="preserve">{escape(text)}</w:t></w:r></w:p>')


def tc(text: str = "", span: int = 1, vmerge: str | None = None) -> str:
    pr = ""
    if span > 1:
        pr += f'<w:gridSpan w:val="{span}"/>'
    if vmerge == "restart":
        pr += '<w:vMerge w:val="restart"/>'
    elif vmerge == "continue":
        pr += "<w:vMerge/>"
    return f"<w:tc><w:tcPr>{pr}</w:tcPr>{p(text)}</w:tc>"


def tr(cells: list[str], header: bool = False) -> str:
    trpr = "<w:trPr><w:tblHeader/></w:trPr>" if header else ""
    return f"<w:tr>{trpr}{''.join(cells)}</w:tr>"


def retention_table() -> str:
    rows = [
        tr([tc("Data class", vmerge="restart"), tc("Primary storage", span=2), tc("Backups", span=2)], header=True),
        tr([tc(vmerge="continue"), tc("Region A"), tc("Region B"), tc("Region A"), tc("Region B")], header=True),
        tr([tc("Customer support transcripts"), tc("18 months"), tc("12 months"), tc("90 days"), tc("35 days")]),
        tr([tc("Model training snapshots"), tc("24 months"), tc("24 months"), tc("180 days"), tc("180 days")]),
        tr([tc("Authentication logs"), tc("400 days"), tc("400 days"), tc("400 days"), tc("2 years")]),
        tr([tc("Billing records"), tc("7 years"), tc("7 years"), tc("7 years"), tc("7 years")]),
    ]
    return f"<w:tbl>{''.join(rows)}</w:tbl>"


def body() -> str:
    parts = [
        p("Example Corp Data Retention Policy", "Title"),
        p("1 Purpose", "Heading1"),
        p("This policy sets how long Example Corp keeps each class of data and where it is stored. "
          "It applies to production systems, analytics environments and backups."),
        p("2 Scope", "Heading1"),
        p("The policy covers all data processed by the AI platform, including data held by subprocessors. "
          "Personal devices and paper records are out of scope."),
        p("3 Retention Schedule", "Heading1"),
        p("Retention periods differ by region because of local regulation. Periods start when the record is created.", footnote=2),
        retention_table(),
        p("4 Exceptions", "Heading1"),
        p("4.1 Legal hold", "Heading2"),
        p("When the legal team issues a hold, deletion stops for every record covered by the hold until the hold is released in writing. "
          "Holds override every period in the retention schedule."),
        p("4.2 Customer-requested deletion", "Heading2"),
        p("Customers may request deletion of their data at any time. Requests are completed within 30 days in primary storage. "
          "Backups are not edited in place; deleted records age out of backups on the normal backup schedule."),
        li("Requests are logged in the privacy ticket queue."),
        li("The data protection officer approves any request that conflicts with a legal hold."),
        p("5 Review", "Heading1"),
        p("The security and legal teams review this policy every 12 months, or sooner after a material change to the platform."),
    ]
    return "".join(parts)


DOC = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
       '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body>'
       + "{body}" + "</w:body></w:document>")
FOOTNOTES = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
             '<w:footnotes xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
             '<w:footnote w:id="-1"><w:p/></w:footnote><w:footnote w:id="0"><w:p/></w:footnote>'
             '<w:footnote w:id="2"><w:p><w:r><w:t>Region B periods follow the stricter of the two applicable regimes.</w:t></w:r></w:p></w:footnote>'
             "</w:footnotes>")
CONTENT_TYPES = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                 '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
                 '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
                 '<Default Extension="xml" ContentType="application/xml"/>'
                 '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
                 '<Override PartName="/word/footnotes.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.footnotes+xml"/>'
                 "</Types>")
RELS = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>'
        "</Relationships>")
DOC_RELS = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/footnotes" Target="footnotes.xml"/>'
            "</Relationships>")


def main() -> None:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(OUT, "w", zipfile.ZIP_DEFLATED) as z:
        for name, data in [("[Content_Types].xml", CONTENT_TYPES), ("_rels/.rels", RELS),
                           ("word/_rels/document.xml.rels", DOC_RELS), ("word/document.xml", DOC.replace("{body}", body())),
                           ("word/footnotes.xml", FOOTNOTES)]:
            info = zipfile.ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0))
            z.writestr(info, data)
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
