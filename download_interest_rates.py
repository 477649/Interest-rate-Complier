from pathlib import Path
from urllib.parse import urlparse

import requests
from playwright.sync_api import sync_playwright


LIST_URL = "https://merolagani.com/AnnouncementList.aspx"
SAVE_DIR = Path("interest_rate_images_latest")
SAVE_DIR.mkdir(exist_ok=True)

SECTORS = [
    "Commercial Banks",
    "Development Bank Limited",
]


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
        "View Detail",
        "View Details",
    ]

    for word in remove_words:
        title = title.replace(word, "")

    title = " ".join(title.split()).strip(" -_")
    return title or "Unknown Bank"


def image_extension(image_url):
    suffix = Path(urlparse(image_url).path).suffix.lower().lstrip(".")
    return suffix if suffix in ["png", "jpg", "jpeg", "webp"] else "png"


with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()
    page.set_default_timeout(60000)
    page.set_default_navigation_timeout(60000)

    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0"
    })

    for sector in SECTORS:
        print(f"\nProcessing sector: {sector}")

        page.goto(LIST_URL, wait_until="domcontentloaded")

        page.locator("select").nth(0).select_option(label=sector)
        page.locator("select").nth(2).select_option(label="Interest Rate")

        page.locator("#ctl00_ContentPlaceHolder1_lbtnSearch").click()
        page.wait_for_timeout(2000)

        announcements = page.locator("a[href*='AnnouncementDetail']").evaluate_all("""
            els => els.map(a => ({
                title: (a.innerText || a.textContent || "").trim(),
                href: a.href
            }))
        """)

        seen_banks = set()

        for item in announcements:
            bank_name = clean_bank_name(item["title"])
            bank_key = bank_name.lower()

            if bank_key in seen_banks:
                continue

            seen_banks.add(bank_key)

            detail_link = item["href"]
            print("Bank:", bank_name)
            print("Detail:", detail_link)

            page.goto(detail_link, wait_until="domcontentloaded")
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

            filename = SAVE_DIR / f"{safe_name(bank_name)}.{ext}"

            response = session.get(img_url, timeout=30)
            response.raise_for_status()

            filename.write_bytes(response.content)
            print("Saved:", filename)

    browser.close()
