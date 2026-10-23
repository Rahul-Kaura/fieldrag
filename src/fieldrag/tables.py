"""Table normalization: expand merged cells and resolve every body cell's headers.

The most common silent error in table extraction is correct text attached to the
wrong header. Spanning cells are expanded into every grid slot they cover (the
canonicalization idea from PubTables-1M), header rows/columns are identified, and
each body cell gets its full column and row header path.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .ir import Node


@dataclass
class RawCell:
    text: str
    colspan: int = 1
    rowspan: int = 1
    header: bool = False


@dataclass
class GridCell:
    text: str
    header: bool
    origin: tuple[int, int]  # (row, col) of the cell that owns this slot


@dataclass
class Grid:
    cells: list[list[GridCell | None]]
    header_rows: int = 0
    header_cols: int = 0
    notes: list[str] = field(default_factory=list)

    @property
    def n_rows(self) -> int:
        return len(self.cells)

    @property
    def n_cols(self) -> int:
        return max((len(r) for r in self.cells), default=0)


def expand(rows: list[list[RawCell]]) -> Grid:
    grid: list[list[GridCell | None]] = []
    for r, row in enumerate(rows):
        while len(grid) <= r:
            grid.append([])
        c = 0
        for cell in row:
            while c < len(grid[r]) and grid[r][c] is not None:
                c += 1
            for dr in range(max(1, cell.rowspan)):
                rr = r + dr
                while len(grid) <= rr:
                    grid.append([])
                for dc in range(max(1, cell.colspan)):
                    cc = c + dc
                    while len(grid[rr]) <= cc:
                        grid[rr].append(None)
                    grid[rr][cc] = GridCell(cell.text.strip(), cell.header, (r, c))
            c += max(1, cell.colspan)
    width = max((len(r) for r in grid), default=0)
    for row in grid:
        row.extend([None] * (width - len(row)))
    return Grid(grid)


def detect_headers(g: Grid) -> Grid:
    """Header rows: leading rows marked as header cells, or (if none are marked) a first row of
    non-numeric labels. Header columns: leading columns where every body row is marked header."""
    def is_header_row(row: list[GridCell | None]) -> bool:
        cells = [c for c in row if c is not None]
        return bool(cells) and all(c.header for c in cells)

    hr = 0
    while hr < g.n_rows - 1 and is_header_row(g.cells[hr]):
        hr += 1
    if hr == 0 and g.n_rows > 1:
        first = [c for c in g.cells[0] if c is not None and c.text]
        if first and not any(_numeric(c.text) for c in first):
            hr = 1
            g.notes.append("header row inferred from content")
    hc = 0
    while hc < g.n_cols - 1 and all(
        (row[hc] is not None and row[hc].header) for row in g.cells[hr:]
    ) and g.n_rows > hr:
        hc += 1
    if hc == 0 and hr > 0 and g.n_cols > 1 and g.n_rows > hr:
        # A label column: its header cell spans every header row (one origin) and every body
        # value in it is non-empty, non-numeric text. Common in Word tables that mark no header column.
        top = {g.cells[r][0].origin for r in range(hr) if g.cells[r][0] is not None}
        body = [g.cells[r][0] for r in range(hr, g.n_rows)]
        if len(top) == 1 and all(c is not None and c.text and not _numeric(c.text) for c in body):
            hc = 1
            g.notes.append("label column inferred from content")
    g.header_rows, g.header_cols = hr, hc
    return g


def _numeric(text: str) -> bool:
    t = text.replace(",", "").replace("%", "").replace("$", "").strip()
    try:
        float(t)
        return True
    except ValueError:
        return False


def _dedupe(seq: list[str]) -> list[str]:
    out: list[str] = []
    for s in seq:
        if s and (not out or out[-1] != s):
            out.append(s)
    return out


def resolve(rows: list[list[RawCell]], caption: str = "") -> Node:
    """Return a `table` node whose `row` children hold `cell` nodes with resolved headers."""
    g = detect_headers(expand(rows))
    table = Node("table", text=caption, attrs={"rows": g.n_rows, "cols": g.n_cols,
                                               "header_rows": g.header_rows, "header_cols": g.header_cols})
    for r in range(g.header_rows, g.n_rows):
        row_node = table.add(Node("row"))
        row_labels = _dedupe([g.cells[r][c].text for c in range(g.header_cols) if g.cells[r][c] is not None])
        seen: set[tuple[int, int]] = set()
        for c in range(g.header_cols, g.n_cols):
            cell = g.cells[r][c]
            if cell is None or cell.origin in seen:
                continue
            seen.add(cell.origin)
            col_path = _dedupe([g.cells[h][c].text for h in range(g.header_rows) if g.cells[h][c] is not None])
            row_node.add(Node("cell", text=cell.text, attrs={"col_header": col_path, "row_header": row_labels}))
        if not row_node.children and row_labels:
            row_node.text = " / ".join(row_labels)
    return table


def serialize_row(row: Node) -> str:
    """One line per row with every value carrying its headers: `Region B › Backups › Retention: 35 days`."""
    parts: list[str] = []
    for cell in row.children:
        if not cell.text:
            continue
        label = " › ".join(cell.attrs.get("row_header", []) + cell.attrs.get("col_header", []))
        parts.append(f"{label}: {cell.text}" if label else cell.text)
    return "; ".join(parts) or row.text
