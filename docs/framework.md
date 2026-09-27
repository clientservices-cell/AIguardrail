# The Seed-First AI Governance Framework — v2

**Operationalising intergenerational relational ethics and ecosystem stewardship in artificial intelligence**

> Companion to the [Seed-First AI Act (draft v2)](seed_first_ai_act.md). The [research dossier](research_dossier.md) gives the formal model, and [`seed_first_guardrail`](../README.md) is the reference implementation. A summary of what changed from v1 is at the end.

## Executive Summary

Most AI governance still inherits the logic of the systems it governs. It optimises for immediate efficiency, short-horizon returns and individual preferences, and treats ecological damage, social fragmentation and loss of human capability as externalities. At planetary scale, that logic risks consuming the "seed corn" of civilisation: the capacities future generations need.

The **Seed-First model** replaces unconstrained optimisation with **intergenerational relational ethics**. Its sources:

- **Indigenous data sovereignty:** the CARE principles.
- **Ubuntu:** the African philosophy of personhood through relationship.
- **Nordic high-trust governance:** *tillit*.
- **Long-horizon stewardship institutions:** for example, Norway's Government Pension Fund Global and the Svalbard Global Seed Vault.

The model treats the preservation of future life-bearing capacity as a **hard constraint** on automated decision-making, not a preference to be weighed. That capacity spans human diversity, the welfare of women and children, community bonds, human agency and biosphere stability.

Two design commitments keep this from becoming a pretext for control:

1. **Individual dignity is the highest tier.** No ecological or collective goal can be pursued by violating it.
2. **The AI is a guardrail, not a governor.** It reports boundaries and refuses to cross them; humans and communities decide what to do.

---

## I. The Seed Axiom

### 1. Defining the seed

In agrarian practice the harvest feeds the present, but the seed belongs to the future. Eating the seed turns a renewable cycle into a countdown. In AI governance the "seed" has four interdependent pillars:

| Pillar | What it protects | Example of depletion by an AI system |
|---|---|---|
| **Demographic Seed** | Future generations: maternal health, child development, geographic, ethnic and genetic diversity | A resource-allocation model that cuts antenatal care in rural districts to meet a cost target |
| **Ecological Seed** | Earth-system processes within planetary boundaries; topsoil, water, climate, food webs | An optimiser that raises yield by over-pumping an aquifer |
| **Cultural and Epistemic Seed** | Indigenous and local knowledge, languages, community bonds, social trust (*tillit*), memory | A model trained on Indigenous language data without consent; a system that replaces neighbourly trust with surveillance |
| **Human Agency Seed** | The capacity of people and communities to deliberate, struggle, learn and adapt | A system that issues directives instead of options, so the skills of self-government erode |

### 2. Relational autonomy

A familiar framing sets radical individual autonomy against collective authority. Relational ethics rejects that choice. A person's agency and flourishing depend on the health of their community and ecosystem, and a community's legitimacy depends on respecting each person's dignity.

Written formally, individual flourishing depends on dignity, community health and biosphere stability. But the dependence must be **non-compensatory**: a surplus in one factor cannot make up for a deficit in another. A simple way to express this is a weakest-link (Leontief) form:

$$
\text{Flourishing}_i \;=\; \min\big(\text{Dignity}_i,\;\text{Health}_{\text{community}},\;\text{Stability}_{\text{biosphere}}\big)
$$

An additive or averaging form would let a system "buy" someone's dignity with ecological gains, or the reverse. That is the trade-off this framework forbids.

---

## II. The Three-Tier Governance Architecture

| Tier | Name | Role | Character |
|---|---|---|---|
| **1** | Planetary and Intergenerational Boundaries — *the Shell* | Hard limits on energy, emissions, water and resource burn, allocated as budgets | An enclosure on AI systems; never a manager of daily human life |
| **2** | Community and Relational Sovereignty — *the Context* | Communities set contextual cultural, economic and social rules, including CARE-based data governance | Plural and local; bounded above by Tier 1 and below by Tier 3 |
| **3** | Inviolable Individual Dignity — *the Floor* | Life, bodily and mental integrity, freedom from surveillance, coercion and forced labour, cognitive privacy, non-discrimination, children's rights | Non-negotiable. A proposed action that breaches it is halted, not traded off |

**Precedence:** Tier 3 > Tier 1 > Tier 2.

- **Why Tier 3 sits above Tier 1:** otherwise ecological goals could justify coercion ("eco-tyranny").
- **Why Tier 1 sits above Tier 2:** otherwise one community could spend the shared planetary budget.
- **When no option satisfies all three tiers:** the system does not pick the least-bad breach. It abstains and escalates to accountable human deliberation.

**Tier 1** monitors aggregate ecological indicators and translates planetary boundaries into Resource Budgets for AI providers and deployers. Allocation follows an equity-sensitive method that accounts for historical responsibility and development needs.

**Tier 2** delegates contextual decisions to communities through recognised, open and inclusive bodies. Communities decide how their budgets are used and how their data and knowledge may be used. This protects **cognitive sovereignty**: the right of communities to govern the interpretive logic applied to them.

**Tier 3** is a set of hard constraints. In optimisation terms, basic rights are not "zero-cost variables", as the v1 text put it. They are **constraints with no finite price**: they define the feasible set, and no amount of benefit elsewhere buys a violation.

---

## III. Paradigm Comparison

| Dimension | Extractive market model | Authoritarian collectivist model | Relational "Seed-First" model |
|---|---|---|---|
| Primary target | 90-day financial return and engagement | State compliance and macro-order | Intergenerational vitality and ecological continuity |
| Treatment of the individual | Consumer; data-extraction point | Resource; replaceable unit | Relational agent with inviolable dignity |
| View of the ecosystem | Externality; sink | Production input | Living foundation, held in trust |
| Handling of struggle | Engineered away through convenience | Imposed through forced sacrifice | Buffered: real challenge, with guaranteed recovery |
| Social trust mechanism | Monetised verification and contracts | Pervasive surveillance and enforcement | Preserved human-to-human reliance (*tillit*) |
| Geographic diversity | Monocultural data dominance | Centralised standardisation | Multi-nodal epistemic and cultural sovereignty |
| Role of AI | Maximiser | Controller | Guardrail and boundary indicator |

---

## IV. Institutional Mechanics: Beyond the Short-Term Trap

The core driver of ecological and social depletion is not ownership as such. It is **short-horizon control metrics**, such as the quarterly earnings cycle, and objective functions that give no weight to harm beyond their horizon.

- **Extractive cycle:** short-term pressure → seed stock stripped → systemic fragility.
- **Stewardship cycle:** long-horizon control → seed stock protected and reinvested → sustained vitality.

### 1. The Norwegian paradigm applied to algorithmic capital

Norway's Government Pension Fund Global is useful less as a "sovereign wealth fund" than as a set of institutional firewalls:

- a **fiscal rule** that limits annual spending to roughly the fund's expected real return, protecting the capital for future generations;
- a transparent **ethical exclusion process**, in which an independent Council on Ethics publishes its recommendations; and
- **operational independence** under democratic accountability.

AI governance needs an equivalent **Intergenerational Control Trust (ICT)**, with:

- **Algorithmic circuit breakers:** code-level locks that halt trading, extraction or labour-allocation algorithms when they breach long-term ecological or human thresholds. They are triggered by the *system's own* violations and reviewable by courts.
- **Decoupling control from yield:** executive and algorithmic reward functions anchored to multi-decade horizons (20–50 years), with explicit weight on harms beyond any evaluation window.
- **Accountability:** transparent appointments, fixed terms, published decisions, legislative reporting and judicial review. Independence from electoral cycles must never mean independence from law.

### 2. Adaptation with human safety buffers

Biological evolution adapts through trial, error and elimination. Humane governance must separate adaptation from destruction:

- **Silicon Simulation Mandate:** complex policies are tested in simulation before deployment, "so that ideas die in simulation and people do not die in reality". A policy passes only if its **worst case** for the most affected group stays above a welfare floor; a good average is not enough.
- **Simulation is necessary, not sufficient.** Models are simplifications, so a simulated pass leads to a consented, time-limited pilot with a recovery fund and a rollback criterion. Wider roll-out comes only after that, under continued monitoring.
- **Failure shock-absorbers:** when a real-world pilot fails, structural aid absorbs the loss, so communities can learn and pivot without existential harm.

---

## V. Structural Safeguards Against Authoritarian Escalation

Five hard-coded safeguards keep the Seed-First model from degenerating into ecological or communal tyranny:

1. **Constraint, not command.** The AI reports boundaries (for example, "water basin drawdown is at 88 %") and leaves solutions to human deliberation.
2. **Non-tradeable human floors.** Basic rights define the feasible set; they are never harvested for systemic balance.
3. **Federated, polycentric architecture.** No single global model holds unified control. Regional nodes operate independently, with local overrides and cross-regional negotiation.
4. **Dissent as evolutionary signal.** Non-violent dissent and social experimentation are treated as indicators of adaptation. AI is never used to identify or suppress them.
5. **No tyranny of the local.** Community (Tier 2) authority cannot be used to impose Tier 3 violations on a community's own members, including minorities and dissenters.

---

## VI. Policy Recommendations for Global Implementation

1. **Codify cognitive and epistemic sovereignty.** International AI standards should guarantee that communities, particularly in the Global South, retain legal control over the data and algorithmic logic applied to their territories, including FPIC and benefit-sharing for Indigenous data and knowledge.
2. **Outlaw unbuffered high-frequency extraction.** Regulate capital-market and extraction AI to end routines that trade multi-generational stability for short-horizon profit.
3. **Establish demographic and geographic safeguard councils.** Global AI oversight bodies should reserve permanent seats for women, Indigenous stewards and regions historically subjected to extractive development. These seats carry a suspensive veto over decisions that specifically affect those communities, with a transparent override procedure.
4. **Mandate Seed-First impact assessments.** Frontier AI deployments should pass an intergenerational audit covering all four pillars, integrated with existing rights and sustainability assessments rather than duplicating them.
5. **Make compliance machine-readable.** Express budgets, community rules and floors in an open policy schema, so that compliance can be checked by code and verified independently. The `seed_first_guardrail` package is an open reference implementation.

---

## What Changed from v1

- **Rights are not "zero-cost variables".** A zero cost would mean trading them away is free. They are now described as constraints with no finite price, which is what the text meant.
- **The flourishing function is non-compensatory.** A generic $f(\cdot)$ would permit trade-offs between dignity and ecology.
- **The Human Agency Seed is now consistent with the Act,** which previously listed only three pillars.
- **"Absolute social trust" is softened to "social trust (*tillit*)".** No real society has absolute trust, and the claim is not needed.
- **The Norway reference is corrected** from "Sovereign Wealth Fund" to the Government Pension Fund Global. The mechanisms that make it relevant (the fiscal rule and the ethics council) are now stated.
- **Tier precedence and the abstain-and-escalate rule are now explicit.**
- **Two safeguards are added:** "no tyranny of the local", and circuit breakers triggered only by the system's own violations.
- **The simulation mandate is qualified.** Simulation is necessary but not sufficient, and the criterion is worst-case, not average.
- **"Veto-empowered seats" is defined** as a suspensive veto with an override procedure, so a single seat cannot block all governance.
