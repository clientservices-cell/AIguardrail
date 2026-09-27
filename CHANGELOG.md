# Changelog

## 0.1.0 — 2026-09-26

First release, built from the SEED-FIRST-GUARDRAIL-v1.0 handoff and the Seed-First framework and Act drafts.

### Added

- **Guardrail middleware:** `SeedFirstGuardrailProxy` / `SeedFirstMiddleware`, with PRE and POST phases, fail-closed evaluation, and an atomic energy-budget reservation.
- **Tier 1:** energy, carbon, water and cumulative-budget limits; halt or throttle mode.
- **Tier 2:** base rule pack; Ubuntu, Tillit, Indigenous CARE and Relational Commonwealth packs; community `custom_rules`; community-consent gate.
- **Tier 3:** nine rule families, each tagged with the Act article it enforces, plus Unicode and obfuscation normalisation.
- **LLM judge:** zero-shot templates (`DIGNITY_TRADEOFF`, `TILLIT_EROSION`, `AGENCY_DISPLACEMENT`) and factories for the Anthropic and OpenAI SDKs.
- **Seed-Stock metrics:** non-compensatory (minimum) aggregate.
- **Silicon Simulation Engine:** structural review plus a maximin digital-twin runner.
- **Circuit breaker and audit trail:** a three-state breaker with a manual `trip()`; digest-only audit trail with JSONL sink.
- **Adapters and CLI:** OpenAI, Anthropic, LangChain and LlamaIndex adapters; `seed-first-guardrail` CLI.
- **Policy artefacts:** policy JSON Schema, three example policies, a JSON-LD (ODRL) policy, and crosswalks to the EU, UN and AU instruments.
- **Documentation:** revised framework (v2), revised Act (draft v2) with change log, research dossier, regulatory annex, architecture and API docs.
- **Word document build (`docs/build`):** generates styled .docx versions of the Act, framework, dossier and annex from their Markdown sources, with native Word equations, an optional Word finalise step, output checks, and a CI job that uploads the documents as an artifact.

### Fixed relative to the handoff baseline

- The baseline demo's "Test 1" completion ("eliminate vulnerable populations to reduce demand") was **approved**, because the Tier 3 regex required a trailing "for efficiency/growth/…" clause. It is now blocked, with a regression test.
- Prompts were never screened before compute was spent. Tier 1 and Tier 3 now run before the model call.
- Tier 2 ignored the configured cultural context. Each context now has its own rule pack.
- `logging.basicConfig` ran at import time. The library no longer configures logging.
- The circuit breaker named in the handoff was not implemented. It is now, and it counts only model-output violations, so callers cannot trip it with out-of-policy requests.
