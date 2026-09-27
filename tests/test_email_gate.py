"""The 90% rule: email only when most report banks have published for the new month, and only once."""

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from merolagani_notices import history, mailer
from merolagani_notices.report import build_report


def rec(symbol, month, sector="Commercial Banks"):
    return {"symbol": symbol, "bank": f"{symbol} Bank", "sector": sector, "announcement_id": 1, "month": month,
            "saving_rates": [2.75], "call": "Up to 0.25%", "ind_lt1": 2.75, "ind_1y": 3.0, "ind_gt1": 4.0,
            "inst_lt1": 2.75, "inst_1y": 2.75, "inst_gt1": 3.0, "notes": []}


ENV = {"SMTP_HOST": "smtp.test", "SMTP_USERNAME": "me@test", "SMTP_PASSWORD": "x", "MAIL_TO": "boss@test"}


class EmailGateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.hist, self.report, self.state = root / "h", root / "r.xlsx", root / "state.json"
        for i in range(10):                       # 10 commercial banks, all in Ashwin
            history.save(self.hist, rec(f"B{i}", "2083-06"))
        history.save(self.hist, rec("DEVX", "2083-06", "Development Banks"))  # not a report bank
        build_report([], self.report, history_dir=self.hist)

    def tearDown(self):
        self.tmp.cleanup()

    def run_mailer(self, *extra):
        with mock.patch.dict(os.environ, ENV), mock.patch.object(mailer, "send") as sent:
            code = mailer.main(["--report", str(self.report), "--history", str(self.hist),
                                "--state", str(self.state), *extra])
        return code, sent.call_count

    def test_development_banks_outside_the_list_are_not_counted(self):
        cov = mailer.coverage(self.hist)
        self.assertEqual((cov["found"], cov["total"]), (10, 10))

    def test_only_one_bank_published_new_month_no_email(self):
        history.save(self.hist, rec("B0", "2083-07"))        # 1 of 10 has Kartik
        self.assertEqual(self.run_mailer(), (0, 0))

    def test_ninety_percent_sends_once(self):
        for i in range(9):                                     # 9 of 10 = 90%
            history.save(self.hist, rec(f"B{i}", "2083-07"))
        self.assertEqual(self.run_mailer(), (0, 1))
        self.assertEqual(json.loads(self.state.read_text())["last_emailed_month"], "2083-07")
        self.assertEqual(self.run_mailer(), (0, 0))           # next day: already sent

    def test_below_ninety_percent_waits(self):
        for i in range(8):                                     # 80%
            history.save(self.hist, rec(f"B{i}", "2083-07"))
        self.assertEqual(self.run_mailer(), (0, 0))

    def test_force_sends_anyway(self):
        history.save(self.hist, rec("B0", "2083-07"))
        self.assertEqual(self.run_mailer("--force"), (0, 1))


if __name__ == "__main__":
    unittest.main()
