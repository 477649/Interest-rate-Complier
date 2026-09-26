"""Saving notices to disk (one folder per bank) and tracking them in a CSV manifest."""

from __future__ import annotations

import csv
import io
import mimetypes
import re
from pathlib import Path, PurePosixPath
from urllib.parse import urlparse

from .scraper import Notice, Sector

MANIFEST_FIELDS = [
    "sector", "symbol", "company", "announcement_id", "date", "fiscal_year",
    "title", "source_url", "attachment_url", "file",
]

_INVALID_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def safe_name(text: str, max_len: int = 80) -> str:
    """Make text safe to use as a file or folder name on Windows, macOS and Linux."""
    cleaned = _INVALID_CHARS.sub(" ", text)
    cleaned = " ".join(cleaned.split()).strip(" .")
    return cleaned[:max_len].rstrip(" .") or "untitled"


def bank_folder(root: Path, sector: Sector, notice: Notice) -> Path:
    return root / safe_name(sector.name) / safe_name(f"{notice.symbol} - {notice.company}")


def guess_extension(url: str, content_type: str) -> str:
    suffix = PurePosixPath(urlparse(url).path).suffix.lower()
    if suffix in {".gif", ".png", ".jpg", ".jpeg", ".webp", ".pdf", ".bmp", ".tif", ".tiff"}:
        return suffix
    guessed = mimetypes.guess_extension(content_type.split(";")[0].strip()) if content_type else None
    return guessed or ".bin"


def convert_to_png(data: bytes, target: Path) -> bool:
    """Write a PNG copy of an image (first frame for GIFs). Returns False if not an image."""
    try:
        from PIL import Image
    except ImportError:
        return False
    try:
        with Image.open(io.BytesIO(data)) as img:
            img.seek(0)
            img.convert("RGBA" if img.mode in ("RGBA", "LA", "P") else "RGB").save(target, "PNG")
        return True
    except Exception:
        return False


class Manifest:
    """CSV record of every downloaded file; also used to skip notices already saved."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.ids: set[int] = set()
        if path.exists():
            with path.open(newline="", encoding="utf-8-sig") as fh:
                for row in csv.DictReader(fh):
                    try:
                        self.ids.add(int(row["announcement_id"]))
                    except (KeyError, ValueError):
                        continue

    def __contains__(self, announcement_id: int) -> bool:
        return announcement_id in self.ids

    def drop_older(self, symbol: str, keep_id: int) -> list[str]:
        """Remove a bank's rows for every notice except ``keep_id``; return their file paths."""
        if not self.path.exists():
            return []
        with self.path.open(newline="", encoding="utf-8-sig") as fh:
            rows = list(csv.DictReader(fh))
        keep, dropped = [], []
        for row in rows:
            if row.get("symbol") == symbol and row.get("announcement_id") != str(keep_id):
                dropped.append(row)
            else:
                keep.append(row)
        if not dropped:
            return []
        with self.path.open("w", newline="", encoding="utf-8-sig") as fh:
            writer = csv.DictWriter(fh, fieldnames=MANIFEST_FIELDS, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(keep)
        self.ids = {int(r["announcement_id"]) for r in keep if r.get("announcement_id", "").isdigit()}
        return [r["file"] for r in dropped if r.get("file")]

    def add(self, rows: list[dict]) -> None:
        if not rows:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        new_file = not self.path.exists()
        # utf-8-sig so Excel opens Nepali/Unicode text correctly
        with self.path.open("a", newline="", encoding="utf-8-sig" if new_file else "utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=MANIFEST_FIELDS)
            if new_file:
                writer.writeheader()
            writer.writerows(rows)
        self.ids.update(int(r["announcement_id"]) for r in rows)
