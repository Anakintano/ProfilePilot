"""Deterministic file validation: type, magic bytes, size, page count, dimensions.

Runs before an upload is marked 'validated' and before any analysis can
reference it. No LLM involved — this is pure policy enforcement.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import fitz  # PyMuPDF
from PIL import Image

from .config import settings
from .storage import ALLOWED_MIME_TYPES


@dataclass
class ValidationResult:
    ok: bool
    reason: str | None = None
    page_count: int | None = None


def validate_declared_metadata(mime_type: str, byte_size: int) -> ValidationResult:
    if mime_type not in ALLOWED_MIME_TYPES:
        return ValidationResult(False, f"Unsupported file type: {mime_type}")
    if byte_size <= 0:
        return ValidationResult(False, "Empty file")
    if byte_size > settings.max_upload_bytes:
        mb = settings.max_upload_bytes // (1024 * 1024)
        return ValidationResult(False, f"File exceeds {mb}MB limit")
    return ValidationResult(True)


def _sniff_mime_type(path: Path) -> str | None:
    """Hand-rolled magic-byte sniff for exactly the 4 types this app accepts.
    Deliberately not using the `magic`/libmagic binding: it requires a
    system libmagic install that's absent by default on Windows (hangs/fails
    there) and unnecessary weight for a 4-signature check anyway."""
    with open(path, "rb") as f:
        header = f.read(16)
    if header.startswith(b"%PDF-"):
        return "application/pdf"
    if header.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if header.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if header[:4] == b"RIFF" and header[8:12] == b"WEBP":
        return "image/webp"
    return None


def validate_stored_file(path: Path, declared_mime_type: str) -> ValidationResult:
    """Runs after bytes are on disk: verifies magic bytes match the declared
    type (rejects MIME spoofing), then checks page count / dimensions."""
    detected = _sniff_mime_type(path)
    detected_label = detected or "an unrecognized format"

    if declared_mime_type == "application/pdf":
        if detected != "application/pdf":
            return ValidationResult(False, f"File content is not a PDF (detected {detected_label})")
        try:
            doc = fitz.open(path)
        except Exception as exc:  # noqa: BLE001 - corrupt/malicious PDFs raise arbitrary errors
            return ValidationResult(False, f"Could not open PDF: {exc}")
        try:
            page_count = doc.page_count
            if page_count == 0:
                return ValidationResult(False, "PDF has no pages")
            if page_count > settings.max_pdf_pages:
                return ValidationResult(
                    False, f"PDF exceeds {settings.max_pdf_pages}-page limit ({page_count} pages)"
                )
            for page in doc:
                rect = page.rect
                if rect.width > 20000 or rect.height > 20000:
                    return ValidationResult(False, "PDF page dimensions are implausibly large")
            return ValidationResult(True, page_count=page_count)
        finally:
            doc.close()

    if declared_mime_type in ("image/png", "image/jpeg", "image/webp"):
        if detected not in ("image/png", "image/jpeg", "image/webp"):
            return ValidationResult(False, f"File content is not an image (detected {detected_label})")
        try:
            with Image.open(path) as img:
                img.verify()
            with Image.open(path) as img:
                width, height = img.size
        except Exception as exc:  # noqa: BLE001 - Pillow raises many error types for bad images
            return ValidationResult(False, f"Could not read image: {exc}")
        if width > settings.max_image_dimension_px or height > settings.max_image_dimension_px:
            return ValidationResult(False, f"Image exceeds {settings.max_image_dimension_px}px per side")
        if width * height > 40_000_000:
            return ValidationResult(False, "Image pixel count too large (decompression-bomb guard)")
        return ValidationResult(True, page_count=1)

    return ValidationResult(False, f"Unsupported file type: {declared_mime_type}")
