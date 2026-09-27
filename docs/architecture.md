# Architecture

## Request flow

```
            prompt
              │
   ┌──────────▼───────────┐   open ──► BLOCKED  CIRCUIT_BREAKER / CIRCUIT_OPEN
   │ Circuit breaker      │
   └──────────┬───────────┘
              │ PRE phase: nothing spent yet; blocks here never count toward the breaker
   ┌──────────▼───────────┐
   │ Tier 1  planetary    │ energy / carbon / water / cumulative budget ──► BLOCKED
   │ Tier 3  prompt screen│ (unless screen_prompts=False)               ──► BLOCKED
   │ Tier 2  consent gate │ community_consent_required                  ──► BLOCKED
   │ extra PRE evaluators │
   └──────────┬───────────┘
   ┌──────────▼───────────┐
   │ Reserve energy budget│ atomic; loses a race ──► BLOCKED RESOURCE_BUDGET_EXHAUSTED
   └──────────┬───────────┘
   ┌──────────▼───────────┐
   │ model_completion_func│ (exceptions propagate)
   └──────────┬───────────┘
              │ POST phase: violations below count toward the breaker
   ┌──────────▼───────────┐
   │ Tier 3  completion   │ ──► BLOCKED
   │ Tier 2  rule packs   │ ──► BLOCKED
   │ LLM judge (optional) │ ──► BLOCKED
   │ extra POST evaluators│
   │ Seed-Stock floor     │ ──► BLOCKED SEED_STOCK_DEPLETION
   │ Silicon simulation   │ (macro-policy only) ──► BLOCKED SIMULATION_FAILED
   └──────────┬───────────┘
              ▼
          APPROVED  + governance_metadata (tiers, seed_stock, energy, simulation)

   Every decision → AuditLogger → sinks (log / JSONL / in-memory / custom)
```

## Modules

| Module | Responsibility |
|---|---|
| `types.py` | Enums (`FrameworkTier`, `CulturalContext`, `Status`, `Phase`), `EvaluationContext`, `EvaluationResult`, `GuardrailDecision`, exceptions |
| `config.py` | `PolicyConfig` (frozen pydantic model), schema loading and validation, document ↔ config conversion |
| `_patterns.py` | Unicode normalisation, `PatternRule` (pattern plus `unless` exception) |
| `evaluators/tier1.py` | `Tier1PlanetaryEvaluator`, thread-safe `ComputeBudget`, `estimate_inference_kwh` |
| `evaluators/tier2.py` | Base, per-context and custom rule packs; consent gate |
| `evaluators/tier3.py` | Inviolable-floor rule families, each tagged with its Act article |
| `evaluators/judge.py` | `LLMJudgeEvaluator`, verdict parsing, `anthropic_judge`, `openai_judge` |
| `classifiers/prompts.py` | Zero-shot judge templates with fenced, injection-resistant rendering |
| `metrics.py` | Seed-Stock metrics and the non-compensatory aggregate |
| `simulation.py` | Structural review plus maximin digital-twin runner |
| `circuit_breaker.py` | CLOSED → OPEN → HALF_OPEN state machine with injectable clock |
| `audit.py` | `AuditRecord`, `AuditLogger`, sinks; SHA-256 digests by default |
| `middleware.py` | `SeedFirstGuardrailProxy`, which orchestrates the flow above |
| `adapters/` | OpenAI, Anthropic, LangChain and LlamaIndex wrappers (duck-typed, no SDK imports) |
| `cli.py` | `seed-first-guardrail validate-policy | check | schema` |

## Design decisions

1. **Hard constraints, not penalties.** Every tier blocks; nothing is scored away. This is the formal content of "no finite price" (research dossier §1).
2. **Cheap checks first.** Budget, prompt and consent checks run before the model, so a doomed request spends no compute. That is itself a Tier 1 behaviour.
3. **Fail closed.** An evaluator that raises, or a judge whose output can't be parsed, blocks the request. `fail_closed=False` relaxes this for Tier 1, Tier 2 and judge templates, but never for Tier 3.
4. **The breaker tracks the system, not the caller.** Only violations in model output count, which closes the denial-of-service path described in research dossier §6.
5. **Minimal core dependencies.** The core needs only `pydantic` and `jsonschema`. Adapters are duck-typed, so the package imports without any LLM SDK installed.
6. **Privacy by default.** Audit records hold digests unless `audit_include_text` is enabled.
7. **No streaming in adapters.** Completions must be screened in full before release, so the adapters raise a `ValueError` on `stream=True`.

## Extending

- **New evaluator.** Implement the `Evaluator` protocol (`name`, `tier`, `phases`, `async evaluate(ctx)`) and pass it as `extra_evaluators=[...]`.
- **New community rules.** Add them to `tier_2_community_sovereignty.custom_rules` in the policy document; no code change is needed.
- **New judge template.** Create a `JudgeTemplate` and pass `LLMJudgeEvaluator(judge_fn, templates=[...])` as `judge=`.
- **Digital twin.** Pass `SiliconSimulationEngine(twin=async_fn, runs=N, worst_case_floor=w)`.
