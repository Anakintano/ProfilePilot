"""Standalone smoke test for the pure-Python parts of the scoring pipeline:

    rubric.engine.compute_scores -> providers.fake_provider.generate -> scoring.audit.audit_recommendations

No DB, no Docker, no network calls -- everything here is in-process pure
Python plus jsonschema validation against packages/contracts/schemas. Run
with:

    python services/worker/tests/smoke_scoring.py

(requires the `jsonschema` package the real worker also depends on; see
services/worker/requirements.txt)
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # .../services/worker, so `app` is importable

from app.providers import fake_provider  # noqa: E402
from app.rubric import engine  # noqa: E402
from app.scoring import audit  # noqa: E402

# Rubric v1, hand-copied from db/migrations/0002_seed_rubric_v1.sql -- keep in
# sync with that file if the seeded rubric ever changes.
RUBRIC = {
    "version": "v1",
    "dimensions": [
        {"key": "impact_quantification", "label": "Impact & Quantification", "description": "Bullet points demonstrate measurable outcomes rather than only listing responsibilities."},
        {"key": "clarity_structure", "label": "Clarity & Structure", "description": "Sections are complete, consistently formatted, and easy to scan."},
        {"key": "relevance_to_role", "label": "Relevance to Target Role", "description": "Experience and skills align with the stated target role and seniority."},
        {"key": "keyword_alignment", "label": "Keyword Alignment", "description": "Key terms from the job description or common role keywords appear naturally in the profile."},
        {"key": "completeness", "label": "Completeness", "description": "Required sections are present with sufficient supporting detail."},
    ],
    "weights": {
        "impact_quantification": 0.25,
        "clarity_structure": 0.15,
        "relevance_to_role": 0.25,
        "keyword_alignment": 0.15,
        "completeness": 0.20,
    },
    "evidence_requirements": {
        "impact_quantification": {"min_quantified_bullets": 2, "signal_regex": r"\d+%|\$[0-9]|\b\d{2,}\b"},
        "clarity_structure": {"required_sections": ["contact", "experience", "education", "skills"], "max_bullet_length_chars": 220},
        "relevance_to_role": {"compare_against": "target_role_and_job_description"},
        "keyword_alignment": {"compare_against": "job_description_or_role_keyword_bank"},
        "completeness": {"required_sections": ["contact", "experience", "education", "skills"], "min_experience_entries": 1},
    },
}

GOAL_PROFILE = {
    "target_role": "Software Engineer Intern",
    "seniority": "intern",
    "geography": "United States",
    "outcome": "Land a summer software engineering internship",
    "job_description": (
        "We are looking for a Software Engineering Intern with experience in Python, SQL, "
        "REST APIs, and git. You will work on our backend team building scalable services and "
        "writing automated tests."
    ),
}

# A deliberately mediocre candidate: all four required sections exist, but
# most experience bullets are un-quantified and skills are missing a few JD
# keywords -- meant to exercise every dimension's non-trivial code path.
EXTRACTED_FIELDS = [
    {"section": "contact", "field_key": "email", "value": "jane.doe@example.com", "user_corrected": False, "corrected_value": None, "confidence": 0.95},
    {"section": "contact", "field_key": "phone", "value": "555-123-4567", "user_corrected": False, "corrected_value": None, "confidence": 0.9},
    {"section": "education", "field_key": "school", "value": "State University, B.S. Computer Science, expected 2027", "user_corrected": False, "corrected_value": None, "confidence": 0.92},
    {"section": "skills", "field_key": "list", "value": "Python, Java, Git, HTML, CSS", "user_corrected": False, "corrected_value": None, "confidence": 0.88},
    {
        "section": "experience", "field_key": "experience.0.bullets",
        "value": (
            "Worked on a team project building a web dashboard\n"
            "Helped with debugging backend issues\n"
            "Wrote unit tests for the API, increasing coverage by 40%"
        ),
        "user_corrected": False, "corrected_value": None, "confidence": 0.8,
    },
    {
        "section": "experience", "field_key": "experience.1.bullets",
        "value": "Assisted senior engineers with code reviews and documentation",
        "user_corrected": True,
        "corrected_value": "Assisted senior engineers with code reviews and documentation for a 5-person team",
        "confidence": 0.75,
    },
]


def main() -> None:
    score_items = engine.compute_scores(EXTRACTED_FIELDS, GOAL_PROFILE, RUBRIC)
    print("=== SCORE ITEMS ===")
    for item in score_items:
        print(f"- {item['dimension']}: {item['score']}/100 (confidence {item['confidence']})")
        print(f"    reasoning: {item['reasoning_summary']}")
        if item["improvement_conditions"]:
            print(f"    improve: {item['improvement_conditions']}")

    recommendations, meta = fake_provider.generate(EXTRACTED_FIELDS, GOAL_PROFILE, score_items, RUBRIC)
    print(f"\n=== RECOMMENDATIONS ({len(recommendations)}, provider meta={meta}) ===")
    for rec in recommendations:
        print(json.dumps(rec, indent=2))

    audited = audit.audit_recommendations(recommendations, EXTRACTED_FIELDS)
    print("\n=== AUDIT RESULTS ===")
    for rec in audited:
        print(f"- [{rec['audit_status']}] {rec['dimension']}: {rec['audit_notes']}")

    # Sanity assertions -- fail loudly (non-zero exit) rather than silently
    # printing plausible-looking garbage.
    assert score_items, "expected at least one score item"
    assert all(0 <= i["score"] <= 100 for i in score_items), "score out of [0,100] range"
    assert all(0 <= i["confidence"] <= 1 for i in score_items), "confidence out of [0,1] range"
    assert recommendations, "expected at least one recommendation for a mediocre profile"
    assert all(r["audit_status"] in ("supported", "unsupported", "vague", "contradictory") for r in audited)
    total_score = sum(i["score"] * RUBRIC["weights"][i["dimension"]] for i in score_items)
    print(f"\nWeighted total score: {total_score:.1f}/100")
    print("OK: smoke test passed.")


if __name__ == "__main__":
    main()
