"""Month-wise store of extracted rates: notices/extracted/history/<SYMBOL>/<YYYY-MM>.json.

Each month is written once from that month's notice and then only read. A later notice in the
same month (e.g. a correction) replaces that month's entry; earlier months are never recalculated.
"""

from __future__ import annotations

import json
from pathlib import Path

from . import months


def month_of(record: dict) -> str | None:
    return record.get("month") or months.detect(record.get("effective", ""), record.get("notice_date"))


def save(history_dir: Path, record: dict) -> str | None:
    month = month_of(record)
    if not month:
        return None
    record = {**record, "month": month, "month_label": months.label(month)}
    path = history_dir / record["symbol"] / f"{month}.json"
    if path.exists():
        existing = json.loads(path.read_text(encoding="utf-8"))
        if int(existing.get("announcement_id", 0)) > int(record.get("announcement_id", 0)):
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


def as_of(bank_months: dict[str, dict], month: str) -> dict | None:
    """The bank's rates in force in `month`: its latest record from that month or earlier."""
    earlier = [m for m in bank_months if m <= month]
    return bank_months[max(earlier)] if earlier else None
