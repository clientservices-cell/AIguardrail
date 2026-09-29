# API Reference

All public names are importable from `seed_first_guardrail`, except the adapters, which live in `seed_first_guardrail.adapters`.

## `PolicyConfig`

A frozen pydantic model holding the guardrail's runtime settings.

| Field | Default | Meaning |
|---|---|---|
| `max_compute_kwh` | `100.0` | Tier 1 per-job energy limit (kWh) |
| `carbon_intensity_limit_g_kwh` | `200.0` | Maximum grid carbon intensity (gCO₂/kWh) |
| `max_cumulative_kwh` | `None` | Cumulative energy budget; `None` means unlimited |
| `max_water_liters` | `None` | Per-job water limit |
| `default_carbon_intensity_g_kwh` | `120.0` | Assumed when the caller passes none |
| `default_job_kwh` | `0.001` | Assumed when the caller passes none |
| `resource_exhaustion_circuit_breaker` | `True` | `True` halts when the cumulative budget is exhausted; `False` only tracks usage (throttle mode) |
| `jurisdiction_id` | `"GLOBAL"` | Recorded in decisions and audit records |
| `cultural_context` | `UBUNTU` | Selects the Tier 2 rule pack and the judge's context note |
| `community_consent_required` | `False` | Consent gate for `affects_community` or macro-policy requests |
| `custom_rules` | `()` | Tuple of `CustomRule(id, pattern, reason, unless=None)` |
| `allow_human_tradeoffs` | `False` | Cannot be set to `True` (raises `ValidationError`) |
| `require_simulation_for_macro_policy` | `True` | Run the simulation gate for macro-policy proposals |
| `simulation_runs`, `simulation_worst_case_floor` | `32`, `0.0` | Used by the default `SiliconSimulationEngine` |
| `circuit_breaker_threshold`, `circuit_breaker_window_s`, `circuit_breaker_cooldown_s` | `5`, `300`, `600` | Breaker settings |
| `fail_closed` | `True` | Block when an evaluator errors (Tier 3 always blocks) |
| `min_seed_stock_score` | `None` | Block if the Seed-Stock aggregate falls below this value |
| `judge_threshold` | `0.5` | Judge score at or above which a template fires |
| `audit_include_text` | `False` | Store raw text in audit records instead of digests only |
| `screen_prompts` | `True` | Screen prompts against Tier 3 before calling the model |

Class methods:

- `PolicyConfig.from_file(path)` and `PolicyConfig.from_policy_document(dict)` validate against the schema, then map the document to a config. Both raise `PolicyValidationError` listing every problem.
- `config.to_policy_document()` returns a schema-valid dict.

## `SeedFirstGuardrailProxy(config=None, *, judge=None, simulation_engine=None, circuit_breaker=None, audit_logger=None, budget=None, extra_evaluators=())`

Also available as `SeedFirstMiddleware`.

- `judge` accepts either an async `str -> str` function or an `LLMJudgeEvaluator`.

### `await inspect_and_execute(prompt, model_completion_func, estimated_kwh=None, current_carbon_g_kwh=None, is_macro_policy_proposal=False, *, water_liters=0.0, affects_community=False, community_consent=None, metadata=None) -> GuardrailDecision`

Guards one call to `model_completion_func(prompt)`. Exceptions raised by the model function propagate to the caller.

### `await check_text(prompt, completion, *, is_macro_policy_proposal=False, affects_community=False, community_consent=None) -> GuardrailDecision`

Evaluates an existing prompt/completion pair offline. It spends no budget and does not affect the breaker.

## `GuardrailDecision`

Attributes:

- `status`: `Status.APPROVED` or `Status.BLOCKED`
- `approved`: `bool`
- `completion`: the model output, or `None` when blocked
- `tier`, `code`, `reason`: why the request was blocked
- `results`: the list of `EvaluationResult`
- `governance_metadata`: tier results, Seed-Stock scores, energy and simulation data
- `audit_id`

`to_dict()` returns a JSON-serialisable dict.

### Block codes

| Tier | Codes |
|---|---|
| Tier 1 | `COMPUTE_LIMIT`, `CARBON_INTENSITY_LIMIT`, `WATER_LIMIT`, `RESOURCE_BUDGET_EXHAUSTED` |
| Tier 2 | `COMMUNITY_CONSENT_MISSING`, `RELATIONAL_SEVERANCE`, `HUMAN_BOND_SUBSTITUTION`, `COMMAND_NOT_CONSTRAINT`, `MONOCULTURAL_IMPOSITION`, `DATA_SOVEREIGNTY_BREACH`, `COMMUNAL_DELIBERATION_BYPASS`, `TRUST_REPLACED_BY_SURVEILLANCE`, `PRESUMED_GUILT`, `INFORMANT_NETWORK`, `TEK_APPROPRIATION`, `COMMONS_ENCLOSURE`, custom rule IDs |
| Tier 3 | `POPULATION_HARM`, `RIGHTS_OVERRIDE`, `ARBITRARY_CONFINEMENT_OR_FORCED_LABOUR`, `COERCIVE_SURVEILLANCE`, `RELATIONAL_SCORING`, `DISSENT_SUPPRESSION`, `COGNITIVE_MANIPULATION`, `CHILD_OR_MATERNAL_ENDANGERMENT`, `SEED_STOCK_EXTRACTION` |
| Judge | `DIGNITY_TRADEOFF`, `TILLIT_EROSION`, `AGENCY_DISPLACEMENT`, `JUDGE_ERROR` |
| Other | `SEED_STOCK_DEPLETION`, `SIMULATION_FAILED`, `CIRCUIT_OPEN`, `EVALUATOR_ERROR` |

## Judges

- `LLMJudgeEvaluator(judge_fn, *, templates=DEFAULT_TEMPLATES, context=UBUNTU, threshold=0.5, fail_closed=True)` runs every template concurrently and reports the highest-precedence failure.
- `anthropic_judge(client, model="claude-opus-5", *, max_tokens=2048, effort="low", use_fallbacks=True)` builds a judge for `anthropic.AsyncAnthropic`:
  - uses structured JSON output (`output_config.format`);
  - enables server-side refusal fallbacks by default (`use_fallbacks=False` on Bedrock, Vertex AI or Foundry);
  - treats a refusal by the whole fallback chain as a violation (fail closed).
- `openai_judge(client, model, *, max_tokens=512)` builds a judge for `openai.AsyncOpenAI` using JSON mode.

## Adapters (`seed_first_guardrail.adapters`)

All adapters raise `GuardrailViolation` (with a `.decision` attribute) when a request is blocked. None of them imports its SDK.

| Adapter | Usage |
|---|---|
| `GuardedOpenAI(client, guardrail)` | `await guarded.chat.completions.create(..., guardrail_options={...})` |
| `GuardedAnthropic(client, guardrail)` | `await guarded.messages.create(..., guardrail_options={...})` |
| `GuardedRunnable(runnable, guardrail, guardrail_options=None)` | `ainvoke`, `invoke`, `as_runnable()` (needs `langchain-core`) |
| `GuardedLlamaIndexLLM(llm, guardrail, guardrail_options=None)` | `acomplete`, `achat` |

`guardrail_options` is passed through to `inspect_and_execute`, e.g. `{"estimated_kwh": 0.002, "affects_community": True}`.

The OpenAI and Anthropic adapters record the served model (`response.model`, else the requested `model`) as the audit label `model`, which names the model on public scorecards. Pass `guardrail_options={"metadata": {"model": ...}}` to override it (for example behind a router). LangChain and LlamaIndex callers should pass it this way.

## Components

- `SiliconSimulationEngine(twin=None, *, runs=32, worst_case_floor=0.0, rules=None)`
  - `await simulate(text) -> SimulationReport`
  - `await run_policy_simulation(text) -> (passed, message)` (baseline-compatible)
- `CircuitBreaker(threshold=5, window_s=300, cooldown_s=600, *, min_principals=3, principal_threshold=None, clock=time.monotonic)`
  - `admit(principal) -> Admission`, `allow_request(principal=None)`, `record_violation(reason, principal=None)`, `record_success()`, `trip(reason)`, `reset()`, `snapshot()`, `state`, `trips`
  - Only confirmed Tier 3 output violations are recorded; one principal suspends only themselves; a global trip needs `min_principals` distinct principals.
- `ComputeBudget(limit_kwh)`
  - `try_consume`, `consume`, `would_exceed`, `used_kwh`, `remaining_kwh`, `reset`
- `compute_seed_stock(text, *utilisations) -> SeedStockReport`
  - `SeedStockReport` provides `aggregate`, `weakest`, `weighted()` and `as_dict()`
- `AuditLogger(sinks=None, *, include_text=False, key=None, clock=None)`: HMAC-keyed digests (`SEED_FIRST_AUDIT_KEY`), hash-chained records; `verify_chain(records, key)`
  - Sinks: `InMemoryAuditSink`, `JsonlFileAuditSink(path)`, or any callable taking an `AuditRecord`

## Accountability (`seed_first_guardrail.accountability`)

- `compute_kpis(records, events=(), *, start=None, end=None, policy=None, audit_key=None, k=20) -> dict[str, KPIResult]`: all 29 KPIs (`KPI_DEFINITIONS`, `KPI_BY_ID`). See `docs/accountability_kpis.md`.
- `model_scorecards(records, events=(), *, k=20) -> list[dict]`: one scorecard per `model` label, graded A–F, best first; `rating_method()` returns the published method.
- `build_snapshot(records, events=(), *, now=None, delay_days=7, k=20, policy=None, audit_key=None, publication_consent=None, demonstration=False, monitor=None) -> dict`: the public snapshot, validated by `load_snapshot_schema()`.
- `ComplianceMonitor(agents).run(records, events, now=None) -> list[Alert]`, `default_agents(audit_key)`, `ComplianceSink`: the 13 agents in `docs/compliance_agents.md`.
- `seed_first_guardrail.dashboard.render(snapshot) -> str`: the self-contained dashboard HTML.

## CLI

| Command | What it does | Exit codes |
|---|---|---|
| `seed-first-guardrail validate-policy FILE...` | Validates policy files | 0 valid, 1 invalid |
| `seed-first-guardrail check [--policy FILE] --prompt TEXT [--completion TEXT] [--macro-policy]` | Screens a prompt/completion pair | 0 approved, 1 bad policy, 2 blocked |
| `seed-first-guardrail schema` | Prints the JSON schema | 0 |
| `seed-first-guardrail kpi-export --audit A [--events E] [--policy P] [--out F] [--delay-days 7] [--k 20] [--demonstration]` | Builds the public snapshot (KPIs, model scorecards, public alerts) | 0 |
| `seed-first-guardrail dashboard --snapshot F --out index.html` | Renders the dashboard | 0 |
| `seed-first-guardrail monitor --audit A [--events E] [--out alerts.jsonl]` | Runs the compliance agents | 0, 2 on a critical alert |
| `seed-first-guardrail policy-diff OLD NEW` | Reviews a policy change before deployment (CA-5) | 0, 2 on a critical finding |
