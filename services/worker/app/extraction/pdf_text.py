"""PyMuPDF embedded-text extraction with per-line bounding boxes, plus page
rendering for pages that need to fall back to OCR.
"""
from __future__ import annotations

import fitz  # PyMuPDF
from PIL import Image

from .reading_order import order_lines_by_reading_order

MIN_SUBSTANTIVE_CHARS = 20


def page_has_substantive_text(page: fitz.Page) -> bool:
    return len(page.get_text("text").strip()) >= MIN_SUBSTANTIVE_CHARS


_BOLD_FLAG = 1 << 4  # PyMuPDF span flags bit 4


def _line_is_bold(spans: list[dict]) -> bool:
    """A line is "bold" if most of its characters (by count, not span count --
    a one-character bold artifact shouldn't outvote a long run of regular
    text) come from bold spans. Used as an entry-boundary signal in
    sectionize.py: résumé job/degree titles are typically bold, descriptions
    and bullets typically aren't, which is a far more reliable signal than
    guessing from vertical whitespace alone."""
    bold_chars = 0
    total_chars = 0
    for span in spans:
        text = span.get("text", "")
        total_chars += len(text)
        flags = span.get("flags", 0)
        font = span.get("font", "")
        if flags & _BOLD_FLAG or "bold" in font.lower():
            bold_chars += len(text)
    return total_chars > 0 and bold_chars / total_chars > 0.5


def extract_embedded_lines(page: fitz.Page, page_number: int) -> list[dict]:
    """Text lines for one page, in top-to-bottom / left-to-right reading
    order, each with a bounding box. page_number is 1-based."""
    raw = page.get_text("dict")
    lines: list[dict] = []
    for block in raw.get("blocks", []):
        if block.get("type") != 0:  # 0 = text block, 1 = image block
            continue
        for line in block.get("lines", []):
            spans = line.get("spans", [])
            text = "".join(span.get("text", "") for span in spans).strip()
            if not text:
                continue
            x0, y0, x1, y1 = line["bbox"]
            lines.append(
                {
                    "text": text,
                    "page_number": page_number,
                    "bbox": {"x": x0, "y": y0, "width": x1 - x0, "height": y1 - y0},
                    "is_bold": _line_is_bold(spans),
                }
            )
    return order_lines_by_reading_order(lines, page_width=page.rect.width)


def render_page_image(page: fitz.Page, dpi: int = 200) -> Image.Image:
    pix = page.get_pixmap(dpi=dpi, colorspace=fitz.csRGB, alpha=False)
    return Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
