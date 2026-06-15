from pathlib import Path
from urllib.parse import urljoin
import re
import requests
from playwright.sync_api import sync_playwright

LIST_URL = "https://merolagani.com/AnnouncementList.aspx"
SAVE_DIR = Path("interest_rate_images")
SAVE_DIR.mkdir(exist_ok=True)

SECTOR = "Development Bank Limited"
ANNOUNCEMENT_TYPE = "Interest Rate"


def safe_name(text):
    text = re.sub(r"\s+", " ", text).strip()
    text = "".join(c if c.isalnum() or c in " -_" else "_" for c in text)
    return text[:80]


def download_file(url, file_path, referer):
    headers = {
        "User-Agent": "Mozilla/5.0",
        "Referer": referer,
    }
    r = requests.get(url, headers=headers, timeout=60)
    r.raise_for_status()
    file_path.write_bytes(r.content)
    print("Saved:", file_path)


with sync_playwright() as p:
    browser = p.chromium.launch(headless=False)
    page = browser.new_page()

    page.goto(LIST_URL, wait_until="domcontentloaded", timeout=120000)
    page.wait_for_timeout(3000)

    page.locator("select").nth(0).select_option(label=SECTOR)
    page.locator("select").nth(2).select_option(label=ANNOUNCEMENT_TYPE)
    page.get_by_text("Search", exact=True).click()
    page.wait_for_timeout(5000)

    rows = page.locator("text=published a notice").locator("xpath=ancestor::*[contains(@class,'row') or self::tr or self::div]")
    count = rows.count()

    print("Rows found:", count)

    bank_items = []

    for i in range(count):
        row = rows.nth(i)
        text = row.inner_text()

        bank_name = text.split(" has published")[0].strip()
        bank_name = safe_name(bank_name)

        links = row.locator("a").evaluate_all("els => els.map(a => a.href).filter(Boolean)")

        for link in links:
            if "AnnouncementDetail" in link:
                bank_items.append((bank_name, link))
                break

    print("Bank detail links found:", len(bank_items))

    for bank_name, detail_url in bank_items:
        print("Processing:", bank_name, detail_url)

        page.goto(detail_url, wait_until="domcontentloaded", timeout=120000)
        page.wait_for_timeout(3000)

        image_urls = page.locator("img").evaluate_all("""
            imgs => imgs.map(img => img.src).filter(Boolean)
        """)

        image_urls = [
            urljoin(detail_url, src)
            for src in image_urls
            if any(x in src.lower() for x in [".png", ".jpg", ".jpeg", "announcement", "uploads"])
        ]

        image_urls = list(dict.fromkeys(image_urls))

        for n, img_url in enumerate(image_urls, start=1):
            ext = img_url.split("?")[0].split(".")[-1].lower()
            if ext not in ["png", "jpg", "jpeg", "webp"]:
                ext = "png"

            file_path = SAVE_DIR / f"{bank_name}_{n}.{ext}"

            try:
                download_file(img_url, file_path, detail_url)
            except Exception as e:
                print("Failed:", img_url, e)

    browser.close()
