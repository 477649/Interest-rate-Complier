# Merolagani Interest Rate Notices

Download the **interest-rate notices** that Nepali banks publish on
[merolagani.com](https://merolagani.com/AnnouncementList.aspx), organised **bank-wise**.

It does the same thing as filtering the Announcements page by
**Sector → Development Bank / Commercial Banks** and **Announcement Type → Interest Rate**,
opening each notice and saving its image, but for every bank in one run.

- Processes **Development Banks first, then Commercial Banks**
- Saves the **original notice file** (image or PDF) at full quality, with an optional PNG copy
- One folder per bank, named by symbol and bank name
- Writes a `manifest.csv` listing every file (opens in Excel)
- **Resumable**: already-downloaded notices are skipped on the next run
- Polite by default: waits 1 second between requests and retries on errors

## Output

```
notices/
├── manifest.csv
├── Development Banks/
│   ├── JBBL - Jyoti Bikas Bank Limited/
│   │   └── 2026-09-16_JBBL_67422.gif
│   ├── KSBBL - Kamana Sewa Bikas Bank Limited/
│   │   └── 2026-09-16_KSBBL_67421.gif
│   └── ...
└── Commercial Banks/
    ├── NABIL - Nabil Bank Limited/
    ├── SCB - Standard Chartered Bank Limited/
    │   └── 2026-09-22_SCB_67526.gif
    └── ...
```

Files are named `<date>_<symbol>_<announcement id>.<ext>`. The announcement ID links back to
`https://merolagani.com/AnnouncementDetail.aspx?id=<id>`.

## Setup

Requires Python 3.9 or newer.

```bash
git clone https://github.com/<your-username>/merolagani-interest-rate-notices.git
cd merolagani-interest-rate-notices
python -m venv .venv
# Windows:  .venv\Scripts\activate
# macOS/Linux:  source .venv/bin/activate
pip install -r requirements.txt
```

## Usage

```bash
# Current fiscal year, development banks then commercial banks
python -m merolagani_notices

# Only the latest notice of each bank, plus PNG copies
python -m merolagani_notices --latest-only --png

# A specific Nepali fiscal year
python -m merolagani_notices --fiscal-year 082-083

# Everything published since a date
python -m merolagani_notices --all-years --since 2025-07-17

# Full history (thousands of files, takes a while)
python -m merolagani_notices --all-years

# Only commercial banks
python -m merolagani_notices --sectors commercial

# Preview what would be downloaded, without saving anything
python -m merolagani_notices --latest-only --dry-run
```

### Options

| Option | Description |
|---|---|
| `--sectors development commercial` | Sectors to process, in order (default: both, development first) |
| `--fiscal-year 083-084` | Nepali fiscal year (default: the latest one listed on the site) |
| `--all-years` | Ignore fiscal year and go through the full history |
| `--since YYYY-MM-DD` | Only notices published on or after this date |
| `--latest-only` | Keep just the most recent notice per bank |
| `--keyword TEXT` | Title text to match (repeatable; default `interest rate`) |
| `-o, --output DIR` | Output folder (default `./notices`) |
| `--png` | Also save a PNG copy of each image notice |
| `--delay SECONDS` | Wait between requests (default `1.0`) |
| `--max-pages N` | Safety cap on listing pages per sector (default `200`, 50 items each) |
| `--dry-run` | List matching notices without downloading |
| `-v, --verbose` | Debug output |

Stop at any time with `Ctrl+C`. Running the same command again continues where it left off.

## How it works

1. **Listing:** the Announcements page loads results from a JSON endpoint
   (`/handlers/webrequesthandler.ashx?type=get_announcements`) that accepts a sector, a fiscal
   year and a page number. The tool reads every page for a sector, newest first.
2. **Filtering:** that endpoint ignores the *Announcement Type* filter, so notices are matched by
   their title containing "interest rate". Checked against the site's own *Interest Rate* filter,
   this matched the same notices and found no unrelated ones (debentures, dividends, AGMs, etc.).
3. **Details:** each notice page gives the bank symbol and name, the date and fiscal year, and
   the attachment URL. Images come from a `fileUrl` script variable and PDFs from a hidden
   `pdfviewer` field.
4. **Saving:** attachments are downloaded into `<sector>/<SYMBOL - Bank Name>/`, and each file is
   recorded in `manifest.csv`.

## Project structure

```
merolagani_notices/
├── __main__.py   # enables `python -m merolagani_notices`
├── cli.py        # command-line options and the main download loop
├── client.py     # HTTP session: rate limiting, retries, site endpoints
├── scraper.py    # sectors, listing pagination, title filter, detail-page parsing
└── storage.py    # folder/file naming, PNG conversion, CSV manifest
tests/
└── test_parsing.py   # offline unit tests (no network)
```

## Tests

```bash
python -m unittest discover -s tests -v
```

## Notes

- Notice images carry Merolagani's watermark; the tool saves them exactly as published.
- If the website changes its layout or endpoints, parsing may need updating. The tests in
  `tests/` show the page structure the parser expects.
- For personal research and analysis. Please keep the default delay so the site isn't overloaded,
  and respect merolagani.com's terms of use.
