"""Read each bank's latest notice with an OpenAI vision model and build the Excel summary.

    python -m merolagani_notices.extract            # extract new notices, then rebuild the report
    python -m merolagani_notices.extract --report-only

Needs the OPENAI_API_KEY environment variable (not needed with --report-only).
Results are cached per bank in notices/extracted/<SYMBOL>.json, keyed by announcement ID,
so a notice is only ever sent to the API once.
"""

from __future__ import annotations

import argparse
import base64
import csv
import io
import json
import logging
import os
import sys
from pathlib import Path

import requests

from . import history
from .report import build_report
from .rules import NS, fd_buckets, fd_points, merge_partial

log = logging.getLogger("merolagani_notices.extract")

API_URL = "https://api.openai.com/v1/chat/completions"
DEFAULT_MODEL = "gpt-4.1"

_FD_ROW = {
    "type": "object",
    "additionalProperties": False,
    "required": ["tenure_text", "from_months", "to_months", "to_inclusive", "rate"],
    "properties": {
        "tenure_text": {"type": "string"},
        "from_months": {"type": "integer"},
        "to_months": {"type": ["integer", "null"]},
        "to_inclusive": {"type": "boolean"},
        "rate": {"type": "number"},
    },
}

SCHEMA = {
    "name": "interest_rate_notice",
    "strict": True,
    "schema": {
        "type": "object",
        "additionalProperties": False,
        "required": ["bank_name", "effective_date", "is_partial_amendment", "saving_rates", "call",
                     "individual_fd", "institutional_fd", "notes", "unclear"],
        "properties": {
            "bank_name": {"type": "string"},
            "effective_date": {"type": "string"},
            "is_partial_amendment": {"type": "boolean"},
            "saving_rates": {"type": "array", "items": {
                "type": "object", "additionalProperties": False, "required": ["product", "rate"],
                "properties": {"product": {"type": "string"}, "rate": {"type": "number"}}}},
            "call": {"type": "string"},
            "individual_fd": {"type": "array", "items": _FD_ROW},
            "institutional_fd": {"type": "array", "items": _FD_ROW},
            "notes": {"type": "array", "items": {"type": "string"}},
            "unclear": {"type": "array", "items": {"type": "string"}},
        },
    },
}

PROMPT = """You read Nepali bank interest-rate notices (English or Nepali) and return deposit rates as JSON.
Read the whole image carefully. Accuracy matters more than completeness: never guess.

- bank_name: from the header/logo.
- effective_date: as written (e.g. "1 Ashwin 2083 (17 Sep 2026)"); "" if absent.
- is_partial_amendment: true if the notice only amends some rates (e.g. only FCY deposits or loans)
  and says other rates remain unchanged.
- saving_rates: every NPR (LCY) saving account product and its rate, one entry per product, including
  remittance, staff and special saving accounts. EXCLUDE call, current, margin, locker, recurring,
  fixed deposits and all foreign-currency (FCY/USD/EUR...) accounts.
- call: the NPR call deposit rate exactly as written, keeping wording like "Up to 1.375%" and the % sign.
  If only described in words (e.g. "as per agreement"), give those words. If absent: "Not specified".
- individual_fd / institutional_fd: the GENERAL NPR fixed-deposit tenure rows only. Exclude remittance FD,
  recurring deposits, FCY deposits, app-only/online rates when an in-person rate exists, and named special
  schemes. For each row give tenure_text as printed, from_months, to_months (null if open-ended, e.g.
  "5 years and above"), to_inclusive (true for "up to 1 year" / "6 months to 1 year", false for
  "below 1 year" / "and below 2 years"), and rate as a number (2.75 for 2.75%).
  Institutional = Institution / Corporate / Non-individual. If one rate is given for a range such as
  "6 months and above", return one row. Tenures shown as "-" or N/A are omitted.
- notes: short notes on assumptions (e.g. which product you treated as general).
- unclear: anything you could not read with confidence. Leave the related rate out rather than guessing.
Do not include loan, base, spread or premium rates."""


def image_data_url(path: Path) -> str:
    """PNG data URL of the first frame (GIF notices are converted), scaled down if very large."""
    from PIL import Image

    with Image.open(path) as img:
        img.seek(0)
        img = img.convert("RGB")
        if max(img.size) > 3000:
            img.thumbnail((3000, 3000))
        buf = io.BytesIO()
        img.save(buf, "PNG", optimize=True)
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


def call_model(image: Path, api_key: str, model: str, timeout: float = 180) -> dict:
    body = {
        "model": model,
        "temperature": 0,
        "response_format": {"type": "json_schema", "json_schema": SCHEMA},
        "messages": [
            {"role": "system", "content": PROMPT},
            {"role": "user", "content": [
                {"type": "text", "text": "Extract the deposit interest rates from this notice."},
                {"type": "image_url", "image_url": {"url": image_data_url(image), "detail": "high"}},
            ]},
        ],
    }
    r = requests.post(API_URL, json=body, timeout=timeout,
                      headers={"Authorization": f"Bearer {api_key}"})
    if r.status_code >= 400:
        raise RuntimeError(f"OpenAI API error {r.status_code}: {r.text[:300]}")
    message = r.json()["choices"][0]["message"]
    if message.get("refusal"):
        raise RuntimeError(f"Model refused: {message['refusal']}")
    return json.loads(message["content"])


def to_record(raw: dict, notice: dict) -> dict:
    """Apply the summary rules to the model's raw reading."""
    ind = fd_buckets(raw["individual_fd"])
    inst = fd_buckets(raw["institutional_fd"])
    notes = list(raw.get("notes", []))
    notes += [f"Unclear: {u}" for u in raw.get("unclear", [])]
    return {
        "symbol": notice["symbol"],
        "bank": raw.get("bank_name") or notice["company"],
        "sector": notice["sector"],
        "announcement_id": int(notice["announcement_id"]),
        "notice_date": notice["date"],
        "effective": raw.get("effective_date") or notice["date"],
        "source_url": notice["source_url"],
        "saving_rates": [s["rate"] for s in raw["saving_rates"]],
        "call": raw.get("call") or NS,
        "ind_lt1": ind[0], "ind_1y": ind[1], "ind_gt1": ind[2],
        "inst_lt1": inst[0], "inst_1y": inst[1], "inst_gt1": inst[2],
        "fd_points": {"individual": fd_points(raw["individual_fd"]),
                      "institutional": fd_points(raw["institutional_fd"])},
        "partial": bool(raw.get("is_partial_amendment")),
        "notes": notes,
        "extracted_by": "openai",
        "raw": raw,
    }


def latest_notices(notices_dir: Path) -> list[dict]:
    """One row per bank (its current notice image) from manifest.csv."""
    manifest = notices_dir / "manifest.csv"
    if not manifest.exists():
        return []
    banks: dict[str, dict] = {}
    with manifest.open(newline="", encoding="utf-8-sig") as fh:
        for row in csv.DictReader(fh):
            if not row.get("file") or row["file"].lower().endswith(".pdf"):
                continue
            current = banks.get(row["symbol"])
            # newest by publication date; IDs are not always chronological (e.g. correction notices)
            order = lambda r: (r.get("date", ""), int(r["announcement_id"]))
            if current is None or order(row) > order(current):
                banks[row["symbol"]] = row
            elif row["announcement_id"] == current["announcement_id"] and row["file"].endswith(".png"):
                banks[row["symbol"]] = row  # prefer the PNG copy when both exist
    return sorted(banks.values(), key=lambda r: r["symbol"])


def load_cache(folder: Path) -> dict[str, dict]:
    cache = {}
    for f in sorted(folder.glob("*.json")):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            cache[data["symbol"]] = data
        except (ValueError, KeyError):
            log.warning("ignoring unreadable cache file %s", f)
    return cache


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="merolagani_notices.extract", description=__doc__.split("\n\n")[0])
    p.add_argument("--notices", type=Path, default=Path("notices"), help="notices folder (default ./notices)")
    p.add_argument("--report", type=Path, default=Path("reports/Interest_Rate_Summary.xlsx"),
                   help="Excel output path (default reports/Interest_Rate_Summary.xlsx)")
    p.add_argument("--model", default=os.environ.get("OPENAI_MODEL") or DEFAULT_MODEL,
                   help=f"OpenAI model (default {DEFAULT_MODEL}, or $OPENAI_MODEL)")
    p.add_argument("--report-only", action="store_true", help="rebuild the Excel file without calling the API")
    p.add_argument("--force", action="store_true", help="re-extract every notice, ignoring the cache")
    args = p.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    cache_dir = args.notices / "extracted"
    history_dir = cache_dir / "history"
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache = load_cache(cache_dir)
    notices = latest_notices(args.notices)
    by_symbol = {n["symbol"]: n for n in notices}

    # make sure every cached record is filed under its Nepali month (one-time for older caches)
    stored = history.load(history_dir)
    for symbol, rec in cache.items():
        if not rec.get("notice_date") and symbol in by_symbol \
                and int(by_symbol[symbol]["announcement_id"]) == rec.get("announcement_id"):
            rec["notice_date"] = by_symbol[symbol]["date"]
        month = history.month_of(rec)
        if month and month not in stored.get(symbol, {}):
            history.save(history_dir, rec)

    pending = [n for n in notices
               if args.force or cache.get(n["symbol"], {}).get("announcement_id") != int(n["announcement_id"])]
    failed = 0
    if pending and not args.report_only:
        api_key = os.environ.get("OPENAI_API_KEY", "").strip()
        if not api_key:
            log.warning("OPENAI_API_KEY is not set: %d new notice(s) not extracted; report uses cached data.",
                        len(pending))
        else:
            log.info("Extracting %d notice(s) with %s", len(pending), args.model)
            for n in pending:
                try:
                    raw = call_model(args.notices / n["file"], api_key, args.model)
                except Exception as exc:  # keep going; one bad notice must not stop the rest
                    failed += 1
                    log.warning("  ! %s: %s", n["symbol"], exc)
                    continue
                record = to_record(raw, n)
                if record["partial"]:
                    record = merge_partial(record, cache.get(n["symbol"]))
                (cache_dir / f"{n['symbol']}.json").write_text(
                    json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
                cache[n["symbol"]] = record
                month = history.save(history_dir, record)
                log.info("  + %s  %s  (%s)", n["symbol"], record["bank"],
                         history.months.label(month) if month else "month unknown")
    elif pending:
        log.info("%d notice(s) not yet extracted (--report-only).", len(pending))

    current = {n["symbol"] for n in notices}
    records = [r for s, r in cache.items() if not current or s in current]
    stale = sorted(n["symbol"] for n in notices
                   if cache.get(n["symbol"], {}).get("announcement_id") != int(n["announcement_id"]))
    build_report(records, args.report, stale=stale, history_dir=history_dir)
    log.info("Report: %s (%d banks%s)", args.report, len(records),
             f", {len(stale)} awaiting extraction" if stale else "")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
