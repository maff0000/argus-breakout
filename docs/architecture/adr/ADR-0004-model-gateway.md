# ADR-0004 — Model access through an OpenAI-compatible local gateway

**Status:** Accepted · **Date:** 2026-10-19

## Context
The brief is written by a local 30B-class model served behind a gateway
that offers an OpenAI-compatible API, prefix caching, a ≈30K-token window
and limited concurrency. The repository is public.

## Decision
The scanner talks only to `LLM_BASE_URL` with `LLM_API_KEY`, using model
names from `LLM_MODEL_BRIEF`, `LLM_MODEL_REVIEW`, `LLM_MODEL_FAST`,
`LLM_MODEL_EMBED`. No host, port, alias or model name appears in source,
tests or docs. The client sets no cache-salt or routing headers. Prompts
are assembled static-first (system prompt, schema) and data-last to benefit
from prefix caching. Budget: evidence pack ≤ 12K tokens, prompt ≤ 24K,
completion ≤ 1.5K; at most 2 concurrent requests from the scanner.

## Consequences
- Any OpenAI-compatible endpoint works; tests use a recorded fake.
- Model changes are configuration, not code.
