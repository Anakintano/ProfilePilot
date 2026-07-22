"""Deterministic rubric scoring engine.

Pure Python: no DB access, no LLM calls, no network -- unit-testable
standalone (see services/worker/tests/smoke_scoring.py). Implements the
evidence_requirements heuristics from db/migrations/0002_seed_rubric_v1.sql
for the five rubric v1 dimensions; keep the two files in sync if the rubric
changes.
"""
from __future__ import annotations

import re
from collections import defaultdict

# ---------------------------------------------------------------------------
# Fallback defaults, used only when a rubric's evidence_requirements omits a
# key (rubric v1 always sets these explicitly; the fallbacks exist so the
# engine degrades gracefully for a future rubric version rather than KeyError).
# ---------------------------------------------------------------------------
DEFAULT_REQUIRED_SECTIONS = ["contact", "experience", "education", "skills"]
DEFAULT_SIGNAL_REGEX = r"\d+%|\$[0-9]|\b\d{2,}\b"
DEFAULT_MIN_QUANTIFIED_BULLETS = 2
DEFAULT_MAX_BULLET_LENGTH = 220
DEFAULT_MIN_EXPERIENCE_ENTRIES = 1

BULLET_SECTIONS = ("experience", "projects", "leadership", "activities")

_STOPWORDS = {
    "a", "an", "the", "and", "or", "for", "to", "of", "in", "on", "with", "is", "are",
    "be", "this", "that", "as", "at", "by", "from", "your", "you", "we", "our", "will",
    "who", "which", "have", "has", "had", "it", "its", "their", "than", "into", "such",
}

# Small built-in fallback used by keyword_alignment when no job_description is
# provided (evidence_requirements: "job_description_or_role_keyword_bank").
# Deliberately modest -- not trying to be an exhaustive taxonomy of tech roles.
ROLE_KEYWORD_BANK: dict[str, list[str]] = {
    "software engineer": ["python", "java", "git", "api", "algorithms", "testing", "sql", "agile", "debugging", "oop"],
    "software engineering": ["python", "java", "git", "api", "algorithms", "testing", "sql", "agile", "debugging", "oop"],
    "backend": ["api", "database", "sql", "microservices", "docker", "rest", "server", "scalability", "python", "java"],
    "frontend": ["javascript", "react", "css", "html", "ui", "responsive", "typescript", "accessibility", "components", "webpack"],
    "full stack": ["javascript", "react", "node", "sql", "api", "css", "html", "backend", "frontend", "git"],
    "data scientist": ["python", "pandas", "machine", "learning", "statistics", "sql", "visualization", "modeling", "numpy", "regression"],
    "data analyst": ["sql", "excel", "tableau", "python", "statistics", "dashboards", "reporting", "visualization", "pandas", "data"],
    "machine learning": ["python", "pytorch", "tensorflow", "machine", "learning", "models", "neural", "data", "training", "algorithms"],
    "product manager": ["roadmap", "stakeholders", "metrics", "user", "research", "prioritization", "agile", "analytics", "strategy", "requirements"],
    "devops": ["docker", "kubernetes", "ci", "cd", "aws", "linux", "automation", "monitoring", "infrastructure", "terraform"],
    "qa": ["testing", "automation", "selenium", "bugs", "regression", "quality", "test", "cases", "manual", "qa"],
}
GENERIC_ROLE_KEYWORDS = ["communication", "teamwork", "leadership", "collaboration", "initiative", "analytical"]


# ---------------------------------------------------------------------------
# Shared helpers (also imported by app/providers/fake_provider.py so the
# recommendation generator reasons about the same section/bullet/keyword
# structure the scorer used -- one source of truth, not two).
# ---------------------------------------------------------------------------

def resolve_value(field: dict) -> str:
    """Prefer a user's correction over the originally extracted value."""
    if field.get("user_corrected") and field.get("corrected_value"):
        return field["corrected_value"]
    return field.get("value") or ""


def group_by_section(extracted_fields: list[dict]) -> dict[str, list[dict]]:
    by_section: dict[str, list[dict]] = defaultdict(list)
    for field in extracted_fields:
        value = resolve_value(field)
        if value.strip():
            by_section[field.get("section", "")].append({**field, "_resolved_value": value})
    return by_section


def collect_bullets(by_section: dict) -> list[tuple[str, str]]:
    """Returns (field_key, bullet_text) pairs from experience-like sections.
    A field's value may itself contain several newline-separated bullets."""
    bullets = []
    for section in BULLET_SECTIONS:
        for field in by_section.get(section, []):
            for line in field["_resolved_value"].splitlines():
                line = line.strip().lstrip("•-*").strip()
                if line:
                    bullets.append((field.get("field_key", ""), line))
    return bullets


def count_experience_entries(by_section: dict) -> int:
    """Best-effort count of distinct experience entries. field_key naming
    isn't a fixed contract from the extraction stage, so this looks for a
    numeric index in field_key (e.g. "experience.0.title") and falls back to
    "1 entry" if the section has content but no such index is found."""
    fields = by_section.get("experience", [])
    if not fields:
        return 0
    indices = set()
    has_non_indexed = False
    for field in fields:
        m = re.search(r"(\d+)", field.get("field_key", "") or "")
        if m:
            indices.add(m.group(1))
        else:
            has_non_indexed = True
    if indices:
        return len(indices)
    return 1 if has_non_indexed else 0


def tokenize(text: str) -> list[str]:
    if not text:
        return []
    cleaned = re.sub(r"[^\w+#./-]", " ", text.lower())
    tokens = []
    for raw in cleaned.split():
        t = raw.strip(".-/")
        if t and t not in _STOPWORDS and len(t) > 1:
            tokens.append(t)
    return tokens


def candidate_token_set(by_section: dict, sections=None) -> tuple[set[str], str]:
    sections = sections if sections is not None else by_section.keys()
    chunks = [f["_resolved_value"] for s in sections for f in by_section.get(s, [])]
    text = " ".join(chunks)
    return set(tokenize(text)), text


def _role_keyword_bank_lookup(role: str) -> list[str]:
    role_l = (role or "").lower()
    for bank_key, keywords in ROLE_KEYWORD_BANK.items():
        if bank_key in role_l:
            return keywords
    return GENERIC_ROLE_KEYWORDS


def find_role_term_gap(by_section: dict, goal_profile: dict) -> tuple[str, list[str], list[str]]:
    """(source_label, all_terms, missing_terms) for relevance_to_role: tokens
    from target_role + job_description that don't appear anywhere in the
    candidate's extracted text."""
    goal_profile = goal_profile or {}
    role = (goal_profile.get("target_role") or "").strip()
    jd = (goal_profile.get("job_description") or "").strip()
    all_terms = sorted(set(tokenize(role)) | set(tokenize(jd)))
    candidate_tokens, _ = candidate_token_set(by_section)
    missing = [t for t in all_terms if t not in candidate_tokens]
    return "your target role and job description", all_terms, missing


def find_keyword_gap(by_section: dict, goal_profile: dict) -> tuple[str, list[str], list[str]]:
    """(source_label, all_keywords, missing_keywords) for keyword_alignment:
    job-description keywords if provided, else the built-in role keyword bank."""
    goal_profile = goal_profile or {}
    jd = (goal_profile.get("job_description") or "").strip()
    role = (goal_profile.get("target_role") or "").strip()
    candidate_tokens, _ = candidate_token_set(by_section)
    if jd:
        all_keywords = sorted(set(tokenize(jd)))
        source = "the job description"
    else:
        all_keywords = _role_keyword_bank_lookup(role)
        source = "common keywords for similar roles"
    missing = [k for k in all_keywords if k not in candidate_tokens]
    return source, all_keywords, missing


def _section_presence(by_section: dict, required_sections: list[str]) -> tuple[list[str], list[str]]:
    present = [s for s in required_sections if by_section.get(s)]
    missing = [s for s in required_sections if s not in present]
    return present, missing


# ---------------------------------------------------------------------------
# Per-dimension scorers. Each returns
# (score_0_100, confidence_0_1, evidence_refs, reasoning_summary, improvement_conditions)
# ---------------------------------------------------------------------------

def _score_impact_quantification(by_section: dict, req: dict):
    min_required = req.get("min_quantified_bullets", DEFAULT_MIN_QUANTIFIED_BULLETS)
    pattern = re.compile(req.get("signal_regex", DEFAULT_SIGNAL_REGEX))
    bullets = collect_bullets(by_section)
    quantified = [(k, t) for k, t in bullets if pattern.search(t)]
    total = len(bullets)
    q = len(quantified)

    if total == 0:
        return (
            0.0, 0.3, [],
            "No experience or project bullets were found to evaluate for quantified impact.",
            ["Add experience or project bullets, then quantify their impact with numbers, %, or $ amounts."],
        )

    score = min(100.0, round(100 * q / min_required, 1)) if min_required > 0 else (100.0 if q else 0.0)
    confidence = 0.9 if total >= 3 else (0.6 if total >= 1 else 0.3)
    evidence_refs = [k or t[:60] for k, t in quantified[:5]]
    reasoning = (
        f"{q} of {total} bullet point(s) include a measurable signal (a %, $, or count); "
        f"the rubric wants at least {min_required}."
    )
    improvement = []
    if q < min_required:
        for k, t in [b for b in bullets if b not in quantified][:2]:
            improvement.append(f"Add a measurable outcome to: \"{t[:100]}\" (e.g. a %, $, or count of impact).")
    return score, confidence, evidence_refs, reasoning, improvement


def _score_clarity_structure(by_section: dict, req: dict):
    required_sections = req.get("required_sections", DEFAULT_REQUIRED_SECTIONS)
    max_len = req.get("max_bullet_length_chars", DEFAULT_MAX_BULLET_LENGTH)
    present, missing = _section_presence(by_section, required_sections)
    section_score = 100 * len(present) / len(required_sections) if required_sections else 100.0

    bullets = collect_bullets(by_section)
    long_bullets = [(k, t) for k, t in bullets if len(t) > max_len]
    length_score = 100.0 if not bullets else 100 * (1 - len(long_bullets) / len(bullets))

    score = round(0.6 * section_score + 0.4 * length_score, 1)
    confidence = 0.85 if by_section else 0.4
    evidence_refs = list(present) + [k or t[:60] for k, t in long_bullets[:3]]

    reasoning = (
        (f"Missing section(s): {', '.join(missing)}." if missing
         else f"All required sections present ({', '.join(required_sections)}).")
    )
    if long_bullets:
        reasoning += f" {len(long_bullets)} bullet(s) exceed the {max_len}-character guideline, hurting scannability."

    improvement = [f"Add a clearly labeled '{s}' section." for s in missing]
    for k, t in long_bullets[:2]:
        improvement.append(f"Shorten this bullet to under {max_len} characters: \"{t[:80]}...\"")
    return score, confidence, evidence_refs, reasoning, improvement


def _score_completeness(by_section: dict, req: dict):
    required_sections = req.get("required_sections", DEFAULT_REQUIRED_SECTIONS)
    min_entries = req.get("min_experience_entries", DEFAULT_MIN_EXPERIENCE_ENTRIES)
    present, missing = _section_presence(by_section, required_sections)
    section_score = 100 * len(present) / len(required_sections) if required_sections else 100.0

    entry_count = count_experience_entries(by_section)
    entries_score = 100.0 if entry_count >= min_entries else (
        100 * entry_count / min_entries if min_entries > 0 else 100.0
    )

    score = round(0.5 * section_score + 0.5 * entries_score, 1)
    confidence = 0.85 if present else 0.4
    evidence_refs = list(present)

    reasoning = (
        f"{len(present)}/{len(required_sections)} required section(s) present"
        + (f"; missing {', '.join(missing)}." if missing else ".")
        + f" Found {entry_count} experience entr{'y' if entry_count == 1 else 'ies'} "
        f"(rubric wants at least {min_entries})."
    )

    improvement = [f"Add a '{s}' section." for s in missing]
    if entry_count < min_entries:
        improvement.append(
            f"Add at least {min_entries - entry_count} more experience entry to meet the minimum of {min_entries}."
        )
    return score, confidence, evidence_refs, reasoning, improvement


def _score_relevance_to_role(by_section: dict, goal_profile: dict):
    source, all_terms, missing = find_role_term_gap(by_section, goal_profile)
    if not all_terms:
        return (
            50.0, 0.3, [],
            "No target role or job description text available to compare against; defaulting to a neutral score.",
            ["Fill in a target role (and ideally a job description) so relevance can be measured."],
        )
    matched = [t for t in all_terms if t not in missing]
    score = round(min(100.0, 100 * len(matched) / len(all_terms)), 1)
    jd_present = bool((goal_profile or {}).get("job_description"))
    confidence = 0.8 if jd_present else 0.55
    evidence_refs = matched[:8]
    reasoning = (
        f"{len(matched)} of {len(all_terms)} term(s) from {source} appear in your profile"
        + (f" (e.g. {', '.join(matched[:5])})." if matched else ".")
    )
    improvement = []
    if missing:
        improvement.append(
            f"Where genuinely true, mention: {', '.join(missing[:6])} -- term(s) from {source} absent from your profile."
        )
    return score, confidence, evidence_refs, reasoning, improvement


def _score_keyword_alignment(by_section: dict, goal_profile: dict):
    source, all_keywords, missing = find_keyword_gap(by_section, goal_profile)
    if not all_keywords:
        return (
            50.0, 0.3, [],
            "No job description or matching role keyword bank available; defaulting to a neutral score.",
            ["Paste the job description into your goal profile for precise keyword matching."],
        )
    matched = [k for k in all_keywords if k not in missing]
    score = round(min(100.0, 100 * len(matched) / len(all_keywords)), 1)
    jd_present = bool((goal_profile or {}).get("job_description"))
    confidence = 0.8 if jd_present else 0.5
    evidence_refs = matched[:8]
    reasoning = (
        f"Matched {len(matched)} of {len(all_keywords)} keyword(s) from {source}"
        + (f" (e.g. {', '.join(matched[:5])})." if matched else ".")
    )
    improvement = []
    if missing:
        improvement.append(
            f"If genuinely applicable, work these keywords into your bullets/skills: {', '.join(missing[:6])}."
        )
    return score, confidence, evidence_refs, reasoning, improvement


_HANDLERS = {
    "impact_quantification": lambda by_section, goal_profile, req: _score_impact_quantification(by_section, req),
    "clarity_structure": lambda by_section, goal_profile, req: _score_clarity_structure(by_section, req),
    "completeness": lambda by_section, goal_profile, req: _score_completeness(by_section, req),
    "relevance_to_role": lambda by_section, goal_profile, req: _score_relevance_to_role(by_section, goal_profile),
    "keyword_alignment": lambda by_section, goal_profile, req: _score_keyword_alignment(by_section, goal_profile),
}


def compute_scores(extracted_fields: list[dict], goal_profile: dict, rubric: dict) -> list[dict]:
    rubric = rubric or {}
    by_section = group_by_section(extracted_fields)
    evidence_requirements = rubric.get("evidence_requirements", {}) or {}
    goal_profile = goal_profile or {}

    results = []
    for dim in rubric.get("dimensions", []):
        key = dim["key"]
        req = evidence_requirements.get(key, {}) or {}
        handler = _HANDLERS.get(key)
        if handler is None:
            score, confidence, evidence_refs, reasoning, improvement = (
                50.0, 0.3, [],
                f"No scoring heuristic implemented for dimension '{key}'; defaulting to a neutral score.",
                [],
            )
        else:
            score, confidence, evidence_refs, reasoning, improvement = handler(by_section, goal_profile, req)
        results.append({
            "dimension": key,
            "score": round(max(0.0, min(100.0, score)), 1),
            "confidence": round(max(0.0, min(1.0, confidence)), 2),
            "evidence_refs": list(evidence_refs),
            "reasoning_summary": reasoning,
            "improvement_conditions": list(improvement),
        })
    return results
