"""Extraction orchestrator: reads an analysis's uploads, pulls text out of
each (embedded text where possible, OCR where not), sectionizes it, and
writes `extracted_fields` rows.

Contract with the caller (services/worker/app/main.py): this function must
NOT commit/rollback the transaction and must NOT touch `jobs` or `analyses`
— it only writes `extracted_fields` and `analysis_events`, and raises a
plain Exception on unrecoverable failure.
"""
from __future__ import annotations

import logging
from itertools import groupby
from uuid import UUID

import fitz  # PyMuPDF
from PIL import Image
from psycopg import Connection
from psycopg.types.json import Jsonb

from ..events import append_event
from .ocr import ocr_image
from .pdf_text import extract_embedded_lines, page_has_substantive_text, render_page_image
from .preprocess import preprocess_for_ocr
from .reclassify import reclassify_missing_sections
from .sectionize import ENTRY_GROUPED_SECTIONS, group_into_entries, sectionize

logger = logging.getLogger("profilepilot.worker.extraction")

REQUIRED_SECTIONS = ["contact", "experience", "education", "skills"]
EMBEDDED_TEXT_CONFIDENCE = 0.97
OCR_RENDER_DPI = 200


def run_extraction(conn: Connection, analysis_id: UUID) -> None:
    uploads = conn.execute(
        """
        SELECT u.* FROM uploads u
        JOIN analysis_uploads au ON au.upload_id = u.id
        WHERE au.analysis_id = %s
        ORDER BY u.created_at
        """,
        (str(analysis_id),),
    ).fetchall()

    if not uploads:
        raise Exception(f"No uploads found for analysis {analysis_id}")

    append_event(conn, analysis_id, "extract", "running", f"Starting extraction of {len(uploads)} file(s)")

    files_failed = 0
    ocr_unavailable_pages = 0
    all_blocks: list[dict] = []

    for upload in uploads:
        try:
            blocks, upload_ocr_unavailable = _extract_upload_blocks(upload["storage_key"], upload["mime_type"])
        except Exception as exc:  # noqa: BLE001 - any single unreadable file must not kill the whole job
            files_failed += 1
            logger.exception("Failed to read upload %s (%s)", upload["id"], upload["storage_key"])
            append_event(
                conn, analysis_id, "extract", "running",
                f"Could not read file '{upload['filename']}': {exc}",
            )
            continue

        ocr_unavailable_pages += upload_ocr_unavailable

        for block in sectionize(blocks):
            text = block["text"].strip()
            if not text:
                continue
            block["text"] = text
            block["upload_id"] = upload["id"]
            all_blocks.append(block)

    if files_failed == len(uploads):
        raise Exception(f"Could not read any of the {len(uploads)} uploaded file(s) for analysis {analysis_id}")

    heuristic_missing = [s for s in REQUIRED_SECTIONS if s not in {b["section"] for b in all_blocks}]
    reclassified_count = 0
    if heuristic_missing:
        try:
            reclassified_count = reclassify_missing_sections(all_blocks, heuristic_missing)
        except Exception:  # noqa: BLE001 - reclassification is a best-effort enrichment, never fatal
            logger.exception("Section reclassification failed; continuing with heuristic sections only")

    section_running_index: dict[str, int] = {}
    inserted_count = 0
    confidence_sum = 0.0
    confidence_count = 0
    sections_present: set[str] = set()

    for group in _build_field_groups(all_blocks):
        section = group[0]["section"]
        idx = section_running_index.get(section, 0)
        section_running_index[section] = idx + 1

        value = "\n".join(b["text"] for b in group)
        page_numbers = [b["page_number"] for b in group if b.get("page_number") is not None]
        confidences = [b["confidence"] for b in group if b.get("confidence") is not None]
        confidence = (sum(confidences) / len(confidences)) if confidences else None

        conn.execute(
            """
            INSERT INTO extracted_fields
                (analysis_id, upload_id, section, field_key, value, source_page, bbox, extraction_method, confidence)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                str(analysis_id),
                str(group[0]["upload_id"]),
                section,
                f"{section}_{idx}",
                value,
                min(page_numbers) if page_numbers else None,
                Jsonb(_union_bbox([b["bbox"] for b in group])),
                group[0]["extraction_method"],
                confidence,
            ),
        )
        inserted_count += 1
        sections_present.add(section)
        if confidence is not None:
            confidence_sum += confidence
            confidence_count += 1

    covered = [s for s in REQUIRED_SECTIONS if s in sections_present]
    missing = [s for s in REQUIRED_SECTIONS if s not in sections_present]
    mean_confidence = (confidence_sum / confidence_count) if confidence_count else None

    summary = f"Extracted {len(covered)}/{len(REQUIRED_SECTIONS)} required sections"
    summary += f" ({', '.join(missing)} missing)" if missing else ""
    summary += f", {inserted_count} fields"
    summary += f", mean confidence {mean_confidence:.2f}" if mean_confidence is not None else ""
    if reclassified_count:
        summary += f"; reclassified {reclassified_count} block(s) into missing sections"
    if ocr_unavailable_pages:
        plural = "s" if ocr_unavailable_pages != 1 else ""
        summary += f"; OCR unavailable for {ocr_unavailable_pages} scanned page{plural} — please review and correct"

    append_event(conn, analysis_id, "extract", "running", summary)


def _build_field_groups(all_blocks: list[dict]) -> list[list[dict]]:
    """Splits the flat, reading-order-corrected block list into the groups
    that become one extracted_fields row each. Sections in
    ENTRY_GROUPED_SECTIONS (experience/education/projects/certifications)
    get grouped into entries (one row per job/degree/cert, not one per
    line); everything else keeps today's one-row-per-line behavior.
    Grouping runs per contiguous (upload_id, section) run so entries never
    merge across a section boundary or across different uploads."""
    groups: list[list[dict]] = []
    for (_upload_id, section), run_iter in groupby(all_blocks, key=lambda b: (b["upload_id"], b["section"])):
        run = list(run_iter)
        if section in ENTRY_GROUPED_SECTIONS:
            groups.extend(group_into_entries(run))
        else:
            groups.extend([b] for b in run)
    return groups


def _union_bbox(bboxes: list[dict]) -> dict:
    x0 = min(b["x"] for b in bboxes)
    y0 = min(b["y"] for b in bboxes)
    x1 = max(b["x"] + b["width"] for b in bboxes)
    y1 = max(b["y"] + b["height"] for b in bboxes)
    return {"x": x0, "y": y0, "width": x1 - x0, "height": y1 - y0}


def _extract_upload_blocks(storage_key: str, mime_type: str) -> tuple[list[dict], int]:
    """Returns (blocks, ocr_unavailable_page_count)."""
    if mime_type == "application/pdf":
        return _extract_pdf_blocks(storage_key)
    if mime_type in ("image/png", "image/jpeg", "image/webp"):
        return _extract_image_blocks(storage_key)
    raise Exception(f"Unsupported mime type: {mime_type}")


def _extract_pdf_blocks(storage_key: str) -> tuple[list[dict], int]:
    doc = fitz.open(storage_key)
    try:
        if doc.page_count == 0:
            raise Exception("PDF has no pages")

        blocks: list[dict] = []
        ocr_unavailable_pages = 0
        for page_index in range(doc.page_count):
            page = doc[page_index]
            page_number = page_index + 1

            if page_has_substantive_text(page):
                for line in extract_embedded_lines(page, page_number):
                    blocks.append(
                        {**line, "extraction_method": "embedded_text", "confidence": EMBEDDED_TEXT_CONFIDENCE}
                    )
                continue

            image = render_page_image(page, dpi=OCR_RENDER_DPI)
            ocr_lines = ocr_image(preprocess_for_ocr(image))
            if ocr_lines is None:
                ocr_unavailable_pages += 1
                continue
            for line in ocr_lines:
                blocks.append(
                    {
                        "text": line["text"],
                        "page_number": page_number,
                        "bbox": line["bbox"],
                        "extraction_method": "ocr",
                        "confidence": line["confidence"],
                        "is_bold": False,  # no font info from OCR
                        "column": line.get("column", 0),
                    }
                )
        return blocks, ocr_unavailable_pages
    finally:
        doc.close()


def _extract_image_blocks(storage_key: str) -> tuple[list[dict], int]:
    with Image.open(storage_key) as raw_image:
        raw_image.load()
        image = raw_image.convert("RGB")

    ocr_lines = ocr_image(preprocess_for_ocr(image))
    if ocr_lines is None:
        return [], 1

    blocks = [
        {
            "text": line["text"],
            "page_number": 1,
            "bbox": line["bbox"],
            "extraction_method": "ocr",
            "confidence": line["confidence"],
            "is_bold": False,  # no font info from OCR
            "column": line.get("column", 0),
        }
        for line in ocr_lines
    ]
    return blocks, 0
