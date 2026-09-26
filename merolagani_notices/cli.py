"""Command-line entry point: python -m merolagani_notices [options]."""

from __future__ import annotations

import argparse
import logging
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path

import requests

from . import __version__
from .client import MeroLaganiClient
from .scraper import (
    DEFAULT_KEYWORDS, SECTORS, Sector, company_from_title, is_interest_rate, iter_announcements, parse_detail,
)
from .storage import Manifest, bank_folder, convert_to_png, guess_extension, safe_name

log = logging.getLogger("merolagani_notices")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="merolagani_notices",
        description="Download bank interest-rate notices from merolagani.com, organised bank-wise.",
    )
    p.add_argument("--sectors", nargs="+", choices=list(SECTORS), default=list(SECTORS),
                   help="sectors to process, in order (default: development commercial)")
    year = p.add_mutually_exclusive_group()
    year.add_argument("--fiscal-year", metavar="YYY-YYY",
                      help="Nepali fiscal year, e.g. 083-084 (default: the latest one on the site)")
    year.add_argument("--all-years", action="store_true", help="download the full history")
    p.add_argument("--since", type=date.fromisoformat, metavar="YYYY-MM-DD",
                   help="only notices published on or after this date")
    p.add_argument("--latest-only", action="store_true",
                   help="keep only the most recent notice for each bank")
    p.add_argument("--keyword", action="append", dest="keywords", metavar="TEXT",
                   help='title keyword to match (repeatable, default: "interest rate")')
    p.add_argument("-o", "--output", type=Path, default=Path("notices"),
                   help="output folder (default: ./notices)")
    p.add_argument("--png", action="store_true", help="also save a PNG copy of every image notice")
    p.add_argument("--delay", type=float, default=1.0,
                   help="seconds to wait between requests (default: 1.0)")
    p.add_argument("--max-pages", type=int, default=200,
                   help="safety cap on listing pages per sector (50 items each)")
    p.add_argument("--dry-run", action="store_true", help="list matching notices without downloading")
    p.add_argument("-v", "--verbose", action="store_true", help="show debug output")
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return p


def save_notice(client: MeroLaganiClient, notice, sector: Sector, root: Path, png: bool) -> list[dict]:
    folder = bank_folder(root, sector, notice)
    folder.mkdir(parents=True, exist_ok=True)
    stamp = notice.date.isoformat() if notice.date else "unknown-date"
    rows = []
    for index, url in enumerate(notice.attachments, start=1):
        data, content_type = client.download(url)
        suffix = f"_{index}" if len(notice.attachments) > 1 else ""
        base = safe_name(f"{stamp}_{notice.symbol}_{notice.id}{suffix}", 120)
        target = folder / f"{base}{guess_extension(url, content_type)}"
        target.write_bytes(data)
        files = [target]
        if png and target.suffix.lower() not in (".png", ".pdf"):
            png_path = target.with_suffix(".png")
            if convert_to_png(data, png_path):
                files.append(png_path)
        for f in files:
            rows.append({
                "sector": sector.name,
                "symbol": notice.symbol,
                "company": notice.company,
                "announcement_id": notice.id,
                "date": stamp,
                "fiscal_year": notice.fiscal_year,
                "title": notice.title,
                "source_url": notice.url,
                "attachment_url": url,
                "file": f.relative_to(root).as_posix(),
            })
    return rows


def run_sector(client, sector: Sector, args, fiscal_year: str, manifest: Manifest | None) -> dict:
    stats = {"matched": 0, "downloaded": 0, "skipped": 0, "no_attachment": 0, "failed": 0}
    banks: dict[str, int] = defaultdict(int)
    seen_banks: set[str] = set()
    keywords = tuple(args.keywords) if args.keywords else DEFAULT_KEYWORDS

    log.info("")
    log.info("=== %s (sector %d) — fiscal year: %s ===", sector.name, sector.id, fiscal_year or "all")

    for ann in iter_announcements(client, sector.id, fiscal_year, args.max_pages):
        if args.since and ann.date < args.since:
            break  # the listing is newest-first, so everything after this is older
        if not is_interest_rate(ann.title, keywords):
            continue
        stats["matched"] += 1

        # titles read "<Bank name> has published a notice ..." — lets --latest-only skip
        # older notices for a bank without opening their pages
        title_key = company_from_title(ann.title)
        if args.latest_only and title_key and title_key in seen_banks:
            continue

        if manifest is not None and ann.id in manifest and not args.latest_only:
            stats["skipped"] += 1
            log.debug("  already saved: %s", ann.id)
            continue

        try:
            notice = parse_detail(client.announcement_page(ann.id), ann.id)
        except requests.RequestException as exc:
            stats["failed"] += 1
            log.warning("  ! could not open announcement %s: %s", ann.id, exc)
            continue
        notice.date = notice.date or ann.date
        notice.title = notice.title or ann.title

        if args.latest_only:
            if notice.symbol in seen_banks:
                continue
            seen_banks.add(notice.symbol)
            if title_key:
                seen_banks.add(title_key)
            if manifest is not None and ann.id in manifest:
                stats["skipped"] += 1
                continue

        label = f"{notice.date}  {notice.symbol:<8} {notice.company}"
        if args.dry_run:
            log.info("  %s  (%d file%s)  %s", label, len(notice.attachments),
                     "" if len(notice.attachments) == 1 else "s", notice.url)
            banks[notice.symbol] += 1
            continue
        if not notice.attachments:
            stats["no_attachment"] += 1
            log.info("  - %s  (no attachment) %s", label, notice.url)
            continue

        try:
            rows = save_notice(client, notice, sector, args.output, args.png)
        except (requests.RequestException, OSError) as exc:
            stats["failed"] += 1
            log.warning("  ! %s  download failed: %s", label, exc)
            continue
        manifest.add(rows)
        stats["downloaded"] += 1
        banks[notice.symbol] += 1
        log.info("  + %s", label)

    log.info("--- %s: %d matching, %d downloaded, %d already saved, %d without attachment, %d failed, %d banks",
             sector.name, stats["matched"], stats["downloaded"], stats["skipped"],
             stats["no_attachment"], stats["failed"], len(banks))
    return stats


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO, format="%(message)s")
    logging.getLogger("urllib3").setLevel(logging.WARNING)

    client = MeroLaganiClient(delay=args.delay)

    fiscal_year = ""
    if args.fiscal_year:
        fiscal_year = args.fiscal_year
    elif not args.all_years:
        try:
            years = client.fiscal_years()
        except requests.RequestException as exc:
            log.error("Could not reach merolagani.com: %s", exc)
            return 1
        fiscal_year = years[0] if years else ""

    manifest = None if args.dry_run else Manifest(args.output / "manifest.csv")
    log.info("Saving to: %s", args.output.resolve() if not args.dry_run else "(dry run)")

    try:
        for key in args.sectors:
            run_sector(client, SECTORS[key], args, fiscal_year, manifest)
    except KeyboardInterrupt:
        log.info("\nStopped. Re-run the same command to continue where you left off.")
        return 130
    except requests.RequestException as exc:
        log.error("Network error: %s", exc)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
