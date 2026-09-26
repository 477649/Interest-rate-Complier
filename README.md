# Merolagani Interest Rate Notices

Download the **interest-rate notices** that Nepali banks publish on
[merolagani.com](https://merolagani.com/AnnouncementList.aspx), organised **bank-wise**.

It does the same thing as filtering the Announcements page by
**Sector → Development Bank / Commercial Banks** and **Announcement Type → Interest Rate**,
opening each notice and saving its image, but for every bank in one run.

- Keeps **only the latest notice of each bank** by default, replacing older ones when a new notice
  comes out (`--all` keeps every notice instead)
- Processes **Development Banks first, then Commercial Banks**
- Saves the **original notice file** (image or PDF) at full quality, with an optional PNG copy
- One folder per bank, named by symbol and bank name
- Writes a `manifest.csv` listing every file (opens in Excel)
- Skips notices that are already saved, so re-runs are quick
- Polite by default: waits 1 second between requests and retries on errors

> **📁 The latest notices are in the [`notices/`](notices) folder of this repository**, updated
> automatically every day by GitHub Actions.

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

Requires Python 3.10 or newer.

```bash
git clone https://github.com/477649/Interest-rate-Complier.git
cd Interest-rate-Complier
python -m venv .venv
# Windows:  .venv\Scripts\activate
# macOS/Linux:  source .venv/bin/activate
pip install -r requirements.txt
```

## Usage

```bash
# Latest notice of each bank: development banks, then commercial banks
python -m merolagani_notices

# Same, plus PNG copies
python -m merolagani_notices --png

# Every notice of the current fiscal year (not just the latest)
python -m merolagani_notices --all

# Every notice published since a date
python -m merolagani_notices --all --all-years --since 2025-07-17

# Full history (thousands of files, takes a while)
python -m merolagani_notices --all --all-years

# Only commercial banks
python -m merolagani_notices --sectors commercial

# Preview what would be downloaded, without saving anything
python -m merolagani_notices --dry-run
```

### Options

| Option | Description |
|---|---|
| `--sectors development commercial` | Sectors to process, in order (default: both, development first) |
| `--fiscal-year 083-084` | Nepali fiscal year (default: the latest one listed on the site) |
| `--all-years` | Ignore fiscal year and go through the full history |
| `--since YYYY-MM-DD` | Only notices published on or after this date |
| `--all` | Download every notice in the period, not just each bank's latest |
| `--keep-old` | Don't delete a bank's older notice when a newer one is saved |
| `--keyword TEXT` | Title text to match (repeatable; default `interest rate`) |
| `-o, --output DIR` | Output folder (default `./notices`) |
| `--png` | Also save a PNG copy of each image notice |
| `--delay SECONDS` | Wait between requests (default `1.0`) |
| `--max-pages N` | Safety cap on listing pages per sector (default `200`, 50 items each) |
| `--dry-run` | List matching notices without downloading |
| `-v, --verbose` | Debug output |

Stop at any time with `Ctrl+C`. Running the same command again continues where it left off.

## Automatic downloads (GitHub Actions)

Two workflows live in `.github/workflows/`:

| Workflow | When | What it does |
|---|---|---|
| **Tests** (`tests.yml`) | Every push and pull request | Runs the unit tests on Python 3.10 and 3.13 |
| **Download interest-rate notices** (`download-notices.yml`) | Daily at 09:00 Nepal time, or manually | Updates the **`notices/` folder** with each bank's latest notice |

The workflow commits into the [`notices/`](notices) folder on `main`: the bank-wise folders and
`manifest.csv` described above. When a bank publishes a new notice, its previous file is replaced;
older versions remain available in the git history.

**Run it by hand:** open the **Actions** tab → *Download interest-rate notices* → **Run workflow**,
then choose the sectors, fiscal year, every notice or PNG copies. The run summary lists what changed.

GitHub pauses scheduled workflows in repositories with no activity for 60 days. Re-enable it from
the Actions tab if that happens.

## Interest rates in Excel

📊 **[`reports/Interest_Rate_Summary.xlsx`](reports/Interest_Rate_Summary.xlsx)**: one row per bank with
Saving (Min/Max), Call, Individual FD and Institution FD (Less Than 1 Year Max / 1 Year / More Than 1 Year Max),
plus a *Notes* sheet with effective dates and assumptions.

After each download, the workflow runs `python -m merolagani_notices.extract`:

1. Each **new** notice image is read by an OpenAI vision model, which returns the saving products, call rate
   and general FD tenure rows as structured JSON.
2. The rules are then applied in Python (`merolagani_notices/rules.py`), so they're consistent and tested:
   - **Saving Min** = lowest saving rate; **Saving Max** = second highest, excluding the first highest
   - Call and FCY accounts are not saving rates; remittance and special FD schemes are excluded
   - **FD less than 1 year** = max of tenures starting below 12 months; **1 year** = the tenure containing
     12 months (e.g. "1 year and below 2 years"); **more than 1 year** = max of tenures beyond 12 months
   - Missing values are "Not specified"; unreadable ones are listed in the Notes sheet
   - Amendment notices that change only some rates keep the other rates from the bank's previous notice
3. Results are cached in `notices/extracted/<SYMBOL>.json`, so each notice is sent to the API only once.

**Setup:** add a repository secret named **`OPENAI_API_KEY`** (Settings → Secrets and variables → Actions →
New repository secret). Optionally set a repository *variable* `OPENAI_MODEL` (default `gpt-4.1`).
Without the key, the workflow still runs and rebuilds the Excel file from cached data, listing banks
with newer notices at the bottom of the sheet.

Run locally:

```bash
set OPENAI_API_KEY=sk-...            # macOS/Linux: export OPENAI_API_KEY=sk-...
python -m merolagani_notices.extract
python -m merolagani_notices.extract --report-only   # rebuild Excel without calling the API
```

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
.github/workflows/
├── tests.yml             # CI: unit tests
└── download-notices.yml  # daily / manual update of notices/
notices/                  # latest notice of every bank (maintained by the workflow)
merolagani_notices/
├── __main__.py   # enables `python -m merolagani_notices`
├── cli.py        # command-line options and the main download loop
├── client.py     # HTTP session: rate limiting, retries, site endpoints
├── scraper.py    # sectors, listing pagination, title filter, detail-page parsing
├── storage.py    # folder/file naming, PNG conversion, CSV manifest
├── extract.py    # OpenAI vision extraction + cache (python -m merolagani_notices.extract)
├── rules.py      # Saving Min/Max and FD tenure bucket rules
└── report.py     # Interest Rate Summary Excel workbook
reports/
└── Interest_Rate_Summary.xlsx
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
