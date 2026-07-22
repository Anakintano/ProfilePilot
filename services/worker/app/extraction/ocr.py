"""PaddleOCR wrapper that degrades gracefully. paddlepaddle/paddleocr are
heavy and may fail to install, fail to download models on first use, or
simply be slow/flaky at runtime — none of that should ever crash a job.
`ocr_image` returns None on any failure; callers must skip that page's OCR
content rather than inserting fabricated text.
"""
from __future__ import annotations

import concurrent.futures
import logging

import numpy as np
from PIL import Image

from .reading_order import order_lines_by_reading_order

logger = logging.getLogger("profilepilot.worker.ocr")

OCR_TIMEOUT_SECONDS = 60

_ocr_engine = None


def _get_engine():
    global _ocr_engine
    if _ocr_engine is not None:
        return _ocr_engine
    from paddleocr import PaddleOCR  # imported lazily: heavy, optional-at-runtime

    _ocr_engine = PaddleOCR(use_angle_cls=True, lang="en", show_log=False)
    return _ocr_engine


def _run_ocr_sync(image: Image.Image) -> list[dict]:
    engine = _get_engine()
    arr = np.array(image.convert("RGB"))
    raw_result = engine.ocr(arr, cls=True)

    lines: list[dict] = []
    for page_result in raw_result or []:
        for box, (text, confidence) in page_result or []:
            text = text.strip()
            if not text:
                continue
            xs = [pt[0] for pt in box]
            ys = [pt[1] for pt in box]
            x0, y0, x1, y1 = min(xs), min(ys), max(xs), max(ys)
            lines.append(
                {
                    "text": text,
                    "bbox": {"x": x0, "y": y0, "width": x1 - x0, "height": y1 - y0},
                    "confidence": float(confidence),
                }
            )
    return order_lines_by_reading_order(lines, page_width=float(arr.shape[1]))


def ocr_image(image: Image.Image) -> list[dict] | None:
    """Runs OCR on a preprocessed image. Returns a list of
    {text, bbox, confidence} dicts in reading order, or None if OCR is
    unavailable for any reason (not installed, model download failed,
    timed out, crashed) — never fabricates text on failure."""
    executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
    try:
        future = executor.submit(_run_ocr_sync, image)
        return future.result(timeout=OCR_TIMEOUT_SECONDS)
    except concurrent.futures.TimeoutError:
        logger.warning("OCR timed out after %ss", OCR_TIMEOUT_SECONDS)
        return None
    except Exception:
        logger.exception("OCR unavailable")
        return None
    finally:
        # Don't block on shutdown: a timed-out/stuck worker thread must not
        # hang the caller. It's daemonized away rather than joined.
        executor.shutdown(wait=False)
