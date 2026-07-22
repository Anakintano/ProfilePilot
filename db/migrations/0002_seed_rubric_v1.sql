-- Rubric v1: internally authored scoring policy (not an external research
-- citation). Evidence requirements are consumed by the deterministic scoring
-- code in services/worker/app/rubric/engine.py — keep the two in sync.
INSERT INTO rubric_versions (version, effective_date, audience, dimensions, weights, evidence_requirements)
VALUES (
    'v1',
    '2026-07-22',
    'intern-to-junior software/tech candidates',
    '[
        {"key": "impact_quantification", "label": "Impact & Quantification", "description": "Bullet points demonstrate measurable outcomes rather than only listing responsibilities."},
        {"key": "clarity_structure", "label": "Clarity & Structure", "description": "Sections are complete, consistently formatted, and easy to scan."},
        {"key": "relevance_to_role", "label": "Relevance to Target Role", "description": "Experience and skills align with the stated target role and seniority."},
        {"key": "keyword_alignment", "label": "Keyword Alignment", "description": "Key terms from the job description or common role keywords appear naturally in the profile."},
        {"key": "completeness", "label": "Completeness", "description": "Required sections are present with sufficient supporting detail."}
    ]'::jsonb,
    '{
        "impact_quantification": 0.25,
        "clarity_structure": 0.15,
        "relevance_to_role": 0.25,
        "keyword_alignment": 0.15,
        "completeness": 0.20
    }'::jsonb,
    '{
        "impact_quantification": {"min_quantified_bullets": 2, "signal_regex": "\\d+%|\\$[0-9]|\\b\\d{2,}\\b"},
        "clarity_structure": {"required_sections": ["contact", "experience", "education", "skills"], "max_bullet_length_chars": 220},
        "relevance_to_role": {"compare_against": "target_role_and_job_description"},
        "keyword_alignment": {"compare_against": "job_description_or_role_keyword_bank"},
        "completeness": {"required_sections": ["contact", "experience", "education", "skills"], "min_experience_entries": 1}
    }'::jsonb
)
ON CONFLICT (version) DO NOTHING;
