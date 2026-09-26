"""Finding interest-rate announcements and parsing their detail pages."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from typing import Iterator

from lxml import html

from .client import DETAIL_URL, MeroLaganiClient

DEFAULT_KEYWORDS = ("interest rate",)


@dataclass(frozen=True)
class Sector:
    key: str
    id: int  # value of the site's "Sector" dropdown
    name: str


# Processing order matters: development banks first, then commercial banks.
SECTORS: dict[str, Sector] = {
    "development": Sector("development", 3, "Development Banks"),
    "commercial": Sector("commercial", 1, "Commercial Banks"),
}


@dataclass
class Announcement:
    id: int
    title: str
    date: date


@dataclass
class Notice:
    id: int
    title: str
    date: date | None
    fiscal_year: str
    symbol: str
    company: str
    attachments: list[str] = field(default_factory=list)

    @property
    def url(self) -> str:
        return f"{DETAIL_URL}?id={self.id}"


def is_interest_rate(title: str, keywords: tuple[str, ...] = DEFAULT_KEYWORDS) -> bool:
    text = " ".join(title.lower().split())
    return any(k.lower() in text for k in keywords)


# "<Bank> has published ...", "<Bank> has made correction ...", "<Bank> published a notice ..."
_PUBLISHED_RE = re.compile(r"\s+(?:has|have)\s+|\s+(?:re-?)?published\b", re.IGNORECASE)


def company_from_title(title: str) -> str:
    """'Garima Bikas Bank Limited has published a notice ...' -> 'garima bikas bank limited'."""
    parts = _PUBLISHED_RE.split(title, maxsplit=1)
    return parts[0].strip().lower() if len(parts) == 2 else ""


def iter_announcements(
    client: MeroLaganiClient, sector_id: int, fiscal_year: str = "", max_pages: int = 200
) -> Iterator[Announcement]:
    """Yield every announcement for a sector, newest first, across all pages."""
    seen: set[int] = set()
    for page in range(1, max_pages + 1):
        rows = client.list_announcements(sector_id, fiscal_year, page)
        if not rows:
            return
        for row in rows:
            aid = int(row["announcementID"])
            if aid in seen:
                continue
            seen.add(aid)
            yield Announcement(
                id=aid,
                title=" ".join(str(row.get("announcementDetail", "")).split()),
                date=date.fromisoformat(str(row["announcementDateAD"])[:10]),
            )


_SYMBOL_RE = re.compile(r"^\s*(\S+)\s*\((.+)\)\s*$")
_AD_DATE_RE = re.compile(r"(\d{4})/(\d{2})/(\d{2})\s*AD")
_FILE_URL_RE = re.compile(r"""fileUrl\s*=\s*["']([^"']+)["']""")


def parse_detail(page_html: str, announcement_id: int) -> Notice:
    """Extract company, date and attachment URLs from an AnnouncementDetail page."""
    doc = html.fromstring(page_html)

    fields: dict[str, str] = {}
    for row in doc.xpath("//table//tr"):
        cells = [" ".join(c.text_content().split()) for c in row.xpath("./th|./td")]
        if len(cells) >= 2 and cells[0]:
            fields.setdefault(cells[0], cells[1])

    symbol, company = "UNKNOWN", "Unknown Company"
    match = _SYMBOL_RE.match(fields.get("Symbol", ""))
    if match:
        symbol, company = match.group(1).upper(), match.group(2).strip()
    elif fields.get("Symbol"):
        symbol = fields["Symbol"].split()[0].upper()

    notice_date = None
    match = _AD_DATE_RE.search(fields.get("Announcement Date", ""))
    if match:
        notice_date = date(*map(int, match.groups()))

    return Notice(
        id=announcement_id,
        title=fields.get("Announcement Detail", ""),
        date=notice_date,
        fiscal_year=fields.get("Fiscal Year", ""),
        symbol=symbol,
        company=company,
        attachments=find_attachments(page_html, doc),
    )


def find_attachments(page_html: str, doc=None) -> list[str]:
    """Attachment URLs: images are set in a `fileUrl` JS variable, PDFs in a hidden input."""
    doc = doc if doc is not None else html.fromstring(page_html)
    candidates = _FILE_URL_RE.findall(page_html)
    candidates += doc.xpath("//input[contains(@id,'pdfviewer')]/@value")
    candidates += doc.xpath("//a[contains(@href,'/Uploads/')]/@href")

    urls: list[str] = []
    seen: set[str] = set()
    for url in candidates:
        url = url.strip()
        if not url:
            continue
        if url.startswith("//"):
            url = "https:" + url
        elif url.startswith("/"):
            url = "https://merolagani.com" + url
        key = re.sub(r"(?<!:)/{2,}", "/", url).lower()
        if key not in seen:
            seen.add(key)
            urls.append(url)
    return urls
