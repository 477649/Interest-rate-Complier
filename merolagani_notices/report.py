"""Write the 'Interest Rate Summary' Excel workbook (with a 'Notes' sheet)."""

from __future__ import annotations

from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from .rules import NS, saving_min_max

SECTOR_ORDER = ["Development Banks", "Commercial Banks"]
FIELDS = ["call", "ind_lt1", "ind_1y", "ind_gt1", "inst_lt1", "inst_1y", "inst_gt1"]

_thin = Side(style="thin", color="8EA9C1")
BORDER = Border(left=_thin, right=_thin, top=_thin, bottom=_thin)
HEAD = PatternFill("solid", fgColor="0B2447")
SUB = PatternFill("solid", fgColor="19376D")
SECTOR = PatternFill("solid", fgColor="D9E7F5")
STRIPE = PatternFill("solid", fgColor="F5F9FD")
WHITE_BOLD = Font(bold=True, color="FFFFFF")
CENTER = Alignment(horizontal="center", vertical="center", wrap_text=True)


def _pct(value):
    return value / 100 if isinstance(value, (int, float)) and not isinstance(value, bool) else value


def build_report(records: list[dict], path: Path, stale: list[str] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    wb = Workbook()
    ws = wb.active
    ws.title = "Interest Rate Summary"

    ws.merge_cells("A1:J1")
    ws["A1"] = "Bank Deposit Interest Rate Summary"
    ws["A1"].font = Font(bold=True, size=14, color="0B2447")
    ws.row_dimensions[1].height = 26

    for rng, text in [("A3:A4", "Bank"), ("B3:C3", "Saving"), ("D3:D4", "Call"),
                      ("E3:G3", "Individual FD"), ("H3:J3", "Institution FD")]:
        ws.merge_cells(rng)
        ws[rng.split(":")[0]] = text
    for ref, text in {"B4": "Min", "C4": "Max", "E4": "Less Than 1 Year Max", "F4": "1 Year",
                      "G4": "More Than 1 Year Max", "H4": "Less Than 1 Year Max", "I4": "1 Year",
                      "J4": "More Than 1 Year Max"}.items():
        ws[ref] = text
    for row in (3, 4):
        for col in range(1, 11):
            c = ws.cell(row=row, column=col)
            c.font, c.alignment, c.border = WHITE_BOLD, CENTER, BORDER
            c.fill = HEAD if row == 3 else SUB
    ws.row_dimensions[4].height = 34

    notes_rows = []
    r = 5
    for sector in SECTOR_ORDER + sorted({x["sector"] for x in records} - set(SECTOR_ORDER)):
        group = sorted((x for x in records if x["sector"] == sector), key=lambda x: x["symbol"])
        if not group:
            continue
        ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=10)
        ws.cell(row=r, column=1, value=sector).font = Font(bold=True, color="0B2447")
        for col in range(1, 11):
            ws.cell(row=r, column=col).fill = SECTOR
            ws.cell(row=r, column=col).border = BORDER
        r += 1
        for i, rec in enumerate(group):
            smin, smax, snote = saving_min_max(rec.get("saving_rates", []))
            values = [rec["bank"], smin, smax] + [rec.get(f, NS) for f in FIELDS]
            for col, v in enumerate(values, start=1):
                c = ws.cell(row=r, column=col, value=_pct(v))
                c.border = BORDER
                if i % 2:
                    c.fill = STRIPE
                if col == 1:
                    c.alignment = Alignment(vertical="center")
                    continue
                c.alignment = CENTER
                if isinstance(c.value, float):
                    c.number_format = "0.00%"
                elif c.value == NS:
                    c.font = Font(italic=True, color="8A94A6")
            notes_rows.append((rec, rec.get("notes", []) + ([snote] if snote else [])))
            r += 1

    last = max(r - 1, 4)
    ws.auto_filter.ref = f"A4:J{last}"
    ws.freeze_panes = "B5"
    ws.column_dimensions["A"].width = 38
    for col in range(2, 11):
        texts = [str(ws.cell(row=rr, column=col).value) for rr in range(4, last + 1)
                 if isinstance(ws.cell(row=rr, column=col).value, str)]
        ws.column_dimensions[get_column_letter(col)].width = min(max([11] + [len(t) + 3 for t in texts]), 24)
    footer = ("Rule: Saving Max = second highest saving rate, excluding the first highest. "
              "See the Notes sheet for assumptions and missing values.")
    if stale:
        footer += f" Newer notices not yet extracted: {', '.join(stale)}."
    ws.cell(row=last + 2, column=1, value=footer).font = Font(italic=True, size=9, color="5A6475")

    ns = wb.create_sheet("Notes")
    for col, h in enumerate(["Bank", "Sector", "Effective Date", "Source Document", "Notes / Assumptions"], 1):
        c = ns.cell(row=1, column=col, value=h)
        c.font, c.fill, c.alignment, c.border = WHITE_BOLD, HEAD, CENTER, BORDER
    rows = [("All banks", "", "", "",
             "Saving Max is the second highest saving rate, excluding the first highest. Call and FCY accounts "
             "are excluded from saving rates; loan, base and spread rates are excluded. Remittance FD rates are "
             "excluded from Individual FD.")]
    for rec, notes in notes_rows:
        rows.append((rec["bank"], rec["sector"], rec.get("effective", ""),
                     rec.get("source_url", "Merolagani interest-rate notice"),
                     "\n".join(f"• {n}" for n in notes) or "—"))
    for rr, vals in enumerate(rows, start=2):
        for col, v in enumerate(vals, start=1):
            c = ns.cell(row=rr, column=col, value=v)
            c.border = BORDER
            c.alignment = Alignment(wrap_text=True, vertical="top")
    for letter, w in zip("ABCDE", (36, 18, 28, 48, 100)):
        ns.column_dimensions[letter].width = w
    ns.freeze_panes = "A2"
    wb.save(path)
