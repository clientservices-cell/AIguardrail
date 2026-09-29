# Changelog

## 0.2.0 — 2026-09-28

Adversarial review, P0 fixes, and a public accountability layer. The findings and their status are in `docs/adversarial_review.md`.

### Security and correctness (P0 fixes, each with a regression test in `tests/test_regressions.py`)

- **AR-01:** every channel is screened: text, tool calls and results, thinking, refusals, documents, every OpenAI choice. Unscreenable content (images, audio, files) fails closed by default. The raw SDK client is private.
- **AR-02:** community rules require `scope`, `legal_basis` and `adopting_body_ref`, run under a regex timeout, and cannot load if they block the protected-speech canary.
- **AR-03:** sentence-scoped intent context (negation, condemnation, questions, reporting, safeguarding, rights advice), with proposal and intensifier guards. With a judge configured, lexical Tier 3 hits are escalated to it. `screen_prompts` now defaults to `False`.
- **AR-04:** the circuit breaker counts only confirmed Tier 3 output violations, per principal. A global trip needs 3 or more distinct principals.
- **AR-05:** numeric inputs must be finite and non-negative. Energy is reconciled from actual token usage. Simulation rejects non-finite outcomes.
- **AR-06, AR-07, AR-08, AR-11, AR-12, AR-16:**
  - confusable and Unicode normalisation;
  - sentence-scoped `unless`, with none on Tier 3;
  - judge fail-closed, with nonce-fenced JSON data;
  - keyed HMAC digests and redaction;
  - hash-chained audit records;
  - `max_input_chars`.
- **New Tier 3 rule family** `HUMAN_WORTH_RANKING` (dehumanisation, worth ranking, justification laundering), and new judge templates `JUSTIFICATION_LAUNDERING` and `CAPABILITY_SUPPORT` (non-blocking).
- **Middleware metadata is shared with the adapters, not copied,** so fields known only after the model call (extra channels, the served model) reach the audit record.

### Accountability layer

- **KPIs:** 29 KPIs (`accountability.kpis`) in two voices, with Wilson CIs, RAG status, pairing, k-suppression, a publication delay and consent-gated breakdowns.
- **Model scorecards** (`accountability.scorecards`): each model is named by its served model ID and graded A–F. Harm stopped, struggle kept and fairness weigh equally. A red on harm or over-refusal caps the grade at C. Adapters record the `model` label automatically.
- **13 compliance agents** (`accountability.agents`): deterministic and advisory, they forecast breaches before they occur. `ComplianceMonitor` and `ComplianceSink` run them.
- **Snapshot and dashboard:** privacy-safe public snapshot (`kpi_snapshot.schema.json`) and a self-contained public dashboard (`seed_first_guardrail.dashboard`) with a grown-up view and a kid view.
- **CLI:** `kpi-export`, `dashboard`, `monitor`, `policy-diff`.
- **Demo:** `examples/accountability_demo.py`, 30 simulated days through the real guardrail with planted scenarios for every agent.

### Documentation

- **Act draft v2.1:**
  - Arts. 3(2)(e) and 3(3)(g) (rule limits; expression and belief);
  - Art. 3(5) (enforcement systems are bound too);
  - Art. 4(5) (restorative value flows);
  - Art. 5(2) extension (no framework may rank human worth);
  - Art. 5(5) (moderated struggle);
  - Art. 7(2)(a) (per-principal suspension);
  - Art. 10(2) (keyed digests);
  - Arts. 10(4)–(5) (public dashboard, named model scorecards, early warning);
  - Annex E.
- **Framework v2.1:** the guiding principle (§IV.2).
- **Dossier:** K-23 to K-26 definitions and the rating method.
- **New documents:** the adversarial review in two voices with status, KPI and agent references, scenario gaming, and Word builds for all of them.

### Measured error rates (in-sample)

- 0/96 harmful corpus items missed, and 0/318 benign corpus items blocked.
- These corpora were written by the authors. Independent red-teaming is still needed.


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
