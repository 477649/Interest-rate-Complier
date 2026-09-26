"""The 'only download when rates changed' rule, tested against a fake Merolagani site (offline)."""

import argparse
import tempfile
import unittest
from pathlib import Path

from merolagani_notices.cli import run_sector
from merolagani_notices.scraper import SECTORS, says_unchanged
from merolagani_notices.storage import Manifest, SkipLog

PAGE = """<html><body><table>
<tr><th>Symbol</th><td>ABC (ABC Bank Limited)</td></tr>
<tr><th>Fiscal Year</th><td>083-084</td></tr>
<tr><th>Announcement Detail</th><td>{title}</td></tr>
<tr><th>Announcement Date</th><td>2026/{month}/16 AD (2083/05/31 BS)</td></tr>
</table><script>var fileUrl = "https://img/{aid}.gif";</script></body></html>"""


class FakeClient:
    def __init__(self, announcements, images):
        self.announcements = announcements  # newest first: (id, title, month)
        self.images = images                # id -> bytes
        self.downloads = []

    def list_announcements(self, sector_id, fiscal_year="", page=1, page_size=50):
        if page > 1:
            return []
        return [{"announcementID": a, "announcementDetail": t, "announcementDateAD": f"2026-{m}-16T00:00:00"}
                for a, t, m in self.announcements]

    def announcement_page(self, aid):
        title, month = next((t, m) for a, t, m in self.announcements if a == aid)
        return PAGE.format(title=title, month=month, aid=aid)

    def download(self, url):
        aid = int(url.rsplit("/", 1)[1].split(".")[0])
        self.downloads.append(aid)
        return self.images[aid], "image/gif"


def args(out):
    return argparse.Namespace(since=None, keywords=None, all_notices=False, keep_old=False, force_update=False,
                              dry_run=False, output=out, png=False, max_pages=5)


NEW = "ABC Bank Limited has published a notice regarding new interest rate effective from {}"


class UnchangedRuleTests(unittest.TestCase):
    def run_once(self, out, client):
        manifest = Manifest(out / "manifest.csv")
        skips = SkipLog(out / "unchanged.csv")
        return run_sector(client, SECTORS["commercial"], args(out), "", manifest, skips), manifest

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.out = Path(self.tmp.name)
        first = FakeClient([(1, NEW.format("Bhadra"), "08")], {1: b"rates-v1"})
        stats, _ = self.run_once(self.out, first)
        self.assertEqual(stats["downloaded"], 1)

    def tearDown(self):
        self.tmp.cleanup()

    def current_files(self):
        return sorted(p.name for p in self.out.rglob("*.gif"))

    def test_identical_notice_is_not_saved(self):
        client = FakeClient([(2, NEW.format("Ashwin"), "09"), (1, NEW.format("Bhadra"), "08")],
                            {1: b"rates-v1", 2: b"rates-v1"})
        stats, _ = self.run_once(self.out, client)
        self.assertEqual((stats["downloaded"], stats["unchanged"]), (0, 1))
        self.assertEqual(self.current_files(), ["2026-08-16_ABC_1.gif"])
        # recorded, so the next run neither fetches nor compares it again
        client.downloads.clear()
        stats, _ = self.run_once(self.out, client)
        self.assertEqual((stats["unchanged"], client.downloads), (1, []))

    def test_unchanged_title_skips_without_downloading(self):
        title = "ABC Bank Limited has published a notice regarding interest rate which will remain unchanged"
        client = FakeClient([(2, title, "09"), (1, NEW.format("Bhadra"), "08")], {1: b"rates-v1", 2: b"x"})
        stats, _ = self.run_once(self.out, client)
        self.assertEqual((stats["unchanged"], client.downloads), (1, []))
        self.assertEqual(self.current_files(), ["2026-08-16_ABC_1.gif"])

    def test_changed_notice_replaces_current(self):
        client = FakeClient([(2, NEW.format("Ashwin"), "09"), (1, NEW.format("Bhadra"), "08")],
                            {1: b"rates-v1", 2: b"rates-v2"})
        stats, manifest = self.run_once(self.out, client)
        self.assertEqual((stats["downloaded"], stats["removed"]), (1, 1))
        self.assertEqual(self.current_files(), ["2026-09-16_ABC_2.gif"])
        self.assertEqual(client.downloads, [2])  # fetched once, reused for saving
        self.assertIn(2, manifest)


class TitleTests(unittest.TestCase):
    def test_says_unchanged(self):
        self.assertTrue(says_unchanged("... interest rate which will remain unchanged for the month of Ashad"))
        self.assertTrue(says_unchanged("... interest rates shall remain the same as previous month"))
        self.assertFalse(says_unchanged("... new interest rate effective from Ashwin 01, 2083"))


if __name__ == "__main__":
    unittest.main()
