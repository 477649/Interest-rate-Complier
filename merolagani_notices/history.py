"""Month-wise store of extracted rates: notices/extracted/history/<SYMBOL>/<YYYY-MM>.json.

Each month is written once from that month's notice and then only read. A later notice in the
same month (e.g. a correction) replaces that month's entry; earlier months are never recalculated.

Carry-forward rule: when a bank's notice states that its rates remain unchanged ("unchanged": true)
or only changes some rates ("partial": true), every rate the notice does not give is taken from the
bank's previous month when the report is built. Stored records keep exactly what the notice said.
"""

from __future__ import annotations

import json
from pathlib import Path

from . import months

NS = "Not specified"
RATE_FIELDS = ["saving_rates", "call", "ind_lt1", "ind_1y", "ind_gt1", "inst_lt1", "inst_1y", "inst_gt1"]


def month_of(record: dict) -> str | None:
    return record.get("month") or months.detect(record.get("effective", ""), record.get("notice_date"))


def _is_carry_forward(record: dict) -> bool:
    return bool(record.get("unchanged") or record.get("partial"))


def save(history_dir: Path, record: dict) -> str | None:
    month = month_of(record)
    if not month:
        return None
    record = {**record, "month": month, "month_label": months.label(month)}
    path = history_dir / record["symbol"] / f"{month}.json"
    if path.exists():
        existing = json.loads(path.read_text(encoding="utf-8"))
        # an "unchanged" notice never replaces a notice that actually published rates for that month
        if record.get("unchanged") and not existing.get("unchanged"):
            return month
        newer_existing = int(existing.get("announcement_id", 0)) > int(record.get("announcement_id", 0))
        if newer_existing and not (existing.get("unchanged") and not record.get("unchanged")):
            return month  # keep the newer notice already stored for this month
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    return month


def load(history_dir: Path) -> dict[str, dict[str, dict]]:
    """{symbol: {month_key: record}}"""
    data: dict[str, dict[str, dict]] = {}
    for f in sorted(history_dir.glob("*/*.json")):
        try:
            rec = json.loads(f.read_text(encoding="utf-8"))
        except ValueError:
            continue
        data.setdefault(f.parent.name, {})[f.stem] = rec
    return data


def _missing(value) -> bool:
    return value in (None, NS, "", [])


def resolve(bank_months: dict[str, dict], month: str) -> dict | None:
    """The bank's rates in force in `month`, applying the carry-forward rule.

    Uses the bank's latest record from `month` or earlier. If that notice said rates are unchanged
    or partially changed, missing rates are filled from the bank's previous months.
    """
    earlier = sorted((m for m in bank_months if m <= month), reverse=True)
    if not earlier:
        return None
    record = dict(bank_months[earlier[0]])
    if not _is_carry_forward(record):
        return record

    filled = []
    for prev_month in earlier[1:]:
        prev = bank_months[prev_month]
        # saving products merge by name: the notice's products win, earlier products fill the rest
        if record.get("saving_products") and prev.get("saving_products"):
            merged = {**prev["saving_products"], **record["saving_products"]}
            if len(merged) > len(record["saving_products"]):
                filled.append(("saving_products", prev_month))
            record["saving_products"] = merged
            record["saving_rates"] = list(merged.values())
        for field in RATE_FIELDS:
            if _missing(record.get(field)) and not _missing(prev.get(field)):
                record[field] = prev[field]
                filled.append((field, prev_month))
        for side in ("individual", "institutional"):
            cur_pts = dict((record.get("fd_points") or {}).get(side) or {})
            prev_pts = (prev.get("fd_points") or {}).get(side) or {}
            for key, value in prev_pts.items():
                if _missing(cur_pts.get(key)) and not _missing(value):
                    cur_pts[key] = value
            if cur_pts:
                record.setdefault("fd_points", {})
                record["fd_points"] = {**record["fd_points"], side: cur_pts}
        if not _is_carry_forward(prev):
            break  # a full notice is the complete baseline; no need to look further back
    if filled:
        sources = sorted({months.label(m) for _, m in filled})
        kind = "rates remain unchanged" if record.get("unchanged") else "only some rates changed"
        record["notes"] = list(record.get("notes", [])) + [
            f"Notice states {kind}; unlisted rates carried forward from {', '.join(sources)}."]
    return record


def as_of(bank_months: dict[str, dict], month: str) -> dict | None:
    """Backward-compatible alias: rates in force in `month` (with carry-forward applied)."""
    return resolve(bank_months, month)
