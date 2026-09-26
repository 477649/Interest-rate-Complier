"""Excel report: previous month vs current month for every rate, with a coloured Changes column.

Sheets:
  Interest Rate Summary  – Bank | Saving (Min, Max) | Call | Individual FD x3 | Institution FD x3,
                           each as <current month> | <previous month> | Changes
  Monthly History        – every bank and every stored month (Shrawan ... Ashadh)
  Notes                  – effective dates, sources and assumptions for the current month
"""

from __future__ import annotations

import re
from pathlib import Path

from openpyxl import Workbook
from openpyxl.formatting.rule import FormulaRule
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from . import history, months
from .rules import NS, saving_min_max

SECTOR_ORDER = ["Development Banks", "Commercial Banks"]

# (group, sub-label prefix, value getter)
METRICS = [
    ("Saving", "Min", lambda r: saving_min_max(r.get("saving_rates", []))[0]),
    ("Saving", "Max", lambda r: saving_min_max(r.get("saving_rates", []))[1]),
    ("Call", "", lambda r: r.get("call", NS)),
    ("Individual FD", "Less Than 1 Year Max", lambda r: r.get("ind_lt1", NS)),
    ("Individual FD", "1 Year", lambda r: r.get("ind_1y", NS)),
    ("Individual FD", "More Than 1 Year Max", lambda r: r.get("ind_gt1", NS)),
    ("Institution FD", "Less Than 1 Year Max", lambda r: r.get("inst_lt1", NS)),
    ("Institution FD", "1 Year", lambda r: r.get("inst_1y", NS)),
    ("Institution FD", "More Than 1 Year Max", lambda r: r.get("inst_gt1", NS)),
]

_thin = Side(style="thin", color="8EA9C1")
BORDER = Border(left=_thin, right=_thin, top=_thin, bottom=_thin)
HEAD = PatternFill("solid", fgColor="0B2447")
SUB = PatternFill("solid", fgColor="19376D")
CHANGE_HEAD = PatternFill("solid", fgColor="24477F")
SECTOR = PatternFill("solid", fgColor="D9E7F5")
STRIPE = PatternFill("solid", fgColor="F5F9FD")
WHITE_BOLD = Font(bold=True, color="FFFFFF")
CENTER = Alignment(horizontal="center", vertical="center", wrap_text=True)
UP = (PatternFill("solid", fgColor="C6EFCE"), Font(color="006100", bold=True))
DOWN = (PatternFill("solid", fgColor="FFC7CE"), Font(color="9C0006", bold=True))
SAME = (PatternFill("solid", fgColor="EDEDED"), Font(color="595959"))
_NUM = re.compile(r"(\d+(?:\.\d+)?)\s*%?")


def _number(value) -> float | None:
    """Rate as a number: 2.75 -> 2.75, 'Up to 1.375%' -> 1.375, 'As per agreement' -> None."""
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    # "up to 50% of minimum saving rate" describes a formula, not a rate
    if isinstance(value, str) and not re.search(r"%\s+of\b", value, re.IGNORECASE):
        found = _NUM.findall(value)
        if len(found) == 1:
            return float(found[0])
    return None


def change(prev, curr):
    """Difference in percentage points (as an Excel fraction), or '—' when not comparable."""
    a, b = _number(prev), _number(curr)
    if a is None or b is None:
        if prev in (None, NS) or curr in (None, NS):
            return "—"
        return "—" if str(prev).strip() == str(curr).strip() else "Changed"
    return round((b - a) / 100, 6)


def _cell_value(value):
    if value is None:
        return "—"
    return value / 100 if isinstance(value, (int, float)) and not isinstance(value, bool) else value


def _style_value(c, stripe: bool):
    c.border = BORDER
    c.alignment = CENTER
    if stripe:
        c.fill = STRIPE
    if isinstance(c.value, float):
        c.number_format = "0.00%"
    elif c.value in (NS, "—"):
        c.font = Font(italic=True, color="8A94A6")


def build_report(records: list[dict], path: Path, stale: list[str] | None = None,
                 history_dir: Path | None = None) -> None:
    """Build the comparison workbook from the month-wise history (falls back to `records`)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    store = history.load(history_dir) if history_dir and history_dir.exists() else {}
    for rec in records:  # make sure every current record is represented
        month = history.month_of(rec)
        if month:
            store.setdefault(rec["symbol"], {}).setdefault(month, {**rec, "month": month})
    all_months = sorted({m for bank in store.values() for m in bank})
    current = all_months[-1] if all_months else None
    prev = months.previous(current) if current else None
    cur_label = months.label(current) if current else "Current"
    prev_label = months.label(prev) if prev else "Previous"

    wb = Workbook()
    ws = wb.active
    ws.title = "Interest Rate Summary"
    ncols = 1 + 3 * len(METRICS)
    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=ncols)
    ws["A1"] = f"Bank Deposit Interest Rates — {cur_label} vs {prev_label}"
    ws["A1"].font = Font(bold=True, size=14, color="0B2447")
    ws.row_dimensions[1].height = 26

    # headers: row 3 = group, row 4 = "<metric> <month>" / Changes
    ws.merge_cells("A3:A4")
    ws["A3"] = "Bank"
    col = 2
    change_cols = []
    groups: dict[str, list[int]] = {}
    for group, sub, _ in METRICS:
        prefix = f"{sub} " if sub else ""
        for offset, text in enumerate((f"{prefix}{cur_label}", f"{prefix}{prev_label}",
                                       f"{sub} Changes".strip() if sub and group != "Saving" else "Changes")):
            ws.cell(row=4, column=col + offset, value=text)
        groups.setdefault(group, []).extend(range(col, col + 3))
        change_cols.append(col + 2)
        col += 3
    for group, cols in groups.items():
        ws.merge_cells(start_row=3, start_column=cols[0], end_row=3, end_column=cols[-1])
        ws.cell(row=3, column=cols[0], value=group)
    for row in (3, 4):
        for c in range(1, ncols + 1):
            cell = ws.cell(row=row, column=c)
            cell.font, cell.alignment, cell.border = WHITE_BOLD, CENTER, BORDER
            cell.fill = HEAD if row == 3 else (CHANGE_HEAD if c in change_cols else SUB)
    ws.row_dimensions[3].height = 22
    ws.row_dimensions[4].height = 48

    # data rows
    notes_rows = []
    r = 5
    banks = {}
    for symbol, bank_months in store.items():
        latest = bank_months[max(bank_months)]
        banks[symbol] = latest
    sectors = SECTOR_ORDER + sorted({b["sector"] for b in banks.values()} - set(SECTOR_ORDER))
    first_data_row = r
    for sector in sectors:
        symbols = sorted(s for s, b in banks.items() if b["sector"] == sector)
        if not symbols:
            continue
        ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=ncols)
        ws.cell(row=r, column=1, value=sector).font = Font(bold=True, color="0B2447")
        for c in range(1, ncols + 1):
            ws.cell(row=r, column=c).fill = SECTOR
            ws.cell(row=r, column=c).border = BORDER
        r += 1
        for i, symbol in enumerate(symbols):
            now = history.as_of(store[symbol], current) or {}
            before = history.as_of(store[symbol], prev) if prev else None
            name_cell = ws.cell(row=r, column=1, value=banks[symbol]["bank"])
            name_cell.border = BORDER
            name_cell.alignment = Alignment(vertical="center")
            if i % 2:
                name_cell.fill = STRIPE
            c = 2
            for _, _, getter in METRICS:
                pv = getter(before) if before else None
                cv = getter(now) if now else None
                # column order: current month | previous month | change (current - previous)
                for offset, v in enumerate((cv, pv, change(pv, cv) if before and now else "—")):
                    cell = ws.cell(row=r, column=c + offset, value=_cell_value(v) if offset < 2 else v)
                    _style_value(cell, bool(i % 2))
                    if offset == 2 and isinstance(cell.value, float):
                        cell.number_format = "+0.00%;-0.00%;0.00%"
                c += 3
            if now:
                notes = list(now.get("notes", []))
                if now.get("month") != current:
                    notes.insert(0, f"No new notice for {cur_label}; rates from {months.label(now['month'])}.")
                notes_rows.append((now, notes))
            r += 1
    last = max(r - 1, 4)

    # conditional colours on the Changes columns (numbers only; '—' stays neutral)
    for c in change_cols:
        letter = get_column_letter(c)
        rng = f"{letter}{first_data_row}:{letter}{last}"
        top = f"{letter}{first_data_row}"
        for formula, (fill, font) in ((f"AND(ISNUMBER({top}),{top}>0)", UP),
                                      (f"AND(ISNUMBER({top}),{top}<0)", DOWN),
                                      (f"AND(ISNUMBER({top}),{top}=0)", SAME)):
            ws.conditional_formatting.add(rng, FormulaRule(formula=[formula], fill=fill, font=font))
        ws.conditional_formatting.add(rng, FormulaRule(formula=[f'{top}="Changed"'], fill=PatternFill(
            "solid", fgColor="FFEB9C"), font=Font(color="9C5700", bold=True)))

    ws.auto_filter.ref = f"A4:{get_column_letter(ncols)}{last}"
    ws.freeze_panes = "B5"
    ws.column_dimensions["A"].width = 36
    for c in range(2, ncols + 1):
        ws.column_dimensions[get_column_letter(c)].width = 12 if c in change_cols else 14
    footer = ("Changes = current month minus previous month (percentage points): green = increase, "
              "red = decrease, grey = no change, '—' = not comparable. Saving Max = second highest saving "
              "rate, excluding the first highest.")
    if stale:
        footer += f" Newer notices not yet extracted: {', '.join(stale)}."
    ws.cell(row=last + 2, column=1, value=footer).font = Font(italic=True, size=9, color="5A6475")

    _dev_spread_sheet(wb, store, current, cur_label)
    _history_sheet(wb, store)
    _notes_sheet(wb, notes_rows, cur_label)
    wb.save(path)


SPREAD_POINTS = [("3M", "3 Months"), ("6M", "6 Months"), ("1Y", "1 Year (12 Months)"), ("2Y", "2 Years"),
                 ("3Y", "3 Years"), ("4Y", "4 Years"), ("5Y+", "5 Years & Above")]


def _dev_spread_sheet(wb: Workbook, store: dict, current: str | None, cur_label: str) -> None:
    """Development banks only: Individual vs Institutional FD rate and their difference, per tenure."""
    ws = wb.create_sheet("Development FD Spread")
    ncols = 1 + 3 * len(SPREAD_POINTS)
    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=ncols)
    ws["A1"] = f"Development Banks — Fixed Deposit: Individual vs Institutional ({cur_label})"
    ws["A1"].font = Font(bold=True, size=14, color="0B2447")
    ws.row_dimensions[1].height = 26

    ws.merge_cells("A3:A4")
    ws["A3"] = "Bank"
    diff_cols = []
    for i, (_, label) in enumerate(SPREAD_POINTS):
        c = 2 + 3 * i
        ws.merge_cells(start_row=3, start_column=c, end_row=3, end_column=c + 2)
        ws.cell(row=3, column=c, value=label)
        for off, text in enumerate(("Individual", "Institutional", "Difference")):
            ws.cell(row=4, column=c + off, value=text)
        diff_cols.append(c + 2)
    for row in (3, 4):
        for c in range(1, ncols + 1):
            cell = ws.cell(row=row, column=c)
            cell.font, cell.alignment, cell.border = WHITE_BOLD, CENTER, BORDER
            cell.fill = HEAD if row == 3 else (CHANGE_HEAD if c in diff_cols else SUB)
    ws.row_dimensions[3].height = 22
    ws.row_dimensions[4].height = 30

    r = 5
    for i, symbol in enumerate(sorted(store)):
        rec = history.as_of(store[symbol], current) if current else None
        if not rec or rec.get("sector") != "Development Banks":
            continue
        points = rec.get("fd_points") or {}
        ind, inst = points.get("individual", {}), points.get("institutional", {})
        name = ws.cell(row=r, column=1, value=rec["bank"])
        name.border = BORDER
        stripe = (r - 5) % 2 == 1
        if stripe:
            name.fill = STRIPE
        for j, (key, _) in enumerate(SPREAD_POINTS):
            a, b = ind.get(key, "—" if not points else NS), inst.get(key, "—" if not points else NS)
            diff = round((a - b) / 100, 6) if isinstance(a, (int, float)) and isinstance(b, (int, float)) else "—"
            for off, v in enumerate((a, b, diff)):
                cell = ws.cell(row=r, column=2 + 3 * j + off, value=_cell_value(v) if off < 2 else v)
                _style_value(cell, stripe)
                if off == 2 and isinstance(cell.value, float):
                    cell.number_format = "+0.00%;-0.00%;0.00%"
        r += 1
    last = max(r - 1, 5)

    for c in diff_cols:
        letter = get_column_letter(c)
        rng, top = f"{letter}5:{letter}{last}", f"{letter}5"
        for formula, (fill, font) in ((f"AND(ISNUMBER({top}),{top}>0)", UP),
                                      (f"AND(ISNUMBER({top}),{top}<0)", DOWN),
                                      (f"AND(ISNUMBER({top}),{top}=0)", SAME)):
            ws.conditional_formatting.add(rng, FormulaRule(formula=[formula], fill=fill, font=font))
    ws.auto_filter.ref = f"A4:{get_column_letter(ncols)}{last}"
    ws.freeze_panes = "B5"
    ws.column_dimensions["A"].width = 36
    for c in range(2, ncols + 1):
        ws.column_dimensions[get_column_letter(c)].width = 12
    ws.cell(row=last + 2, column=1, value=(
        "Difference = Individual rate minus Institutional rate (percentage points): green = individuals earn more, "
        "red = institutions earn more, grey = same. 'Not specified' = the bank publishes no rate for that tenure "
        "(e.g. institutional FD starting at 6 months or 1 year). Rates are the general FD rate applying to a "
        "deposit of exactly that tenure; '5 Years & Above' uses the band covering 5 years.")).font = \
        Font(italic=True, size=9, color="5A6475")


def _history_sheet(wb: Workbook, store: dict) -> None:
    hs = wb.create_sheet("Monthly History")
    headers = ["Bank", "Sector", "Month", "Fiscal Month #", "Saving Min", "Saving Max", "Call",
               "Individual FD <1Y Max", "Individual FD 1Y", "Individual FD >1Y Max",
               "Institution FD <1Y Max", "Institution FD 1Y", "Institution FD >1Y Max", "Effective Date"]
    for c, h in enumerate(headers, 1):
        cell = hs.cell(row=1, column=c, value=h)
        cell.font, cell.fill, cell.alignment, cell.border = WHITE_BOLD, HEAD, CENTER, BORDER
    rows = []
    for symbol, bank_months in store.items():
        for month, rec in bank_months.items():
            rows.append((rec.get("sector", ""), rec.get("bank", symbol), month, rec))
    rows.sort(key=lambda x: (SECTOR_ORDER.index(x[0]) if x[0] in SECTOR_ORDER else 9, x[1], x[2]))
    for r, (sector, bank, month, rec) in enumerate(rows, start=2):
        name = months.label(month)
        values = [bank, sector, name, months.FISCAL_ORDER.index(name.split()[0]) + 1] + \
                 [getter(rec) for _, _, getter in METRICS] + [rec.get("effective", "")]
        for c, v in enumerate(values, 1):
            cell = hs.cell(row=r, column=c, value=_cell_value(v) if 5 <= c <= 13 else v)
            _style_value(cell, r % 2 == 1)
    for c, w in enumerate([36, 18, 16, 10] + [13] * 9 + [30], 1):
        hs.column_dimensions[get_column_letter(c)].width = w
    hs.freeze_panes = "B2"
    hs.auto_filter.ref = f"A1:{get_column_letter(len(headers))}{max(len(rows) + 1, 2)}"


def _notes_sheet(wb: Workbook, notes_rows: list, cur_label: str) -> None:
    ns = wb.create_sheet("Notes")
    for c, h in enumerate(["Bank", "Sector", "Effective Date", "Source Document", f"Notes ({cur_label})"], 1):
        cell = ns.cell(row=1, column=c, value=h)
        cell.font, cell.fill, cell.alignment, cell.border = WHITE_BOLD, HEAD, CENTER, BORDER
    rows = [("All banks", "", "", "",
             "Saving Max is the second highest saving rate, excluding the first highest. Call and FCY accounts "
             "are excluded from saving rates; loan, base and spread rates are excluded. Remittance FD rates are "
             "excluded from Individual FD. Months follow the Nepali calendar (Shrawan to Ashadh).")]
    for rec, notes in notes_rows:
        rows.append((rec["bank"], rec.get("sector", ""), rec.get("effective", ""),
                     rec.get("source_url", "Merolagani interest-rate notice"),
                     "\n".join(f"• {n}" for n in notes) or "—"))
    for r, vals in enumerate(rows, start=2):
        for c, v in enumerate(vals, 1):
            cell = ns.cell(row=r, column=c, value=v)
            cell.border = BORDER
            cell.alignment = Alignment(wrap_text=True, vertical="top")
    for letter, w in zip("ABCDE", (36, 18, 28, 48, 100)):
        ns.column_dimensions[letter].width = w
    ns.freeze_panes = "A2"
