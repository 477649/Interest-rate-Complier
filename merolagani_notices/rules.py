"""The extraction rules for the Interest Rate Summary, applied to rates read from a notice.

Kept separate from the AI call so the rules are deterministic and unit-tested.
"""

from __future__ import annotations

NS = "Not specified"


def saving_min_max(rates: list[float]) -> tuple[float | str, float | str, str | None]:
    """Min = lowest saving rate. Max = second highest, excluding the first (single) highest rate.

    Rates are compared as distinct values, so products tied for the top rate are all excluded.
    Returns (min, max, note).
    """
    rates = [float(r) for r in rates if isinstance(r, (int, float))]
    if not rates:
        return NS, NS, None
    distinct = sorted(set(rates), reverse=True)
    if len(distinct) == 1:
        return distinct[0], distinct[0], "Only one saving rate available; used as both Min and Max."
    return min(rates), distinct[1], None


def _covers_12_months(row: dict) -> bool:
    start, end = row["from_months"], row.get("to_months")
    if start > 12:
        return False
    if end is None or end > 12:
        return True
    return end == 12 and bool(row.get("to_inclusive"))


def fd_buckets(rows: list[dict]) -> tuple[float | str, float | str, float | str]:
    """(Less Than 1 Year Max, 1 Year, More Than 1 Year Max) from general FD tenure rows.

    Each row: {"from_months": int, "to_months": int | None (open-ended), "to_inclusive": bool, "rate": float}
    - Less than 1 year: max rate of tenures starting below 12 months.
    - 1 year: the tenure that contains 12 months; the most specific one (latest start) wins,
      so "1 year and below 2 years" beats "3 months to 2 years".
    - More than 1 year: max rate of tenures that extend beyond 12 months.
    """
    rows = [r for r in rows if isinstance(r.get("rate"), (int, float))]
    if not rows:
        return NS, NS, NS

    below = [r["rate"] for r in rows if r["from_months"] < 12]
    one_year = [r for r in rows if _covers_12_months(r)]
    above = [r["rate"] for r in rows if r.get("to_months") is None or r["to_months"] > 12]

    lt1 = max(below) if below else NS
    y1 = max(one_year, key=lambda r: (r["from_months"], r["rate"]))["rate"] if one_year else NS
    gt1 = max(above) if above else NS
    return lt1, y1, gt1


FD_POINTS = [("3M", 3), ("6M", 6), ("1Y", 12), ("2Y", 24), ("3Y", 36), ("4Y", 48), ("5Y+", 60)]


def rate_at(rows: list[dict], months: int) -> float | str:
    """FD rate applying to a deposit of exactly `months` (the most specific matching tenure row)."""
    hits = []
    for r in rows:
        if not isinstance(r.get("rate"), (int, float)):
            continue
        start, end = r["from_months"], r.get("to_months")
        inside_end = end is None or months < end or (months == end and r.get("to_inclusive"))
        if start <= months and inside_end:
            hits.append(r)
    if not hits:
        return NS
    return max(hits, key=lambda r: (r["from_months"], r["rate"]))["rate"]


def fd_points(rows: list[dict]) -> dict[str, float | str]:
    """Rates at 3M, 6M, 1Y, 2Y, 3Y, 4Y and 5Y+ from general FD tenure rows."""
    return {label: rate_at(rows, m) for label, m in FD_POINTS}


def merge_partial(new: dict, previous: dict | None) -> dict:
    """For amendment notices that only change some rates, keep earlier values for the rest."""
    if not previous:
        return new
    merged = dict(new)
    for key in ("saving_rates", "call", "ind_lt1", "ind_1y", "ind_gt1", "inst_lt1", "inst_1y", "inst_gt1"):
        if merged.get(key) in (None, NS, []) and previous.get(key) not in (None, NS, []):
            merged[key] = previous[key]
    merged["notes"] = list(new.get("notes", [])) + [
        f"Partial amendment notice: unchanged rates carried over from announcement {previous.get('announcement_id')}."
    ]
    return merged
