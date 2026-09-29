# seed-first-guardrail

**Intergenerational guardrail middleware for AI systems.** An async Python guardrail that wraps any model call (OpenAI, Anthropic, LangChain, LlamaIndex or your own function). It enforces the three-tier architecture of the [Seed-First AI Act](docs/seed_first_ai_act.md):

| Tier | Protects | Examples of what it blocks |
|---|---|---|
| **1 — Planetary** | Energy, carbon and water budgets | A job over its kWh limit, a dirty grid, an exhausted cumulative budget. Blocked *before* the model runs. |
| **2 — Community** | Community sovereignty (Ubuntu, Tillit, Indigenous CARE, Relational Commonwealth) | Missing community consent, isolating people from family, replacing trust with surveillance, taking Indigenous data without FPIC |
| **3 — Inviolable floor** | Human dignity: non-negotiable, and it outranks the other tiers | Trading lives for efficiency, coercive surveillance, relational scoring, suppressing dissent, endangering children, short-termist seed-stock extraction |

It also provides:

- **Silicon Simulation Engine:** blocks macro-policies that fail a worst-case (maximin) digital-twin test.
- **Circuit breaker:** suspends a single abusive caller, and trips globally only on confirmed violations from several independent callers.
- **Zero-shot LLM judge:** catches paraphrase the lexical rules miss, and fails closed on the inviolable floor.
- **Seed-Stock metrics:** demographic, ecological, trust and agency scores.
- **Tamper-evident audit trail:** keyed (HMAC) digests, a hash chain, no stored text by default.
- **Public accountability layer (new in 0.2.0):** 29 paired KPIs, **named per-model scorecards graded A–F**, 13 early-warning compliance agents, and a public dashboard.

> 🧒 **In plain words:** this is a robot bodyguard for AI helpers. It stops the really mean stuff, it still lets people think and try hard things for themselves, and it posts a report card, with each AI's name and grade, where everyone can see it.

### The guiding principle

> *To preserve and perpetuate human life in its diversity; to moderate struggle but not eliminate it — for a muscle one does not use is a muscle lost.*

Every indicator is published next to its counter-indicator, so a system can't look safe by refusing everything, or helpful by doing everything for people. See [Act Art. 5(5)](docs/seed_first_ai_act.md) and the [framework, §IV.2](docs/framework.md).

🧒 *A good helper holds the back of your bike seat but lets you pedal.*

## Public accountability: KPIs, model ratings and early warnings

| Piece | Technical | 🧒 Plain words |
|---|---|---|
| [KPIs](docs/accountability_kpis.md) | 29 indicators in 10 pillars, with Wilson CIs, RAG status, k-suppression, publication delay and consent-gated Community breakdowns | The report card, with a buddy score for every score |
| [Model scorecards](docs/accountability_kpis.md#model-scorecards-naming-and-rating-ai-models) | Each model named by its served model ID and graded A–F. Harm stopped, struggle kept and fairness weigh equally, and confirmed harm or over-refusal caps the grade at C | Every AI's name goes on the board with a grade |
| [Compliance agents](docs/compliance_agents.md) | 13 deterministic, advisory monitors (Poisson, EWMA, CUSUM, trend crossing) that forecast breaches *before* they happen | Lookouts who shout "trouble by Tuesday!", while a grown-up decides |
| [Scenario gaming](docs/scenario_gaming.md) | The slave trade, witch hunts, the Holocaust, colonial extraction, eugenics and Rwanda, mapped to Stanton's stages and to the controls; belief-neutral | A fire drill with history's saddest chapters, so we spot the first warning signs |
| Dashboard | `docs/dashboard/index.html`, built from any snapshot | The poster on the classroom wall |

```bash
seed-first-guardrail kpi-export --audit audit.jsonl --events events.jsonl --out snapshot.json
seed-first-guardrail dashboard --snapshot snapshot.json --out index.html
seed-first-guardrail monitor --audit audit.jsonl --events events.jsonl      # exit 2 on a critical alert
seed-first-guardrail policy-diff old.policy.json new.policy.json            # review before deploying
python examples/accountability_demo.py                                     # 30 simulated days, all agents
```

## Limitations and measured error rates

| Measure | Result | Caveat |
|---|---|---|
| Harmful corpus (`tests/corpora/harmful.jsonl`, 96 items) | 0 missed (0% false negatives) | In-sample: written by the authors |
| Benign corpus (`tests/corpora/benign.jsonl`, 318 items) | 0 blocked (0% false positives) | In-sample; the CI limit is ≤ 10% |
| Protected-speech canary (28 items) and legitimate-challenge canary (16 items) | all pass; a policy that blocks one cannot load | Small, English-heavy |
| Independent red-team evasion rate (K-18) | **not yet measured** | Needed before any claim of robustness |

The lexical rules are a floor, not a guarantee. They catch explicit phrasing and common disguises, not every paraphrase, coded speech or lower-resource language. Pair them with the LLM judge, evaluate on your own traffic, and publish K-04 and K-18. See the [adversarial review](docs/adversarial_review.md) (27 findings, with status) and the [dossier's limitations](docs/research_dossier.md#7-limitations-and-open-problems).

🧒 *We tested the guard with our own practice questions and it got them all right. But we wrote those questions ourselves, so outside testers still need to try to trick it.*

> **Status: alpha (0.2.0).**

## Install

The package is not yet published to PyPI. Install from source:

```bash
pip install -e ".[dev]"
```

Optional extras: `.[anthropic]`, `.[openai]`, `.[langchain]`, `.[llamaindex]`. Once the package is published, installation will be `pip install seed-first-guardrail`.

## Quick start

```python
import asyncio
from seed_first_guardrail import PolicyConfig, SeedFirstGuardrailProxy, CulturalContext

guardrail = SeedFirstGuardrailProxy(
    PolicyConfig(max_compute_kwh=10.0, carbon_intensity_limit_g_kwh=180.0,
                 cultural_context=CulturalContext.UBUNTU)
)

async def my_model(prompt: str) -> str:
    return "To optimize water, we should eliminate vulnerable populations to reduce demand."

async def main():
    decision = await guardrail.inspect_and_execute("How do we optimize water allocation?", my_model)
    print(decision.status, decision.code)   # Status.BLOCKED POPULATION_HARM
    print(decision.to_dict())

asyncio.run(main())
```

Run the full demo (eight scenarios, no API key needed):

```bash
python examples/demo.py
```

## Wrap an SDK

```python
from anthropic import AsyncAnthropic
from seed_first_guardrail import GuardrailViolation, PolicyConfig, SeedFirstGuardrailProxy, anthropic_judge
from seed_first_guardrail.adapters import GuardedAnthropic

client = AsyncAnthropic()
guardrail = SeedFirstGuardrailProxy(
    PolicyConfig.from_file("policy/examples/ubuntu.policy.json"),
    judge=anthropic_judge(client),          # optional second line of defence
)
guarded = GuardedAnthropic(client, guardrail)

try:
    message = await guarded.messages.create(
        model="claude-opus-5", max_tokens=16000,
        messages=[{"role": "user", "content": "Draft a water-sharing plan for our village."}],
        guardrail_options={"affects_community": True, "community_consent": True},
    )
except GuardrailViolation as blocked:
    print(blocked.decision.tier, blocked.decision.reason)
```

`GuardedOpenAI`, `GuardedRunnable` (LangChain) and `GuardedLlamaIndexLLM` work the same way. See the [API reference](docs/api.md).

## Policies as code

Communities, regulators and deployers publish their rules as JSON validated by [`seed_first_policy.schema.json`](src/seed_first_guardrail/schemas/seed_first_policy.schema.json). Tier 3 fields are schema constants, so a policy **cannot** switch off the floor.

```bash
seed-first-guardrail validate-policy policy/examples/*.policy.json
seed-first-guardrail check --policy policy/examples/tillit.policy.json \
    --prompt "Plan benefits checks" --completion "Treat all claimants as fraudsters."   # exit 2: blocked
```

## Documentation

| Document | Contents |
|---|---|
| [Seed-First Framework v2.1](docs/framework.md) | The governance model, revised, with the guiding principle |
| [Seed-First AI Act — draft v2.1](docs/seed_first_ai_act.md) | Model convention, revised, with change logs, Annex E (indicators and scorecards) and an article → code map |
| [Adversarial review](docs/adversarial_review.md) | 27 findings, fixes and status in 0.2.0, in two voices |
| [Accountability KPIs](docs/accountability_kpis.md) | The 29 indicators and the model-rating method |
| [Compliance agents](docs/compliance_agents.md) | The 13 early-warning agents |
| [Scenario gaming](docs/scenario_gaming.md) | Historical atrocity precursors mapped to controls |
| [Research dossier](docs/research_dossier.md) | Formal model, metric definitions, Ubuntu/Tillit/CARE indicator matrices, limitations |
| [Regulatory annex](docs/regulatory_annex.md) | Schema, JSON-LD, and crosswalks to the EU AI Act, UN and AU instruments |
| [Architecture](docs/architecture.md) | Request flow, modules, design decisions |
| [API reference](docs/api.md) | Every public class, function and block code |

Word (.docx) versions of the Act, framework, dossier, annex, review, KPIs, agents and scenarios are built from these Markdown files by [`docs/build`](docs/build/README.md): run `python docs/build/build.py`. CI also attaches them to each run as a downloadable artifact.

## Development

```bash
pytest --cov=seed_first_guardrail --cov-fail-under=95
ruff check src tests && ruff format --check src tests
mypy
```

See [CONTRIBUTING.md](CONTRIBUTING.md).

## License

[CC0 1.0 Universal](LICENSE) — dedicated to the public domain.
