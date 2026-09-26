"""Offline tests for parsing and file naming (no network access needed).

Run with:  python -m unittest discover -s tests -v
"""

import csv
import tempfile
import unittest
from datetime import date
from pathlib import Path

from merolagani_notices.scraper import (
    SECTORS, company_from_title, find_attachments, is_interest_rate, parse_detail,
)
from merolagani_notices.storage import Manifest, bank_folder, guess_extension, safe_name

DETAIL_PAGE = """
<html><body>
<table>
  <tr><th>Symbol</th><td><a href="/CompanyDetail.aspx?symbol=CORBL">CORBL (Corporate Development Bank Limited)</a></td></tr>
  <tr><th>Fiscal Year</th><td>083-084</td></tr>
  <tr><th>Announcement Detail</th><td>Corporate Development Bank Limited has published a notice regarding
      new interest rate on deposit, loan and advances.</td></tr>
  <tr><th>Announcement Date</th><td>2026/09/16 AD (2083/05/31 BS)</td></tr>
</table>
<input type="hidden" id="ctl00_ContentPlaceHolder1_pdfviewer" value="" />
<script>
  $(document).ready(function () {
      var fileUrl = "https://images.merolagani.com//Uploads/Repository/639251393071781414.gif";
  });
</script>
</body></html>
"""

PDF_PAGE = """
<html><body>
<table><tr><th>Symbol</th><td>NABIL (Nabil Bank Limited)</td></tr></table>
<input type="hidden" id="ctl00_ContentPlaceHolder1_pdfviewer" value="/Uploads/Repository/123.pdf" />
<script>var fileUrl = "";</script>
</body></html>
"""


class ParseDetailTests(unittest.TestCase):
    def test_extracts_company_date_and_image(self):
        notice = parse_detail(DETAIL_PAGE, 67425)
        self.assertEqual(notice.symbol, "CORBL")
        self.assertEqual(notice.company, "Corporate Development Bank Limited")
        self.assertEqual(notice.fiscal_year, "083-084")
        self.assertEqual(notice.date, date(2026, 9, 16))
        self.assertEqual(notice.attachments,
                         ["https://images.merolagani.com//Uploads/Repository/639251393071781414.gif"])
        self.assertTrue(notice.url.endswith("AnnouncementDetail.aspx?id=67425"))

    def test_pdf_attachment_from_hidden_input(self):
        self.assertEqual(find_attachments(PDF_PAGE), ["https://merolagani.com/Uploads/Repository/123.pdf"])

    def test_missing_fields_fall_back_safely(self):
        notice = parse_detail("<html><body><p>nothing here</p></body></html>", 1)
        self.assertEqual(notice.symbol, "UNKNOWN")
        self.assertIsNone(notice.date)
        self.assertEqual(notice.attachments, [])


class FilterTests(unittest.TestCase):
    def test_interest_rate_titles(self):
        self.assertTrue(is_interest_rate("Garima Bikas Bank Limited has published new Interest  Rates"))
        self.assertFalse(is_interest_rate("20th AGM Minutes - Excel Development Bank Limited (EDBL)"))
        self.assertTrue(is_interest_rate("Revised base rate", keywords=("base rate",)))

    def test_company_from_title(self):
        self.assertEqual(company_from_title("Garima Bikas Bank Limited has published a notice"),
                         "garima bikas bank limited")
        self.assertEqual(company_from_title("Everest Bank Limited has made correction on its rates"),
                         "everest bank limited")
        self.assertEqual(company_from_title("Nabil Bank Limited published a notice regarding rates"),
                         "nabil bank limited")
        self.assertEqual(company_from_title("No publisher phrase here"), "")

    def test_sector_order_is_development_then_commercial(self):
        self.assertEqual(list(SECTORS), ["development", "commercial"])
        self.assertEqual(SECTORS["development"].id, 3)
        self.assertEqual(SECTORS["commercial"].id, 1)


class StorageTests(unittest.TestCase):
    def test_safe_name_strips_invalid_characters(self):
        self.assertEqual(safe_name('A/B: "C"? <D> | E.'), "A B C D E")
        self.assertEqual(safe_name("   "), "untitled")

    def test_bank_folder_layout(self):
        notice = parse_detail(DETAIL_PAGE, 67425)
        folder = bank_folder(Path("out"), SECTORS["development"], notice)
        self.assertEqual(folder, Path("out") / "Development Banks" / "CORBL - Corporate Development Bank Limited")

    def test_guess_extension(self):
        self.assertEqual(guess_extension("https://x/y/file.GIF", ""), ".gif")
        self.assertEqual(guess_extension("https://x/y/download", "application/pdf"), ".pdf")

    def test_manifest_round_trip(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "manifest.csv"
            Manifest(path).add([{"announcement_id": 5, "company": "Nabil Bank Limited", "file": "a.gif"}])
            self.assertIn(5, Manifest(path))
            with path.open(encoding="utf-8-sig", newline="") as fh:
                self.assertEqual(next(csv.DictReader(fh))["company"], "Nabil Bank Limited")

    def test_drop_older_keeps_only_latest_notice_per_bank(self):
        with tempfile.TemporaryDirectory() as tmp:
            manifest = Manifest(Path(tmp) / "manifest.csv")
            manifest.add([
                {"symbol": "NABIL", "announcement_id": 1, "file": "Commercial Banks/NABIL/old.gif"},
                {"symbol": "NABIL", "announcement_id": 2, "file": "Commercial Banks/NABIL/new.gif"},
                {"symbol": "SCB", "announcement_id": 3, "file": "Commercial Banks/SCB/scb.gif"},
            ])
            self.assertEqual(manifest.drop_older("NABIL", keep_id=2), ["Commercial Banks/NABIL/old.gif"])
            reloaded = Manifest(Path(tmp) / "manifest.csv")
            self.assertNotIn(1, reloaded)
            self.assertIn(2, reloaded)
            self.assertIn(3, reloaded)
            self.assertEqual(manifest.drop_older("NABIL", keep_id=2), [])


if __name__ == "__main__":
    unittest.main()
