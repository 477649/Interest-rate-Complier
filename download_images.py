from pathlib import Path
import requests
from playwright.sync_api import sync_playwright

LIST_URL = "https://merolagani.com/AnnouncementList.aspx"
SAVE_DIR = Path("interest_rate_images")
SAVE_DIR.mkdir(exist_ok=True)

SECTORS = [
    "Commercial Banks",
    "Development Bank Limited",
    "Finance",
    "Microfinance",
]

def safe_name(text):
    return "".join(c if c.isalnum() or c in " -_" else "_" for c in text).strip()

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()
    page.goto(LIST_URL, wait_until="networkidle", timeout=60000)

    for sector in SECTORS:
        print(f"Processing sector: {sector}")

        page.goto(LIST_URL, wait_until="networkidle", timeout=60000)

        page.locator("select").nth(0).select_option(label=sector)
        page.locator("select").nth(2).select_option(label="Interest Rate")

        page.get_by_text("Search").click()
        page.wait_for_timeout(5000)

        links = page.locator("a").evaluate_all("""
            els => els
                .map(a => a.href)
                .filter(h => h && h.includes("AnnouncementDetail"))
        """)

        links = list(dict.fromkeys(links))
        print("Found detail pages:", len(links))

        for index, link in enumerate(links, start=1):
            print("Opening:", link)
            page.goto(link, wait_until="networkidle", timeout=60000)
            page.wait_for_timeout(3000)

            image_urls = page.locator("img").evaluate_all("""
                imgs => imgs
                    .map(img => img.src)
                    .filter(src => src && (
                        src.toLowerCase().includes("announcement") ||
                        src.toLowerCase().includes("uploads") ||
                        src.toLowerCase().includes("interest")
                    ))
            """)

            image_urls = list(dict.fromkeys(image_urls))

            for img_no, img_url in enumerate(image_urls, start=1):
                ext = img_url.split("?")[0].split(".")[-1].lower()
                if ext not in ["png", "jpg", "jpeg", "webp"]:
                    ext = "png"

                filename = SAVE_DIR / f"{safe_name(sector)}_{index}_{img_no}.{ext}"

                response = requests.get(img_url, timeout=30)
                response.raise_for_status()

                filename.write_bytes(response.content)
                print("Saved:", filename)

    browser.close()
