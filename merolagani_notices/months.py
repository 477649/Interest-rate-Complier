"""Nepali (Bikram Sambat) month detection for interest-rate notices.

Months are keyed chronologically as "YYYY-MM" with the BS calendar month number
(Baisakh = 01 ... Chaitra = 12), and labelled like "Ashwin 2083".
"""

from __future__ import annotations

import re
from datetime import date, timedelta

# Calendar order: Baisakh is month 1 of the BS year.
MONTHS = ["Baisakh", "Jestha", "Ashadh", "Shrawan", "Bhadra", "Ashwin",
          "Kartik", "Mangsir", "Poush", "Magh", "Falgun", "Chaitra"]
# Fiscal-year order (Shrawan to Ashadh), used for display
FISCAL_ORDER = MONTHS[3:] + MONTHS[:3]

_ALIASES = {
    1: ["baisakh", "baishakh", "vaisakh", "vaishakh", "बैशाख", "वैशाख"],
    2: ["jestha", "jeshtha", "jeth", "jesth", "जेठ", "ज्येष्ठ", "जेष्ठ"],
    3: ["ashadh", "ashad", "asadh", "asar", "ashar", "असार", "आषाढ", "आषाढ़"],
    4: ["shrawan", "shravan", "srawan", "sawan", "saun", "साउन", "श्रावण"],
    5: ["bhadra", "bhadau", "bhadra", "भदौ", "भाद्र"],
    6: ["ashwin", "aswin", "ashvin", "ashoj", "asoj", "ashwoj", "असोज", "आश्विन", "अश्विन"],
    7: ["kartik", "kartika", "kattik", "कात्तिक", "कार्तिक"],
    8: ["mangsir", "mangshir", "margashirsha", "mansir", "मंसिर", "मङ्सिर", "मार्गशीर्ष"],
    9: ["poush", "paush", "push", "pus", "पुस", "पौष"],
    10: ["magh", "माघ"],
    11: ["falgun", "phalgun", "fagun", "फागुन", "फाल्गुन"],
    12: ["chaitra", "chait", "चैत", "चैत्र"],
}
_NAME_RE = re.compile(
    "|".join(sorted((re.escape(a) for names in _ALIASES.values() for a in names), key=len, reverse=True)),
    re.IGNORECASE,
)
_LOOKUP = {a.lower(): m for m, names in _ALIASES.items() for a in names}
_DEVANAGARI = str.maketrans("०१२३४५६७८९", "0123456789")
_BS_NUMERIC = re.compile(r"\b(20[6-9]\d)\s*[/.\-]\s*(\d{1,2})\s*[/.\-]\s*\d{1,2}\b")
_BS_YEAR = re.compile(r"\b(20[6-9]\d)\b")


def key(year: int, month: int) -> str:
    return f"{year}-{month:02d}"


def label(month_key: str) -> str:
    year, month = month_key.split("-")
    return f"{MONTHS[int(month) - 1]} {year}"


def previous(month_key: str) -> str:
    year, month = map(int, month_key.split("-"))
    return key(year - 1, 12) if month == 1 else key(year, month - 1)


def from_text(text: str) -> str | None:
    """Month key from an effective-date text such as '1st Ashwin 2083' or '2083/06/01'."""
    text = (text or "").translate(_DEVANAGARI)
    numeric = _BS_NUMERIC.search(text)
    if numeric and 1 <= int(numeric.group(2)) <= 12:
        return key(int(numeric.group(1)), int(numeric.group(2)))
    name = _NAME_RE.search(text)
    year = _BS_YEAR.search(text)
    if name and year:
        return key(int(year.group(1)), _LOOKUP[name.group(0).lower()])
    return None


def from_ad_date(d: date) -> str:
    """Approximate BS month for an AD date (BS months start around the 14th-17th of each AD month).

    Notices are usually published the day before the new month, so the date is shifted by one day.
    """
    d = d + timedelta(days=1)
    start_day = 13 if d.month == 4 else 15
    ad_month = d.month if d.day >= start_day else d.month - 1 or 12
    ad_year = d.year if not (d.day < start_day and d.month == 1) else d.year - 1
    # AD month 4 (mid-April) -> Baisakh (1) ... AD month 3 (mid-March) -> Chaitra (12)
    bs_month = (ad_month - 4) % 12 + 1
    bs_year = ad_year + 57 if ad_month >= 4 else ad_year + 56
    return key(bs_year, bs_month)


def detect(effective_text: str, notice_date: str | date | None) -> str | None:
    found = from_text(effective_text)
    if found:
        return found
    if isinstance(notice_date, str) and re.match(r"\d{4}-\d{2}-\d{2}", notice_date):
        notice_date = date.fromisoformat(notice_date[:10])
    return from_ad_date(notice_date) if isinstance(notice_date, date) else None
