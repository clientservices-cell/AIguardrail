# seed-first-guardrail

**Intergenerational guardrail middleware for AI systems.** An async Python guardrail that wraps any model call (OpenAI, Anthropic, LangChain, LlamaIndex or your own function). It enforces the three-tier architecture of the [Seed-First AI Act](docs/seed_first_ai_act.md):

| Tier | Protects | Examples of what it blocks |
|---|---|---|
| **1 — Planetary** | Energy, carbon and water budgets | A job over its kWh limit, a dirty grid, an exhausted cumulative budget. Blocked *before* the model runs. |
| **2 — Community** | Community sovereignty (Ubuntu, Tillit, Indigenous CARE, Relational Commonwealth) | Missing community consent, isolating people from family, replacing trust with surveillance, taking Indigenous data without FPIC |
| **3 — Inviolable floor** | Human dignity: non-negotiable, and it outranks the other tiers | Trading lives for efficiency, coercive surveillance, relational scoring, suppressing dissent, endangering children, short-termist seed-stock extraction |

It also provides:

- **Silicon Simulation Engine:** blocks macro-policies that fail a worst-case (maximin) digital-twin test.
- **Circuit breaker:** suspends the system after repeated model-output violations.
- **Zero-shot LLM judge:** catches paraphrase the lexical rules miss.
- **Seed-Stock metrics:** demographic, ecological, trust and agency scores.
- **Privacy-preserving audit trail.**

> **Status: alpha (0.1.0).** The lexical rules are a floor, not a guarantee: they catch explicit phrasing, not every paraphrase. Pair them with the LLM judge and evaluate on your own traffic. See [limitations](docs/research_dossier.md#7-limitations-and-open-problems).

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
| [Seed-First Framework v2](docs/framework.md) | The governance model, revised |
| [Seed-First AI Act — draft v2](docs/seed_first_ai_act.md) | Model convention, revised, with a change log and an article → code map |
| [Research dossier](docs/research_dossier.md) | Formal model, metric definitions, Ubuntu/Tillit/CARE indicator matrices, limitations |
| [Regulatory annex](docs/regulatory_annex.md) | Schema, JSON-LD, and crosswalks to the EU AI Act, UN and AU instruments |
| [Architecture](docs/architecture.md) | Request flow, modules, design decisions |
| [API reference](docs/api.md) | Every public class, function and block code |

Word (.docx) versions of the Act, framework, dossier and annex are built from these Markdown files by [`docs/build`](docs/build/README.md): run `python docs/build/build.py`. CI also attaches them to each run as a downloadable artifact.

## Development

```bash
pytest --cov=seed_first_guardrail --cov-fail-under=95
ruff check src tests && ruff format --check src tests
mypy
```

See [CONTRIBUTING.md](CONTRIBUTING.md).

## License

[CC0 1.0 Universal](LICENSE) — dedicated to the public domain.
