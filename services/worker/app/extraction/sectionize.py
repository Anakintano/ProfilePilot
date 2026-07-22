"""Heuristic section classification for résumé text. Walks blocks/lines
already in reading order (top-to-bottom, left-to-right per page, pages in
document order) and assigns each one a section.
"""
from __future__ import annotations

import re

EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.\w+")
PHONE_RE = re.compile(r"(\+?\d[\d\-.\s()]{7,}\d)")

HEADER_KEYWORDS: dict[str, tuple[str, ...]] = {
    "experience": ("experience", "work experience", "employment", "employment history", "work history", "professional experience"),
    "education": ("education", "academic background"),
    # "top skills" is LinkedIn's actual PDF-export wording -- not a generic
    # synonym, the literal standard heading -- so this isn't optional polish,
    # it's the difference between working and not working on LinkedIn exports.
    "skills": ("skills", "top skills", "technical skills", "core skills", "skills and tools", "skills & tools", "skills & endorsements", "areas of expertise"),
    "summary": ("summary", "objective", "about", "about me", "profile"),
    "projects": ("projects", "personal projects", "academic projects"),
    "certifications": ("certifications", "certificates", "licenses", "licenses and certifications", "licenses & certifications", "honors-awards", "honors & awards", "honors and awards", "awards"),
}

MAX_HEADER_WORDS = 5
MAX_HEADER_CHARS = 40
CONTACT_ZONE_MAX_BLOCK_INDEX = 8  # first ~8 blocks of page 1 count as "near the top"


def _looks_like_header(text: str) -> str | None:
    stripped = text.strip().strip(":").strip()
    if not stripped or len(stripped) > MAX_HEADER_CHARS or len(stripped.split()) > MAX_HEADER_WORDS:
        return None
    lowered = stripped.lower()
    for section, keywords in HEADER_KEYWORDS.items():
        for kw in keywords:
            if lowered == kw or lowered.startswith(kw):
                return section
    return None


def _looks_like_contact(text: str) -> bool:
    return bool(EMAIL_RE.search(text)) or bool(PHONE_RE.search(text))


def sectionize(blocks: list[dict]) -> list[dict]:
    """Returns a new list of blocks, each with a `section` key (and an
    `is_header` flag marking the header line itself) added."""
    current_section: str | None = None
    prev_page: int | None = None
    prev_column: int | None = None
    result: list[dict] = []
    for idx, block in enumerate(blocks):
        # A column-0-to-column-1 jump *within the same page* means we've
        # just finished reading an entire sidebar and are starting an
        # entirely different column (reading_order.py tags columns this
        # way). That specific transition must not let the sidebar's last
        # section leak into the main column just because no new header
        # happened to appear yet there. An ordinary page boundary is NOT
        # this -- multi-page sections (e.g. Experience continuing onto a
        # single-column page 2) must keep their section, so only this exact
        # same-page 0->1 transition resets, nothing else.
        page = block.get("page_number")
        column = block.get("column", 0)
        if page == prev_page and prev_column == 0 and column == 1:
            current_section = None
        prev_page, prev_column = page, column

        text = block["text"]
        header_section = _looks_like_header(text)
        if header_section is not None:
            current_section = header_section
            result.append({**block, "section": header_section, "is_header": True})
            continue
        if block.get("page_number") == 1 and idx < CONTACT_ZONE_MAX_BLOCK_INDEX and _looks_like_contact(text):
            result.append({**block, "section": "contact", "is_header": False})
            continue
        result.append({**block, "section": current_section or "other", "is_header": False})
    return result


# ---------------------------------------------------------------------------
# Entry grouping: a section like "experience" or "education" is a list of
# distinct entries (one per job/degree/cert), each spanning several lines
# (title, dates, bullets) -- not one flat field per line.
# ---------------------------------------------------------------------------

ENTRY_GROUPED_SECTIONS = {"experience", "education", "projects", "certifications"}
_BULLET_PREFIXES = ("•", "-", "*", "‣", "▪", "◦")
_NUMBERED_BULLET_RE = re.compile(r"^\d+[.)]\s")

_MONTH = (
    r"jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|"
    r"aug(?:ust)?|sep(?:tember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?"
)
# "June 2025 - Present (2 months)" / "Sep 2025 - Mar 2026" -- résumé/LinkedIn
# date ranges reliably mark a job/degree entry's header block, which is a far
# more robust anchor than guessing entry boundaries from whitespace alone
# (PDF exports vary widely in whether they even use bold for titles -- many
# don't, so font weight can't be relied on as a general-purpose signal).
_DATE_RANGE_RE = re.compile(
    rf"(?:{_MONTH})\.?\s*\d{{4}}\s*-\s*(?:present|(?:{_MONTH})\.?\s*\d{{4}})",
    re.IGNORECASE,
)


def _starts_with_bullet(text: str) -> bool:
    stripped = text.strip()
    if not stripped:
        return False
    return stripped[0] in _BULLET_PREFIXES or bool(_NUMBERED_BULLET_RE.match(stripped))


def _looks_like_date_range(text: str) -> bool:
    # Regex whitespace already matches U+00A0 (non-breaking space), which
    # PDF exports commonly use around date-range dashes.
    return bool(_DATE_RANGE_RE.search(text))


def group_into_entries(blocks: list[dict]) -> list[list[dict]]:
    """Groups one section's reading-order-corrected blocks into entries
    (one per job/degree/cert item, not one per line). Best-effort, not a
    parser -- occasional mis-splits are expected and correctable on the
    extraction-review screen.

    Signals, in order of how much they're trusted:
    1. A header line is always its own singleton entry, and always forces
       the next line to start a fresh entry.
    2. If ANY line in this run looks like a date range, dates anchor entry
       boundaries: walk back up to 2 lines (title, organization) from each
       date-range line to find where that entry actually starts. This is
       the common case (experience/education) and is deliberately the only
       signal used when dates are present -- once we trust the date anchors,
       we do NOT also split on vertical gaps, because genuine within-entry
       whitespace (e.g. before a description paragraph that follows the
       title block) looks identical to inter-entry whitespace and would
       cause false splits.
    2b. If NO line in the run looks like a date range (e.g. a flat
        certifications list with no dates), fall back to vertical-gap
        detection between same-page line pairs (a gap spanning a page break
        is meaningless -- it's comparing unrelated per-page coordinate
        spaces, which previously caused spurious splits at every page
        boundary), plus a bullet-then-non-bullet transition. Only used in
        this no-dates branch -- applying it when dates are present
        over-splits multi-line bullets (a wrapped continuation line doesn't
        start with a bullet marker either, so it would wrongly look like the
        start of a new item)."""
    if not blocks:
        return []

    n = len(blocks)
    entry_start = [False] * n
    entry_start[0] = True

    for i, block in enumerate(blocks):
        if block.get("is_header"):
            entry_start[i] = True
            if i + 1 < n:
                entry_start[i + 1] = True

    has_date_anchors = any(
        not b.get("is_header") and _looks_like_date_range(b["text"]) for b in blocks
    )

    if has_date_anchors:
        for i, block in enumerate(blocks):
            if block.get("is_header") or not _looks_like_date_range(block["text"]):
                continue
            start = i
            j = i - 1
            steps_back = 0
            while (
                j >= 0
                and steps_back < 2
                and not blocks[j].get("is_header")
                and not _starts_with_bullet(blocks[j]["text"])
                and not _looks_like_date_range(blocks[j]["text"])
            ):
                start = j
                steps_back += 1
                j -= 1
            entry_start[start] = True
    else:
        same_page_gaps = []
        for prev, cur in zip(blocks, blocks[1:]):
            if prev.get("page_number") != cur.get("page_number"):
                continue
            prev_bottom = prev["bbox"]["y"] + prev["bbox"]["height"]
            same_page_gaps.append(max(0.0, cur["bbox"]["y"] - prev_bottom))
        median_gap = sorted(same_page_gaps)[len(same_page_gaps) // 2] if same_page_gaps else 0.0
        gap_threshold = max(median_gap * 1.5, 4.0)

        for i in range(1, n):
            prev, cur = blocks[i - 1], blocks[i]
            if entry_start[i] or cur.get("is_header"):
                continue
            if prev.get("page_number") != cur.get("page_number"):
                continue
            if _starts_with_bullet(cur["text"]):
                continue
            prev_bottom = prev["bbox"]["y"] + prev["bbox"]["height"]
            gap = cur["bbox"]["y"] - prev_bottom
            if _starts_with_bullet(prev["text"]) or gap > gap_threshold:
                entry_start[i] = True

    entries: list[list[dict]] = []
    for i, block in enumerate(blocks):
        if entry_start[i]:
            entries.append([block])
        else:
            entries[-1].append(block)
    return entries
