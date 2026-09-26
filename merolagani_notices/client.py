"""HTTP access to merolagani.com with retries and polite rate limiting."""

from __future__ import annotations

import time

import requests
from lxml import html
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

BASE_URL = "https://merolagani.com"
LIST_URL = f"{BASE_URL}/AnnouncementList.aspx"
DETAIL_URL = f"{BASE_URL}/AnnouncementDetail.aspx"
API_URL = f"{BASE_URL}/handlers/webrequesthandler.ashx"

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0 Safari/537.36 merolagani-notices/1.0"
)

FISCAL_YEAR_FIELD = "ctl00$ContentPlaceHolder1$ddlFiscalYearFilter"


class MeroLaganiClient:
    """Thin wrapper around a requests session.

    Every request waits at least ``delay`` seconds after the previous one, and
    transient failures (429 / 5xx / connection errors) are retried with backoff.
    """

    def __init__(self, delay: float = 1.0, timeout: float = 30.0, retries: int = 3) -> None:
        self.delay = delay
        self.timeout = timeout
        self._last_request = 0.0

        self.session = requests.Session()
        self.session.headers.update({"User-Agent": USER_AGENT, "Accept-Language": "en-US,en;q=0.9"})
        retry = Retry(
            total=retries,
            backoff_factor=1.5,
            status_forcelist=(429, 500, 502, 503, 504),
            allowed_methods=("GET",),
        )
        adapter = HTTPAdapter(max_retries=retry)
        self.session.mount("https://", adapter)
        self.session.mount("http://", adapter)

    def _throttle(self) -> None:
        wait = self.delay - (time.monotonic() - self._last_request)
        if wait > 0:
            time.sleep(wait)
        self._last_request = time.monotonic()

    def get(self, url: str, **kwargs) -> requests.Response:
        self._throttle()
        response = self.session.get(url, timeout=self.timeout, **kwargs)
        response.raise_for_status()
        return response

    # ------------------------------------------------------------------ site API

    def fiscal_years(self) -> list[str]:
        """Fiscal years offered by the announcement filter, newest first (e.g. '083-084')."""
        page = html.fromstring(self.get(LIST_URL).text)
        values = page.xpath(f"//select[@name='{FISCAL_YEAR_FIELD}']/option/@value")
        return [v.strip() for v in values if v.strip()]

    def list_announcements(
        self, sector_id: int, fiscal_year: str = "", page: int = 1, page_size: int = 50
    ) -> list[dict]:
        """One page of announcements for a sector (all announcement types, newest first).

        This is the JSON endpoint behind the site's "Load More" button. It does not
        support filtering by announcement type, so callers filter by title.
        """
        params = {
            "type": "get_announcements",
            "symbol": "",
            "sectorID": sector_id,
            "fiscalYear": fiscal_year,
            "pageNumber": page,
            "pageSize": page_size,
        }
        data = self.get(API_URL, params=params).json()
        return data if isinstance(data, list) else []

    def announcement_page(self, announcement_id: int) -> str:
        return self.get(DETAIL_URL, params={"id": announcement_id}).text

    def download(self, url: str) -> tuple[bytes, str]:
        """Return (content, content_type) for an attachment URL."""
        response = self.get(url)
        return response.content, response.headers.get("Content-Type", "")
