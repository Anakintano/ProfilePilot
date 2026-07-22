"""Column-aware reading-order reconstruction.

Both the embedded-text path (pdf_text.py) and the OCR path (ocr.py)
previously sorted lines by a naive global (y, x) key. That interleaves a
short sidebar column with a tall main column on a genuine two-column layout
(LinkedIn PDF exports, most résumé templates with a sidebar): the sidebar
reaches its own headers at the same y-band where the main column is still
mid-entry, so a sidebar header like "Certifications" can sort in right
before a main-column bullet, corrupting section classification downstream
(sectionize.py inherits whatever header it last saw).

This is heuristic gap-detection, not a general layout engine — it only
handles the common single left/right column split and falls back to the
original simple sort for anything it isn't confident about (single-column
documents, which are the majority case, are unaffected).
"""
from __future__ import annotations

MIN_GAP_PT = 60.0
MIN_GAP_FRACTION_OF_WIDTH = 0.12
MIN_LINES_PER_COLUMN = 3
MIN_COLUMN_HEIGHT_FRACTION = 0.20


def order_lines_by_reading_order(lines: list[dict], page_width: float) -> list[dict]:
    """Reorders `lines` (each a dict with a `bbox` {x,y,width,height}) into
    reading order, tagging each with a `column` index (0 for single-column
    or the left column, 1 for a detected right column). Downstream,
    sectionize.py resets its "current section" tracking whenever `column`
    changes -- reaching the end of a genuinely different column is not a
    signal that the previous column's last section continues, even though
    nothing in the text itself announces a new section there.

    Detects a single left/right column split via the largest gap between
    distinct left-edge (x0) positions; if the gap is wide enough and both
    sides look like genuine columns (enough lines, enough vertical span),
    sorts each column independently by y and concatenates left-then-right.
    Otherwise falls back to a plain (y, x) sort — the previous behavior, and
    the correct one for single-column documents."""
    if len(lines) < MIN_LINES_PER_COLUMN * 2:
        return _simple_sort(lines, column=0)

    split_x = _find_column_split(lines, page_width)
    if split_x is None:
        return _simple_sort(lines, column=0)

    left = [ln for ln in lines if ln["bbox"]["x"] < split_x]
    right = [ln for ln in lines if ln["bbox"]["x"] >= split_x]

    if not _looks_like_real_columns(left, right, lines):
        return _simple_sort(lines, column=0)

    return _simple_sort(left, column=0) + _simple_sort(right, column=1)


def _simple_sort(lines: list[dict], column: int) -> list[dict]:
    ordered = sorted(lines, key=lambda ln: (ln["bbox"]["y"], ln["bbox"]["x"]))
    return [{**ln, "column": column} for ln in ordered]


def _find_column_split(lines: list[dict], page_width: float) -> float | None:
    """Largest gap between consecutive distinct x0 values, if it's wide
    enough to plausibly be a column boundary rather than ordinary
    within-column indentation variance (bullets, nested lines, etc.)."""
    x0_values = sorted({ln["bbox"]["x"] for ln in lines})
    if len(x0_values) < 2:
        return None

    best_gap = 0.0
    best_split = None
    for a, b in zip(x0_values, x0_values[1:]):
        gap = b - a
        if gap > best_gap:
            best_gap = gap
            best_split = (a + b) / 2

    threshold = max(MIN_GAP_PT, MIN_GAP_FRACTION_OF_WIDTH * page_width)
    if best_gap < threshold:
        return None
    return best_split


def _looks_like_real_columns(left: list[dict], right: list[dict], all_lines: list[dict]) -> bool:
    """Guards against a false-positive split from one stray indented line:
    both sides need enough lines and enough vertical spread to look like
    genuine parallel columns, not noise."""
    if len(left) < MIN_LINES_PER_COLUMN or len(right) < MIN_LINES_PER_COLUMN:
        return False

    all_ys = [ln["bbox"]["y"] for ln in all_lines]
    total_height = max(all_ys) - min(all_ys)
    if total_height <= 0:
        return False

    for group in (left, right):
        ys = [ln["bbox"]["y"] for ln in group]
        span = max(ys) - min(ys) if len(ys) > 1 else 0.0
        if span < MIN_COLUMN_HEIGHT_FRACTION * total_height:
            return False
    return True
