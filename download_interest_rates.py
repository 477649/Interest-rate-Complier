from datetime import datetime, date
from pathlib import Path
from urllib.parse import urlparse
from zoneinfo import ZoneInfo
import re

import requests
from playwright.sync_api import sync_playwright


LIST_URL = "https://merolagani.com/AnnouncementList.aspx"
SAVE_DIR = Path("interest_rate_images_latest_month")
SAVE_DIR.mkdir(exist_ok=True)

SECTORS = [
    "Commercial Banks",
    "Development Bank Limited",
]

NEPAL_TZ = ZoneInfo("Asia/Kathmandu")
TODAY = datetime.now(NEPAL_TZ).date()
MONTH_START = date(TODAY.year, TODAY.month, 1)


def safe_name(text):
    text = text.replace("\n", " ").replace("\r", " ")
    text = "".join(c if c.isalnum() or c in " -_" else "_" for c in text)
    return " ".join(text.split()).strip()


def clean_bank_name(title):
    title = safe_name(title)

    remove_words = [
        "Interest Rate",
        "Interest Rates",
        "Announcement",
        "Published",
        "Published Date",
        "View Detail",
        "View Details",
    ]

    for word in remove_words:
        title = title.replace(word, "")

    return " ".join(title.split()).strip(" -_") or "Unknown Bank"


def image_extension(image_url):
    suffix = Path(urlparse(image_url).path).suffix.lower().lstrip(".")
    return suffix if suffix in ["png", "jpg", "jpeg", "webp"] else "png"


def parse_published_date(text):
    text = " ".join(text.split())

    date_patterns = [
        r"\d{4}-\d{1,2}-\d{1,2}",
        r"\d{4}/\d{1,2}/\d{1,2}",
        r"\d{1,2}-\d{1,2}-\d{4}",
        r"\d{1,2}/\d{1,2}/\d{4}",
        r"[A-Za-z]{3,9}\s+\d{1,2},\s+\d{4}",
        r"\d{1,2}\s+[A-Za-z]{3,9}\s+\d{4}",
    ]

    date_formats = [
        "%Y-%m-%d",
        "%Y/%m/%d",
        "%d-%m-%Y",
        "%d/%m/%Y",
        "%b %d, %Y",
        "%B %d, %Y",
        "%d %b %Y",
        "%d %B %Y",
    ]

    for pattern in date_patterns:
        match = re.search(pattern, text)
        if not match:
            continue

        raw_date = match.group(0)

        for fmt in date_formats:
            try:
                return datetime.strptime(raw_date, fmt).date()
            except ValueError:
                pass

    return None


with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()
    page.set_default_timeout(60000)
    page.set_default_navigation_timeout(60000)

    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0"
    })

    print("Downloading Interest Rate files from:")
    print("Month start:", MONTH_START)
    print("Today:", TODAY)

    for sector in SECTORS:
        print(f"\nProcessing sector: {sector}")

        page.goto(LIST_URL, wait_until="domcontentloaded")

        page.locator("select").nth(0).select_option(label=sector)
        page.locator("select").nth(2).select_option(label="Interest Rate")

        page.locator("#ctl00_ContentPlaceHolder1_lbtnSearch").click()
        page.wait_for_timeout(2000)

        rows = page.locator("tr").evaluate_all("""
            rows => rows.map(row => {
                const link = row.querySelector("a[href*='AnnouncementDetail']");
                return {
                    text: row.innerText || "",
                    title: link ? (link.innerText || link.textContent || "").trim() : "",
                    href: link ? link.href : ""
                };
            }).filter(item => item.href);
        """)

        seen_banks = set()

        for item in rows:
            published_date = parse_published_date(item["text"])

            if not published_date:
                print("Skipped: published date not found")
                continue

            if published_date > TODAY:
                print("Skipped future date:", published_date)
                continue

            if published_date < MONTH_START:
                print("Stopped. Older than current month:", published_date)
                break

            bank_name = clean_bank_name(item["title"])
            bank_key = bank_name.lower()

            # Keeps only latest file per bank for this month
            if bank_key in seen_banks:
                continue

            seen_banks.add(bank_key)

            print("Bank:", bank_name)
            print("Published Date:", published_date)

            page.goto(item["href"], wait_until="domcontentloaded")
            page.wait_for_timeout(1000)

            image_urls = page.locator("img").evaluate_all("""
                imgs => imgs
                    .map(img => img.src)
                    .filter(src => src && (
                        src.toLowerCase().includes("announcement") ||
                        src.toLowerCase().includes("uploads") ||
                        src.toLowerCase().includes("interest")
                    ))
            """)

            if not image_urls:
                print("No image found:", bank_name)
                continue

            img_url = image_urls[0]
            ext = image_extension(img_url)

            filename = SAVE_DIR / f"{safe_name(bank_name)}_{published_date}.{ext}"

            response = session.get(img_url, timeout=30)
            response.raise_for_status()

            filename.write_bytes(response.content)
            print("Saved:", filename)

    browser.close()
