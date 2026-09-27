"""Email the Excel report with a short summary.

    python -m merolagani_notices.mailer --report reports/Interest_Rate_Summary.xlsx

SMTP settings come from environment variables (GitHub secrets in the workflow):
    SMTP_HOST, SMTP_PORT (587 = STARTTLS, 465 = SSL), SMTP_USERNAME, SMTP_PASSWORD,
    MAIL_TO (comma-separated), MAIL_CC (optional), MAIL_FROM (optional, defaults to SMTP_USERNAME)
"""

from __future__ import annotations

import argparse
import html
import logging
import os
import smtplib
import ssl
import sys
from email.message import EmailMessage
from pathlib import Path

from openpyxl import load_workbook

log = logging.getLogger("merolagani_notices.mailer")

XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def summarize(report: Path) -> dict:
    """Read the comparison sheet: title, and per-bank counts of increased/decreased rates."""
    ws = load_workbook(report, data_only=True)["Interest Rate Summary"]
    title = ws["A1"].value or "Interest Rate Summary"
    change_cols = [c for c in range(2, ws.max_column + 1)
                   if str(ws.cell(row=4, column=c).value or "").endswith("Changes")]
    banks, sector = [], ""
    for r in range(5, ws.max_row + 1):
        name = ws.cell(row=r, column=1).value
        if not name or str(name).startswith(("Changes =", "Rule")):
            continue
        values = [ws.cell(row=r, column=c).value for c in change_cols]
        if all(v is None for v in values):  # sector divider row
            sector = str(name)
            continue
        up = sum(isinstance(v, (int, float)) and v > 0 for v in values)
        down = sum(isinstance(v, (int, float)) and v < 0 for v in values)
        banks.append({"bank": name, "sector": sector, "up": up, "down": down})
    return {"title": title, "banks": banks,
            "up": sum(b["up"] for b in banks), "down": sum(b["down"] for b in banks)}


def build_message(report: Path, sender: str, to: list[str], cc: list[str]) -> EmailMessage:
    s = summarize(report)
    changed = [b for b in s["banks"] if b["up"] or b["down"]]
    subject = s["title"].replace("Bank Deposit Interest Rates — ", "Deposit Interest Rate Report: ")

    lines = [f"{b['bank']}: {b['up']} up, {b['down']} down" for b in changed]
    text = (f"Dear Sir/Madam,\n\nPlease find attached the {s['title']}.\n\n"
            f"Banks covered: {len(s['banks'])}\nRates increased: {s['up']}\nRates decreased: {s['down']}\n\n"
            + ("Banks with rate changes:\n" + "\n".join(lines) if lines else "No rate changes from the previous month.")
            + "\n\nThis report was generated automatically from bank notices published on merolagani.com.\n")

    rows = "".join(
        f"<tr><td style='padding:4px 10px;border:1px solid #C9D3E0'>{html.escape(str(b['bank']))}</td>"
        f"<td style='padding:4px 10px;border:1px solid #C9D3E0;text-align:center;color:#3F6F12'>{b['up']}</td>"
        f"<td style='padding:4px 10px;border:1px solid #C9D3E0;text-align:center;color:#B42318'>{b['down']}</td></tr>"
        for b in changed)
    table = (f"<table style='border-collapse:collapse;font-size:13px'><tr style='background:#0B4EA2;color:#fff'>"
             f"<th style='padding:6px 10px'>Bank</th><th style='padding:6px 10px'>Rates up</th>"
             f"<th style='padding:6px 10px'>Rates down</th></tr>{rows}</table>") if rows else \
        "<p>No rate changes from the previous month.</p>"
    body_html = f"""<div style="font-family:Calibri,Arial,sans-serif;font-size:14px;color:#1F2937">
<p>Dear Sir/Madam,</p>
<p>Please find attached the <b>{html.escape(s['title'])}</b>.</p>
<p><b>Banks covered:</b> {len(s['banks'])} &nbsp;|&nbsp;
<span style="color:#3F6F12"><b>Rates increased:</b> {s['up']}</span> &nbsp;|&nbsp;
<span style="color:#B42318"><b>Rates decreased:</b> {s['down']}</span></p>
{table}
<p style="color:#6B7280;font-size:12px">Generated automatically from bank notices published on merolagani.com.</p>
</div>"""

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = sender
    msg["To"] = ", ".join(to)
    if cc:
        msg["Cc"] = ", ".join(cc)
    msg.set_content(text)
    msg.add_alternative(body_html, subtype="html")
    msg.add_attachment(report.read_bytes(), maintype=XLSX.split("/")[0], subtype=XLSX.split("/")[1],
                       filename=report.name)
    return msg


def _split(value: str | None) -> list[str]:
    return [a.strip() for a in (value or "").replace(";", ",").split(",") if a.strip()]


def send(msg: EmailMessage, host: str, port: int, username: str, password: str) -> None:
    context = ssl.create_default_context()
    if port == 465:
        with smtplib.SMTP_SSL(host, port, context=context, timeout=60) as smtp:
            smtp.login(username, password)
            smtp.send_message(msg)
    else:
        with smtplib.SMTP(host, port, timeout=60) as smtp:
            smtp.starttls(context=context)
            smtp.login(username, password)
            smtp.send_message(msg)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="merolagani_notices.mailer", description="Email the Excel report.")
    p.add_argument("--report", type=Path, default=Path("reports/Interest_Rate_Summary.xlsx"))
    p.add_argument("--dry-run", action="store_true", help="build the email and print it, without sending")
    args = p.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    env = os.environ
    to, cc = _split(env.get("MAIL_TO")), _split(env.get("MAIL_CC"))
    username = env.get("SMTP_USERNAME", "")
    sender = env.get("MAIL_FROM") or username
    if not args.report.exists():
        log.error("Report not found: %s", args.report)
        return 1
    msg = build_message(args.report, sender or "report@example.com", to or ["(not set)"], cc)
    if args.dry_run:
        log.info("Subject: %s\nTo: %s\n\n%s", msg["Subject"], msg["To"],
                 msg.get_body(("plain",)).get_content())
        return 0

    missing = [k for k in ("SMTP_HOST", "SMTP_USERNAME", "SMTP_PASSWORD", "MAIL_TO") if not env.get(k)]
    if missing:
        log.warning("Email not sent: missing settings %s", ", ".join(missing))
        return 0  # not an error: email is optional
    send(msg, env["SMTP_HOST"], int(env.get("SMTP_PORT") or 587), username, env["SMTP_PASSWORD"])
    log.info("Report emailed to %s%s", ", ".join(to), f" (cc {', '.join(cc)})" if cc else "")
    return 0


if __name__ == "__main__":
    sys.exit(main())
