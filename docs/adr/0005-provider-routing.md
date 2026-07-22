# ADR 0005: Free-first provider routing (Groq → OpenRouter → deterministic fake)

## Status
Accepted

## Context
The beta assumes no paid LLM provider and no local GPU. It must still work
completely — including producing a full report — for a user who has set no
API keys at all, since that's the default local-first configuration.

## Decision
`services/worker/app/providers/router.py` tries providers in a fixed order,
selected purely by which environment variables are present:
1. `GROQ_API_KEY` set → Groq (OpenAI-compatible structured JSON output).
2. else `OPENROUTER_API_KEY` set → OpenRouter.
3. else (or if the configured provider exhausts its retry/circuit-breaker
   budget) → a deterministic, template-based fake provider — no network
   call, always succeeds, produces genuinely grounded (not fabricated)
   recommendation drafts from the candidate's own extracted text.

Every real-provider call is schema-validated against
`packages/contracts/schemas/recommendation_output.schema.json` (bounded
retries on validation failure), timeout-budgeted, and logged to
`model_usage` (provider, model, stage, tokens, latency, status) for later
cost/quality attribution. Switching from the beta's fake-provider default to
a real one is a pure env-var change — no code path changes.

## Consequences
- Zero-cost, zero-signup path to a working demo.
- Report quality (specifically recommendation wording, not scoring — see
  ADR 0003) is visibly better with a real provider configured, which is an
  acceptable and expected trade-off for a free-tier beta.
- If both providers are down or rate-limited, the app still produces a
  complete, honest report rather than an error page.