"""Offline test: the email is built from the report and carries it as an attachment (nothing is sent)."""

import tempfile
import unittest
from pathlib import Path

from merolagani_notices import history
from merolagani_notices.mailer import build_message, main
from merolagani_notices.report import build_report


def record(month_eff, aid, saving):
    return {"symbol": "ABC", "bank": "ABC Bank Ltd.", "sector": "Commercial Banks", "announcement_id": aid,
            "effective": month_eff, "saving_rates": saving, "call": "Up to 0.25%", "ind_lt1": 2.75,
            "ind_1y": 3.0, "ind_gt1": 4.0, "inst_lt1": 2.75, "inst_1y": 2.75, "inst_gt1": 3.0, "notes": []}


class MailerTests(unittest.TestCase):
    def test_message_has_summary_and_attachment(self):
        with tempfile.TemporaryDirectory() as tmp:
            hist, report = Path(tmp) / "h", Path(tmp) / "Interest_Rate_Summary.xlsx"
            history.save(hist, record("1 Bhadra 2083", 1, [3.00, 3.50]))
            history.save(hist, record("1 Ashwin 2083", 2, [2.75, 3.50]))
            build_report([], report, history_dir=hist)
            msg = build_message(report, "me@example.com", ["boss@example.com"], ["team@example.com"])
            self.assertEqual(msg["Subject"], "Deposit Interest Rate Report: Ashwin 2083 vs Bhadra 2083")
            self.assertEqual((msg["To"], msg["Cc"]), ("boss@example.com", "team@example.com"))
            text = msg.get_body(("plain",)).get_content()
            # saving min 3.00 -> 2.75 and saving max (second highest) 3.00 -> 2.75
            self.assertIn("Rates decreased: 2", text)
            self.assertIn("ABC Bank Ltd.: 0 up, 2 down", text)
            attachments = list(msg.iter_attachments())
            self.assertEqual(attachments[0].get_filename(), "Interest_Rate_Summary.xlsx")

    def test_missing_settings_skips_without_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            report = Path(tmp) / "r.xlsx"
            build_report([record("1 Ashwin 2083", 2, [2.75])], report)
            import os
            saved = {k: os.environ.pop(k, None) for k in ("SMTP_HOST", "SMTP_USERNAME", "SMTP_PASSWORD", "MAIL_TO")}
            try:
                self.assertEqual(main(["--report", str(report)]), 0)
            finally:
                os.environ.update({k: v for k, v in saved.items() if v is not None})


if __name__ == "__main__":
    unittest.main()
