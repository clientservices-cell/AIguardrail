# Scope — seed-first-guardrail as an instrument of supervision

*Draft v1, 19 October 2026. Companion to the [Seed-First AI Act, draft v3.1](docs/seed_first_ai_act.md), Chapter VIA.*

## What this is

seed-first-guardrail is an instrument of supervision for deployed AI systems: a deployer-side enforcement and reporting layer that wraps model calls in hard constraints, records every decision in a tamper-evident chain, publishes paired indicators and graded scorecards, and gives anyone refused a way to contest it. It is built so that an independent supervisor — a conformity-assessment body, an industry standards council, a regulator, or an audit committee — can examine what a deployer's AI did against a written policy, the way a bank examiner reads a call report. It is not the supervisor. Supervision needs an institution with authority and an instrument it can rely on; this project builds the instrument and says plainly where the institution has to come from.

🧒 **In plain words:** a referee needs a rulebook, a whistle and a scoreboard everyone can see. We are building the whistle and the scoreboard. Someone with the power to stop the game still has to be the referee.

## What this is not

- **Not a frontier-safety policy.** It does not see training runs, model weights, capability evaluations or a developer's decision to build or release a model. Those belong to the developer's own policy (Anthropic's Responsible Scaling Policy is the most developed public example) and, in time, to law. Nothing here substitutes for either.
- **Not a regulator.** It has no authority over anyone. A deployer who adopts it is bound by their own policy file and by whoever they answer to — a customer, an assessor, a supervisor — not by this project.
- **Not a guarantee.** The lexical rules are a floor. The published error rates are measured on specific corpora under specific configurations, and `docs/evaluation.md` says which. A guardrail that claims to catch everything is lying; this one says what it caught and what it missed.
- **Not a replacement for first-party safeguards.** Model providers ship their own classifiers and moderation endpoints. This layer uses them as evaluators where available; what it adds is the part they do not give you — policy as versioned code, an audit chain that spans providers, paired public indicators, and a contest path.
- **Not a worldview you must adopt.** The Seed-First AI Act's planetary and community tiers are optional policy profiles. The `core` profile — the human-dignity floor, the audit chain, the circuit breaker, the contest path and the indicator layer — installs without them.

## Institution and instrument

Every mature supervisory regime has two parts: an institution with authority, independence, funding and examiners, and a set of instruments — standardized reports, shared rails, ratings and examinations — that the institution runs on. The instruments are not the regime, but a regime without them is a press release. Banking took a century to build both. AI supervision has, so far, a few voluntary policies and no instruments that work across developers. This project builds the instruments first, on the pattern of five precedents.

| Precedent | What it is | Where its authority comes from | What it shows us |
| --- | --- | --- | --- |
| **Federal Reserve System** (reference) | Central bank and supervisor of bank holding companies and state member banks, 1913. A public Board of Governors over twelve regional Reserve Banks whose stock is held by their member banks. Funded by its own operations, not appropriations. | Statute (Federal Reserve Act). | The shape: public governance over an industry-owned structure. The instruments: standardized periodic reports, examiner-assigned ratings (CAMELS), supervisor-designed stress tests, and shared rails (Fedwire) every member transacts through. Also the limit: it missed 2008 and 2023; supervision reduces risk, it does not abolish it. |
| **FINRA** | Self-regulatory organization for US broker-dealers, 2007. Writes rules, examines members, fines and bars. | Industry-created, under statutory oversight by the SEC, which approves its rules. Funded by member fees. | A self-regulatory body with teeth is possible when a public authority stands behind it. The AI version would be an industry body whose rules a regulator approves. |
| **PCI Security Standards Council** | Publishes the PCI DSS for anyone handling card data, 2006. Assessments done by Qualified Security Assessors the Council certifies. | No statute. Created by the card networks; enforced by contract through acquirers and merchants. | Compliance can be the price of market access without a law. The AI analogue: a standard that model providers and cloud platforms require of deployers by contract, with certified assessors. |
| **NCUA** | Independent federal agency that charters, supervises and insures federal credit unions, 1970 (chartering from 1934). Funded by operating fees on the institutions it supervises and by the share-insurance fund. Every federal credit union must have a Supervisory Committee independent of management. | Statute (Federal Credit Union Act). | A sector can get its own supervisor built for its structure. And the internal check — an independent committee that audits, verifies accounts and reports to members — is itself a required instrument, not an optional one. |
| **EU AI Act notified bodies** | Under Regulation (EU) 2024/1689, high-risk AI systems undergo conformity assessment; member states designate independent notified bodies to perform it; the AI Office oversees general-purpose models. Obligations phase in through 2026–2027. | Statute (EU regulation), with assessment by designated independent bodies. | The first live regime where an independent assessor needs tooling to examine a deployed AI system against written requirements — Article 9 risk management, Article 12 record-keeping, Article 14 human oversight, Article 15 accuracy and robustness. This is the nearest real customer for an instrument of supervision. |

The Federal Reserve is the reference because it is the fullest version; the four below it are the achievable ones. Each shows a different source of authority — statute, statute-backed self-regulation, contract, and designated assessment — and the instrument has to work under any of them.

## What the instrument provides

Five things a supervisor needs from the supervised, each with its banking analogue and the module that delivers it.

| Supervisory function | Banking analogue | What this project provides | Module |
| --- | --- | --- | --- |
| **Standardized periodic reporting** | The call report: same fields, same schedule, filed by every institution, comparable across them | The KPI snapshot (`kpi_snapshot.schema.json`) and the conformance statement: version, policy hash, tiers and judges on, measured rates for that configuration, date of last red-team run. Same schema for every deployer, so an examiner can compare. | `accountability.snapshot`, `accountability.kpis`, the conformance template (1.0) |
| **A shared rail that cannot be quietly rewritten** | Fedwire and the general ledger: every transaction passes through, and the record is the record | The audit chain: every decision written to a pluggable sink as a keyed digest in a hash chain, no text stored by default, tampering detectable. Spans providers, so the record does not depend on any one vendor. | `audit.py` |
| **Ratings assigned by a method, not by the rated** | CAMELS: a grade an examiner assigns from evidence | Model scorecards graded A–F from paired indicators — harm stopped beside struggle kept, so a system cannot look safe by refusing everything or helpful by doing everything. Today the deployer runs the method; the method is public so an assessor can run it instead. | `accountability.scorecards`, `accountability.kpis` |
| **Examination on the examiner's terms** | Stress tests designed by the supervisor, not the bank | The red-team harness (0.3): any corpus, including one the examiner brings, replayed through the real middleware with rates and intervals by rule family and source. The project's own corpora are published with provenance; an examiner's are not required to be. | `seed-first redteam`, `tests/redteam/` |
| **A way to contest a decision** | Member complaints to the Supervisory Committee; appeal of an examination finding | `contest_ref` on every refusal, a contest record with resolver and state, and a paired KPI (contest rate / overturn rate) so neither "never overturned" nor "always overturned" reads as good. | `contest` CLI and API (0.4) |

Two things the table does not include, because they are the institution's and not the instrument's: the rules themselves, and the power to act on a finding. The Seed-First AI Act is one proposed rulebook; the policy schema accepts others. What the software enforces is whatever policy file it is given, and it records that it did.

## What it requires from others

An instrument without an institution is a dashboard nobody has to look at. Four things have to come from outside this project, and the precedents show where each can come from.

| Requirement | Why the software cannot supply it | Where it can come from |
| --- | --- | --- |
| **Authority** — the power to require reporting and to act on a finding | Code enforces a policy on the caller who installed it; it cannot compel anyone else | Statute (the Fed, NCUA, EU AI Act); statute-backed self-regulation (FINRA); or contract — model providers and cloud platforms requiring it of deployers as a condition of access (PCI) |
| **Independence** — governance no supervised party controls | A project whose author is its only authority is the RSP's weakness in miniature | A standards council with public-interest governors over industry members (the Reserve Bank structure); for this project now, the two-person rule and external approver in `GOVERNANCE.md` (0.4) |
| **Funding** — steady, not grant-by-grant | Volunteer maintenance ends | Assessments on the supervised (OCC, FDIC, NCUA, FINRA all fund themselves this way); for this project now, a funder of open infrastructure and, at 1.0, pilot deployers who pay for conformance support |
| **Examiners** — people with the power to look and the duty to report | No software replaces a person who reads the record and says what is wrong | Certified assessors (PCI's QSAs, EU notified bodies, ISO/IEC 42001 certification bodies); internal supervisory committees (NCUA); for this project now, the external reviewers invited in `REVIEWING.md` |

The honest sequence is the banking one. The instruments existed before the institutions were complete: ledgers, clearing houses and audit before central banks and deposit insurance. Building a usable instrument is how you earn a seat when the institution is designed — and how you make sure the institution, when it comes, has something to run on.

## Who it is for, and the path

**Now (0.2–0.3):** deployers who want a written policy enforced and a record they could hand to an auditor; researchers who want a red-team harness that reports rates with intervals; reviewers who want something concrete to criticize.

**From 0.4:** compliance teams who need to show an assessor that an AI system's risk management, logging, human oversight and robustness controls exist and ran — the crosswalks map each module to NIST AI RMF, ISO/IEC 42001 Annex A and EU AI Act Articles 9, 12, 14 and 15.

**At 1.0:** assessors and notified bodies who need an instrument to examine a deployer with; internal supervisory functions — audit committees, risk committees, the AI equivalent of a credit union's Supervisory Committee — who need the same record from inside; and any future industry council or regulator designing the institution, who should find the reporting format, the rail, the rating method and the examination harness already built, tested and public.

The path is the release plan: measure (0.3), govern (0.4), harden (0.5), position (1.0). Each release moves one requirement from the table above partly inside the project — independence through governance, examiners through review, funding through pilots — while being clear that the full version of each lives outside it.

## Commitments and limits

We commit to the following, and they are testable:

1. **No claim without a measurement.** Every rate in the README appears in `docs/evaluation.md` with its corpus, configuration, date and interval; a test fails the build otherwise.
2. **Every indicator has a counter-indicator.** Harm stopped is published beside struggle kept; over-blocking is a red, not a virtue.
3. **The floor cannot be switched off by a policy file.** Tier 3 is fixed in the schema, and a policy that tries to relax it is rejected at load.
4. **The record is tamper-evident and private by default.** Digests, not text; a chain, not a log.
5. **Reviews are published unredacted with a dated response.** Including the ones we disagree with.
6. **Changes to the floor need a second signature** from someone outside the project (0.4).

And we state the following limits, which are the reasons an institution is still needed:

- We see the call, not the model. Capability thresholds, training and weights are outside our view.
- Our rates are only as good as the corpora they are measured on, and until 0.3 those corpora are our own.
- We have no power over anyone who does not install us, and none to act on what we record beyond refusing a call and writing it down.
- A referee who misses a foul does not make the foul legal. Nothing here is legal advice, and nothing here is a warranty; see `NOTICE`.

🧒 We promise to tell the truth about what we caught and what we missed, to write it where everyone can read it, and to let other people check our work. We do not promise to catch everything, because nobody can.

## Sources

- Federal Reserve System: [Federal Reserve Act](https://www.federalreserve.gov/aboutthefed/fract.htm); [Structure of the Federal Reserve System](https://www.federalreserve.gov/aboutthefed/structure-federal-reserve-system.htm); [Supervision and regulation](https://www.federalreserve.gov/supervisionreg.htm)
- FINRA: [About FINRA](https://www.finra.org/about); SEC oversight under the Securities Exchange Act of 1934, Section 15A
- PCI Security Standards Council: [About the Council](https://www.pcisecuritystandards.org/about_us/); [Qualified Security Assessors](https://www.pcisecuritystandards.org/assessors_and_solutions/qualified_security_assessors)
- NCUA: [About NCUA](https://ncua.gov/about); [Supervisory Committee Guide for Federal Credit Unions](https://ncua.gov/regulation-supervision/manuals-guides/supervisory-committee-guide-federal-credit-unions)
- EU AI Act: [Regulation (EU) 2024/1689](https://eur-lex.europa.eu/eli/reg/2024/1689/oj) — Articles 9, 12, 14, 15; notified bodies (Chapter III, Section 4); the AI Office
- Anthropic: [Responsible Scaling Policy](https://anthropic.com/rsp), v3.4
- This project: `README.md`, `docs/architecture.md`, `docs/adversarial_review.md`, `docs/accountability_kpis.md`, and the release roadmap in the README

*Verify the institutional facts against the linked primary pages before this file ships; dates and structures are stated from general knowledge and should carry a `reviewed_by` line like the crosswalks.*
