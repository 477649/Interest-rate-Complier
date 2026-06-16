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

    match = re.search(r"(.+?)\s+has published", title, re.IGNORECASE)
    if match:
        return safe_name(match.group(1))

    return title or "Unknown Bank"


def image_extension(image_url):
    suffix = Path(urlparse(image_url).path).suffix.lower().lstrip(".")
    return suffix if suffix in ["png", "jpg", "jpeg", "webp"] else "png"


def parse_published_date(text):
    text = " ".join(text.split())

    for fmt in ["%b %d, %Y", "%B %d, %Y", "%Y-%m-%d", "%Y/%m/%d"]:
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            pass

    return None


with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()
    page.set_default_timeout(60000)
    page.set_default_navigation_timeout(60000)

    session = requests.Session()
    session.headers.update({"User-Agent": "Mozilla/5.0"})

    print("Current month from:", MONTH_START)
    print("Today:", TODAY)

    for sector in SECTORS:
        print(f"\nProcessing sector: {sector}")

        page.goto(LIST_URL, wait_until="domcontentloaded")

        page.locator("select").nth(0).select_option(label=sector)
        page.locator("select").nth(2).select_option(label="Interest Rate")

        page.locator("#ctl00_ContentPlaceHolder1_lbtnSearch").click()
        page.wait_for_timeout(3000)

        announcements = page.locator("a[href*='AnnouncementDetail']").evaluate_all("""
            links => links.map(link => {
                let block = link;

                for (let i = 0; i < 6 && block; i++) {
                    const dateEl = block.querySelector && block.querySelector("small.text-muted, small");

                    if (dateEl && dateEl.innerText.trim()) {
                        return {
                            title: (link.innerText || link.textContent || "").trim(),
                            href: link.href,
                            published_date: dateEl.innerText.trim()
                        };
                    }

                    block = block.parentElement;
                }

                return {
                    title: (link.innerText || link.textContent || "").trim(),
                    href: link.href,
                    published_date: ""
                };
            });
        """)

        print("Announcements found:", len(announcements))

        seen_banks = set()

        for item in announcements:
            published_date = parse_published_date(item["published_date"])

            if not published_date:
                print("Skipped, date not found:", item["title"])
                continue

            if published_date > TODAY:
                print("Skipped future date:", published_date)
                continue

            if published_date < MONTH_START:
                print("Stopped, older than current month:", published_date)
                break

            bank_name = clean_bank_name(item["title"])
            bank_key = bank_name.lower()

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
