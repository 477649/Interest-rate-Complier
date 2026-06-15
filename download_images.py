from pathlib import Path
from urllib.parse import urljoin
import re
import time
import requests
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

LIST_URL = "https://merolagani.com/AnnouncementList.aspx"
SAVE_DIR = Path("interest_rate_images")
SAVE_DIR.mkdir(exist_ok=True)

SECTORS = [
    "Commercial Banks",
    "Development Bank Limited",
    "Finance",
    "Microfinance",
]

ANNOUNCEMENT_TYPE = "Interest Rate"


def safe_name(text, max_len=80):
    text = re.sub(r"\s+", " ", text or "").strip()
    text = "".join(c if c.isalnum() or c in " -_" else "_" for c in text)
    return text[:max_len].strip("_ ") or "unknown"


def goto_page(page, url):
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=120000)
    except PlaywrightTimeoutError:
        print(f"Timeout opening page, continuing anyway: {url}")

    page.wait_for_timeout(3000)


def download_image(img_url, filename):
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131.0 Safari/537.36",
        "Referer": LIST_URL,
    }

    response = requests.get(img_url, headers=headers, timeout=60)
    response.raise_for_status()

    filename.write_bytes(response.content)
    print("Saved:", filename)


with sync_playwright() as p:
    browser = p.chromium.launch(
        headless=True,
        args=[
            "--disable-blink-features=AutomationControlled",
            "--no-sandbox",
            "--disable-dev-shm-usage",
        ],
    )

    context = browser.new_context(
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131.0 Safari/537.36",
        viewport={"width": 1366, "height": 768},
    )

    page = context.new_page()

    for sector in SECTORS:
        print("=" * 60)
        print("Processing sector:", sector)

        goto_page(page, LIST_URL)

        try:
            selects = page.locator("select")
            print("Dropdown count:", selects.count())

            selects.nth(0).select_option(label=sector)
            page.wait_for_timeout(1000)

            selects.nth(2).select_option(label=ANNOUNCEMENT_TYPE)
            page.wait_for_timeout(1000)

            page.get_by_text("Search", exact=True).click()
            page.wait_for_timeout(7000)

        except Exception as e:
            print("Filter/search failed:", e)
            continue

        links = page.locator("a").evaluate_all("""
            els => els
                .map(a => a.href)
                .filter(h => h && h.includes("AnnouncementDetail"))
        """)

        links = list(dict.fromkeys(links))
        print("Found detail links:", len(links))

        for index, link in enumerate(links, start=1):
            print("Opening detail:", link)
            goto_page(page, link)

            try:
                heading_text = page.locator("body").inner_text(timeout=10000)
            except Exception:
                heading_text = f"{sector}_{index}"

            page_title = safe_name(heading_text[:100])

            image_urls = page.locator("img").evaluate_all("""
                imgs => imgs
                    .map(img => img.getAttribute("src"))
                    .filter(src => src)
            """)

            image_urls = [
                urljoin(link, src)
                for src in image_urls
                if any(word in src.lower() for word in [
                    "announcement",
                    "uploads",
                    "interest",
                    ".png",
                    ".jpg",
                    ".jpeg"
                ])
            ]

            image_urls = list(dict.fromkeys(image_urls))
            print("Found images:", len(image_urls))

            for img_no, img_url in enumerate(image_urls, start=1):
                ext = img_url.split("?")[0].split(".")[-1].lower()
                if ext not in ["png", "jpg", "jpeg", "webp"]:
                    ext = "png"

                filename = SAVE_DIR / f"{safe_name(sector)}_{index}_{img_no}_{page_title}.{ext}"

                try:
                    download_image(img_url, filename)
                    time.sleep(1)
                except Exception as e:
                    print("Image download failed:", img_url, e)

    browser.close()

print("Done.")
