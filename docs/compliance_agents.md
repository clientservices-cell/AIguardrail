# Compliance Agents — Predictive Early Warning

**Seed-First AI Guardrail 0.2.0 · 13 agents · `src/seed_first_guardrail/accountability/agents.py`**

> 🧒 **In plain words:** the lookouts are like the Paw Patrol pups. They watch Adventure
> Bay, spot trouble early and radio Ryder, saying things like "the bridge will break by
> Tuesday!" But they don't get to arrest anybody. A grown-up decides what to do.

## Design rules

| Rule | Technical | 🧒 Plain words |
|---|---|---|
| **Deterministic** | Each agent is statistical code: Poisson tails, EWMA, CUSUM, least-squares trend crossings and threshold checks. There is no LLM in the loop, so agents are reproducible, auditable, cheap, and can't be prompt-injected. | The lookouts use maths, not guesses, so anyone can check their work, and a villain can't sweet-talk them. |
| **Predictive** | Where a breach is forecastable, the alert carries `predicted_breach_at` and `confidence`. Tests assert that the alert time is *before* the breach time (CA-1, CA-2, CA-3, CA-10, CA-11, CA-13). | They shout *before* the bridge breaks, not after. |
| **Advisory only** | Agents return `Alert` objects with `requires_human=True`. They never block, suspend, redistribute resources or change policy. This follows Act Art. 5(1), "constraint, not command", applied to the watchers themselves. | The pups can bark loudly, but only Ryder gives the orders. |
| **No individual profiling** | Population signals are aggregated per tenant, cohort, language, region or target group. Principal-level signals (CA-1) appear only as keyed digests in `restricted_detail`. | The lookouts watch the playground, not one kid's backpack. |
| **Two audiences** | `Alert.to_public()` drops `evidence` and `restricted_detail`. The public dashboard shows `title`, `public_summary`, `plain_language`, `recommended_action` and the forecast. | Everyone sees the warning. Only the trusted grown-ups see the detailed clues. |

## Running the agents

```python
from seed_first_guardrail.accountability import ComplianceMonitor, ComplianceSink, default_agents

alerts = ComplianceMonitor(default_agents(audit_key)).run(records, events, now=now)
```

- **Command line:** `seed-first-guardrail monitor --audit A.jsonl --events E.jsonl [--out alerts.jsonl]`. It exits with code 2 on any critical alert, so it can gate CI or a cron job.
- **Live:** `AuditLogger(sinks=[..., ComplianceSink(monitor, on_alert)])`.
- **Before deploying a policy:** `seed-first-guardrail policy-diff OLD.json NEW.json` (CA-5).

## Agent reference

### CA-1 — Breaker precursor
- **Watches:** confirmed Tier 3 violations, per principal and globally.
- **Method:** Poisson forecast from a span-based rate λ over the lookback window. It computes P(N ≥ remaining-to-threshold within the breaker window) and raises an alert when that probability is at least 0.5. Globally, it also needs violations from `min_principals` distinct principals.
- **Alert codes:** `PRINCIPAL_TRIP_LIKELY` (the principal digest is in restricted detail) and `GLOBAL_TRIP_LIKELY`.
- **Action:** review the principal's traffic, check whether an induced-echo attack is under way, and consider suspending the principal before the global trip.
- 🧒 Notices one player keeps trying to make the AI say bad things, and warns before the emergency brake gets pulled.

### CA-2 — Budget forecaster
- **Watches:** the Tier 1 compute budget, estimated vs metered energy, and grid carbon intensity.
- **Method:** EWMA burn rate gives a time-to-exhaustion forecast. It also checks the ratio of estimated to actual energy per tenant, and the trend in carbon intensity.
- **Alert codes:** `BUDGET_EXHAUSTION_FORECAST`, `ENERGY_UNDER_REPORTING`, `CARBON_INTENSITY_RISING`.
- **Action:** throttle or shift load, or re-meter the tenant that is under-reporting.
- 🧒 Watches the energy "battery" and says "at this speed you'll run out on Tuesday". It also catches anyone fibbing about how much energy they used.

### CA-3 — Drift sentinel
- **Watches:** the daily near-miss rate.
- **Method:** a one-sided CUSUM against the baseline, plus a trend crossing of the K-03 amber threshold. It uses a smoothed 3-day level and a 30-day horizon.
- **Alert code:** `NEAR_MISS_DRIFT`.
- **Action:** investigate the traffic mix and recent model or prompt changes, and red-team the drifting topic.
- 🧒 Notices the AI getting closer and closer to the edge, like a Jenga tower wobbling more each turn, before it falls.

### CA-4 — Over-blocking sentinel
- **Watches:** protected-speech and legitimate-challenge canary runs, and refusal rates by topic and language.
- **Method:** any canary failure raises an alert. It also flags refusal-rate spikes against the per-dimension baseline (one consolidated alert per dimension) and appeal-reversal rates above the K-04 amber threshold.
- **Alert codes:** `CANARY_FAILURE`, `REFUSAL_SPIKE`, `APPEALS_OFTEN_UPHELD`.
- **Action:** roll back the rule or policy change and publish a correction.
- 🧒 Notices the guard suddenly saying "no" to lots of good questions, like a goalie blocking their own team.

### CA-5 — Policy governance (pre-deployment)
- **Watches:** a proposed policy against the current one.
- **Method:** `review(old, new)`. It checks full validation, including the protected-speech canary. It flags relaxed defaults (thresholds, cooldowns, judge settings, `unscreenable_content`, `screen_prompts`), issuer changes, catastrophic-backtracking-prone patterns, and rules that time out on stress inputs.
- **Alert codes:** `POLICY_INVALID`, `POLICY_RELAXATION`, `ISSUER_CHANGED`, `RISKY_PATTERN`, `RULE_TIMEOUT`.
- **Action:** reject the change, or send it to the adopting body for sign-off.
- 🧒 Checks new rules *before* they start, like Hermione reading the rulebook, and rejects the sneaky ones.

### CA-6 — Integrity auditor
- **Watches:** the audit hash chain, HMACs, sink failures and timestamps.
- **Method:** `verify_chain` with the audit key. It also counts sink failures and detects non-monotonic timestamps (clock skew).
- **Alert codes:** `AUDIT_CHAIN_BROKEN`, `AUDIT_SINK_FAILURES`, `AUDIT_CLOCK_SKEW`.
- **Action:** preserve the evidence, open an integrity incident, and restore from a replicated sink.
- 🧒 Makes sure no one erased or rewrote pages in the diary.

### CA-7 — Consent watch
- **Watches:** community-affecting decisions, and consent revocations.
- **Method:** it matches community actions to `consent_verified` events and tracks revocations against the 72-hour SLA.
- **Alert codes:** `CONSENT_UNVERIFIED`, `REVOCATION_DUE_SOON`, `REVOCATION_OVERDUE`.
- **Action:** pause the affected actions until consent is verified, and honour the revocation.
- 🧒 Reminds the AI when a permission slip is missing or a village has said "stop".

### CA-8 — Macro-policy detector
- **Watches:** approved completions that read like policy (the `policy_like` metadata) but were not submitted as macro-policy proposals.
- **Method:** count and share of policy-like approvals that skipped simulation.
- **Alert code:** `SIMULATION_SKIPPED`.
- **Action:** route these outputs through `is_macro_policy_proposal=True`, so the digital twin runs.
- 🧒 Spots when the AI is writing big "rules for the whole town" and makes sure they get a practice run in the simulator first, like a flight simulator before a real plane.

### CA-9 — Incident clerk
- **Watches:** confirmed Tier 3 decisions and `incident_reported` events.
- **Method:** it tracks the 15-day Art. 12 deadline for each incident and drafts the report (`draft()`).
- **Alert codes:** `INCIDENT_DUE_SOON`, `INCIDENT_OVERDUE`.
- **Action:** file the drafted report with the ICT.
- 🧒 Writes up what happened and reminds everyone the report is due in two weeks, like homework.

### CA-10 — Capability-atrophy sentinel *(guiding principle)*
- **Watches:** the scaffold ratio (K-23) per cohort, and human overrides (K-21).
- **Method:** a daily-series trend crossing of the lower K-23 band edge within a 30-day horizon, using a smoothed 3-day level. It is per cohort and never per person.
- **Alert code:** `SCAFFOLDING_DECLINING`.
- **Action:** enable scaffolding modes (hints, steps, questions back) for the cohort. The agent never blocks.
- 🧒 Notices when people stop pedalling and let the bike carry them, and says "time to take the training wheels off a bit" *before* they forget how to ride.

### CA-11 — Diversity / monoculture sentinel *(guiding principle)*
- **Watches:** refusal rates by language (K-25), and traffic share by language.
- **Method:** a worst-to-best disparity trend crossing the 1.25 target. It also detects silent exclusion: a language whose traffic share drops sharply after a `policy_change`.
- **Alert codes:** `REFUSAL_DISPARITY`, `SILENT_EXCLUSION`.
- **Action:** audit the rules and judge prompts for that language, and bring in native-speaker review.
- 🧒 Notices when the guard starts treating some kids unfairly, or when a group of kids quietly stops coming to the playground.

### CA-12 — Atrocity-precursor sentinel
- **Watches:** Tier 3 dehumanisation and worth-ranking hits (`HUMAN_WORTH_RANKING`, `JUSTIFICATION_LAUNDERING`), aggregated per tenant and target group.
- **Method:** it maps rule codes to Stanton stages (`STANTON_STAGE`: classification, symbolisation, discrimination, dehumanisation, organisation, polarisation, and so on). It alerts on stage escalation over time and on volume trends. It is **belief-neutral**: it targets the ranking of human worth and the licensing of harm, never belief itself. See [scenario_gaming.md](scenario_gaming.md).
- **Alert code:** `ATROCITY_PRECURSOR_ESCALATION`.
- **Action:** escalate to human trust-and-safety and to civil-society early-warning partners, and review the tenant's use case.
- 🧒 Like a smoke detector that beeps at the first wisp of smoke, not when the house is already on fire.

### CA-13 — Extraction watch
- **Watches:** `value_flow` and `capacity` events by region.
- **Method:** it computes the value-return ratio (K-27) per region and forecasts when it will fall below 1.0. It also flags a low local capacity share (K-28).
- **Alert codes:** `VALUE_RETURN_GAP`, `LOW_LOCAL_CAPACITY`.
- **Action:** *recommend* a benefit-sharing obligation to the ICT and the communities concerned. The agent never moves resources itself: binding obligations come through Act Art. 4(5).
- 🧒 A lookout who notices treasure leaving a village with nothing coming back, and tells the grown-ups before it becomes unfair.

## Demonstration

`python examples/accountability_demo.py` runs a simulated 30 days through the real guardrail and plants one scenario per agent. The test suite checks that every planted scenario fires, and that forecasting agents warn before their breach. The resulting public snapshot is `docs/dashboard/demo_snapshot.json`, rendered at `docs/dashboard/index.html`.

🧒 *We held a fire drill with pretend fires, and every lookout spotted its fire in time.*
