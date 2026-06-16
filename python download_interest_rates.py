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
    "Finance",
    "Microfinance",
]


def safe_name(text):
    return "".join(c if c.isalnum() or c in " -_" else "_" for c in text).strip()


def image_extension(image_url):
    suffix = Path(urlparse(image_url).path).suffix.lower().lstrip(".")
    return suffix if suffix in {"png", "jpg", "jpeg", "webp"} else "png"


with sync_playwright() as p:
    browser = p.chromium.launch(headless=False)
    page = browser.new_page()

    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0"
    })

    for sector in SECTORS:
        print(f"Processing sector: {sector}")

        page.goto(LIST_URL, wait_until="domcontentloaded")

        # Select Sector
        page.locator("select").nth(0).select_option(label=sector)

        # Select Announcement Type
        page.locator("select").nth(2).select_option(label="Interest Rate")

        # Click correct Search button
        page.locator("#ctl00_ContentPlaceHolder1_lbtnSearch").click()
        page.wait_for_timeout(2000)

        # Get latest detail link only
        links = page.locator("a").evaluate_all("""
            els => els
                .map(a => a.href)
                .filter(h => h && h.includes("AnnouncementDetail"))
        """)

        links = list(dict.fromkeys(links))

        if not links:
            print(f"No detail page found for {sector}")
            continue

        latest_link = links[0]
        print("Latest detail page:", latest_link)

        page.goto(latest_link, wait_until="domcontentloaded")
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
            print(f"No image found for {sector}")
            continue

        # Download latest image only
        img_url = image_urls[0]
        ext = image_extension(img_url)

        filename = SAVE_DIR / f"{safe_name(sector)}_latest.{ext}"

        response = session.get(img_url, timeout=30)
        response.raise_for_status()

        filename.write_bytes(response.content)
        print("Saved:", filename)

    browser.close()
