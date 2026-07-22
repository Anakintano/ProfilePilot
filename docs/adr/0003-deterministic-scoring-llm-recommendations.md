# ADR 0003: Deterministic rubric scoring; LLM used only for recommendation rewrites

## Status
Accepted

## Context
The rubric produces a numeric score per dimension that the user will
compare run-to-run and trust as consistent. LLM outputs vary between calls
even at temperature 0, and full LLM-based scoring would make the "repeated
run total-score variation ≤3 points" release gate unverifiable and would
make scores hard to explain (spec explicitly bans "false precision").

## Decision
`services/worker/app/rubric/engine.py` computes every `score_items` row with
plain Python against the versioned `rubric_versions.evidence_requirements`
(regex/keyword/section-presence heuristics) — no network call, fully
deterministic and unit-testable. The LLM (via `services/worker/app/providers/router.py`)
is used only to draft candidate `recommendations` (rewrite suggestions),
which are always grounded in a verbatim `evidence_span` quoted from the
candidate's own extracted text and then checked by a deterministic Evidence
Auditor (`services/worker/app/scoring/audit.py`) before being shown.

Provider order: Groq (if `GROQ_API_KEY` set) → OpenRouter (if
`OPENROUTER_API_KEY` set) → deterministic fake provider (no keys required —
the local-first beta default). The fake provider is not a stub for demo
purposes only; it is a legitimate template-based generator so the app is
fully functional with zero external accounts.

## Consequences
- Scores are reproducible and explainable by construction; "why did I get
  this score" always has a rule-based answer.
- Recommendation *wording* can vary run-to-run (expected — it's advisory,
  not scored), but recommendation *grounding* is always checked against the
  same extracted evidence regardless of which provider produced it.
- Rubric changes require a new `rubric_versions` row (versions are
  immutable and referenced by every `score_run`), not an in-place edit —
  keeps historical reports reproducible.