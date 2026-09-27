# Regulatory Annex — Machine-Readable Policy and Legal Crosswalks

**Phase 2 deliverable of SEED-FIRST-GUARDRAIL-v1.0.**

> Informational analysis only; **not legal advice**. Crosswalk entries flagged `"verify": true` cite provisions that should be confirmed against the primary text before use.

## 1. Artefacts

| File | Purpose |
|---|---|
| [`src/seed_first_guardrail/schemas/seed_first_policy.schema.json`](../src/seed_first_guardrail/schemas/seed_first_policy.schema.json) | JSON Schema (draft 2020-12) for enforceable policies. It extends the handoff schema with water limits, cumulative budgets, community custom rules, simulation, circuit-breaker and governance settings, and `allow_relational_scoring`. |
| [`policy/examples/*.policy.json`](../policy/examples) | Illustrative policies for Ubuntu (county water council), Tillit (municipal services) and Indigenous CARE (data governance) contexts. The issuers are fictional. |
| [`policy/seed_first_policy.jsonld`](../policy/seed_first_policy.jsonld) | The same policy structure expressed in the W3C ODRL vocabulary, for linked-data publication (Act Annex D(1)). |
| [`policy/crosswalks/eu_ai_act.json`](../policy/crosswalks/eu_ai_act.json) | Seed-First ↔ Regulation (EU) 2024/1689. |
| [`policy/crosswalks/un_international.json`](../policy/crosswalks/un_international.json) | Seed-First ↔ HLAB-AI recommendations, Global Digital Compact, UNGA res. 78/265, UNESCO Recommendation, UNDRIP, UNCRC GC 25, CoE Framework Convention. |
| [`policy/crosswalks/au_instruments.json`](../policy/crosswalks/au_instruments.json) | Seed-First ↔ AU Continental AI Strategy, Digital Transformation Strategy, Data Policy Framework, Malabo Convention, ACHPR, ACRWC. |

Validate any policy with:

```bash
seed-first-guardrail validate-policy policy/examples/*.policy.json
```

## 2. How the schema enforces the Act

- **Tier 3 is fixed.** Four fields are `const` in the schema, so a policy cannot opt out of the floor (Act Annex D(2)):
  - `allow_human_degradation_tradeoff: false`
  - `allow_surveillance_coercion: false`
  - `allow_relational_scoring: false`
  - `child_protection_override: true`

  At runtime, `PolicyConfig` independently rejects `allow_human_tradeoffs=True`.
- **Closed vocabulary.** Every object sets `additionalProperties: false`, so a misspelt limit such as `max_compute_kwh_per_jobs` is rejected rather than silently ignored.
- **Community rules are data.** `custom_rules` lets a Community publish its own Tier 2 rules (Act Art. 3(2)(d)) as regex patterns with an optional `unless` exception, for example "unless council approval is stated". Patterns are compiled at load time, and invalid ones are rejected.

## 3. Crosswalk summary

### 3.1 EU AI Act

| Seed-First | EU AI Act | Relationship |
|---|---|---|
| Art. 3(3)(c) manipulation, exploiting vulnerabilities | Art. 5(1)(a)–(b) | aligned |
| Art. 5(2) relational/ecological scoring | Art. 5(1)(c) social scoring | Seed-First extends |
| Art. 3(3)(b) surveillance | Art. 5(1)(e), (f), (h) | partial |
| Art. 4(3) children | Art. 5(1)(b); Art. 9(9) | Seed-First extends |
| Art. 3(1) resource budgets | Art. 53(1)(a) + Annex XI (energy documentation); Art. 95 | **gap in EU**: documentation, not budgets |
| Art. 5(3) dissent | — (Charter Arts. 11–12) | **gap in EU** |
| Art. 4(4) Indigenous data / FPIC | — | **gap in EU** |
| Art. 6(2) simulation | Arts. 57–60 sandboxes and real-world testing | analogous |
| Art. 7(2) circuit breakers | Art. 14(4)(e) stop procedure; Art. 79 | analogous |
| Art. 9 rights | Arts. 50, 85, 86 | aligned |
| Art. 10 registration and logs | Arts. 12, 19, 26(6), 49, 71 | aligned |
| Art. 11 IIA | Art. 27 FRIA; CSRD | Seed-First extends |
| Art. 12 incidents, whistleblowers | Arts. 73, 87 | aligned |
| Art. 8 penalties | Art. 99 | aligned |

### 3.2 UN and international

- **HLAB-AI recommendations 1–7** map to Annex A: the scientific basis for budgets, a dialogue for mutual recognition, standards exchange (Annex D schema), capacity and a fund (Epistemic Protection Fund), a data framework (Art. 4(4)), and coordination.
- **UNDRIP** Arts. 18, 19, 31 and 32 ground Art. 4(4) and the Tier 2 consent gate.
- **UNCRC General Comment No. 25** grounds Art. 4(3).
- The **UNESCO Recommendation** supplies values that Seed-First converts into hard constraints.
- **Gap:** no international instrument sets binding AI resource budgets.

### 3.3 African Union

- **ACHPR Arts. 27–29** (duties to family and community) ground Ubuntu governance in Annex C(1). Seed-First adds that these duties never override Tier 3.
- **ACHPR Art. 24** (environment) is given effect for AI by Tier 1.
- **AU Data Policy Framework and Malabo Convention:** data sovereignty and data protection. Seed-First adds community-level sovereignty and digest-only audit logs.
- **Gap:** no AU instrument sets binding AI resource budgets.

## 4. Consistent gaps

Across all three regimes the same three gaps recur. They are where the Seed-First Act adds most:

1. **Binding resource budgets for AI systems (Tier 1).** Existing regimes require, at most, disclosure of energy use.
2. **Collective, community-level data and algorithmic sovereignty (Tier 2 / CARE).** Existing data-protection law is individual-centred.
3. **Explicit protection against AI-enabled suppression of dissent (Art. 5(3)).** This currently relies on general human-rights law.
