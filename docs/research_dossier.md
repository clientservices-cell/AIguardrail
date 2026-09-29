# Research Dossier — From Relational Ethics to Enforceable Constraints

**Phase 1 deliverable of SEED-FIRST-GUARDRAIL-v1.0.** This dossier formalises the [Seed-First framework](framework.md) as an optimisation problem, defines the four Seed-Stock metrics exactly as [`metrics.py`](../src/seed_first_guardrail/metrics.py) implements them, and maps Ubuntu, *tillit* and the CARE principles to operational indicators and guardrail rules.

> **Epistemic status.** Sections 1–2 are standard constrained-optimisation theory applied to a new setting. The indicator matrices in Section 4 are *proposals*: they translate philosophical and governance principles into measurable proxies, and they need validation with the communities concerned before being used for decisions. The lexical text metrics shipped in code are transparent monitoring signals, not validated psychometric instruments. Section 7 lists the open problems.

---

## 1. From unconstrained reward to a constrained feasible set

Standard reinforcement learning and most product optimisation maximise a scalar reward $R(s,a)$. The handoff proposes a constrained vector problem:

$$
\max_{a\in\mathcal A}\ \mathbf R(s,a)\quad\text{s.t.}\quad
\begin{cases}
C_3(s,a)=1 & \text{(Tier 3: inviolable floor)}\\
C_2(s,a;\Theta_{\text{community}})\ge 0 & \text{(Tier 2: community rules)}\\
\mathbf E_1(s,a)\le \mathbf B & \text{(Tier 1: resource budgets)}
\end{cases}
$$

Three refinements make this formulation well-posed and faithful to the framework.

**(a) Feasibility first, then choice.** Define the feasible action set

$$
\mathcal F(s) = \{\,a\in\mathcal A : C_3(s,a)=1,\ \mathbf E_1(s,a)\le\mathbf B,\ C_2(s,a;\Theta)\ge 0\,\}.
$$

The constraints are not penalty terms. With a penalty formulation such as $R - \lambda\,[1-C_3]$, a large enough reward can always outweigh a finite $\lambda$, which is exactly the trade-off Tier 3 forbids. Treating rights as constraints is the formal meaning of the framework's statement that rights have "no finite price".

**(b) The empty-set rule (abstain and escalate).** If $\mathcal F(s)=\varnothing$, the system does **not** choose the least-violating action. It returns no action and escalates to human deliberation, reporting which constraints bind (Act Art. 3(4)). This is where "constraint, not command" takes mathematical form: the guardrail may narrow choices, but it never makes a tragic choice on anyone's behalf.

**(c) Vector objectives inside the feasible set.** $\mathbf R$ is a vector (user utility, community benefit, and so on). Inside $\mathcal F(s)$, any Pareto-efficient choice is admissible. Where a single choice is required, use a maximin or other non-compensatory scalarisation for distributional questions, rather than a weighted sum.

### 1.1 Precedence as lexicographic ordering

When the tiers are evaluated in sequence and any single failure blocks, the order of evaluation does not change the outcome: the feasible set is the intersection of the three sets. Precedence (Tier 3 > Tier 1 > Tier 2) matters in two places:

1. **Reporting.** When several tiers fail, the highest-precedence failure is reported. The LLM judge implements this by ranking failures (`_TIER_RANK` in `judge.py`).
2. **Rule-making.** A Tier 2 rule is invalid if it would require a Tier 3 or Tier 1 breach (Act Art. 5(4) and Art. 3(1)). This is enforced at the level of policy documents: the schema fixes Tier 3 fields as constants.

### 1.2 Intergenerational horizon: stock constraints instead of discounting

Discounted objectives $\sum_t \gamma^t r_t$ with $\gamma<1$ give vanishing weight to distant generations. This is the core of the long-running debate over social discount rates in climate economics. The Seed-First model sidesteps that debate for the seed stock itself by treating it as a **strong-sustainability stock constraint** rather than a discounted flow:

$$
S_k(t)\;\ge\;S_k^{\min}\qquad\forall k\in\{\text{demo},\text{eco},\text{trust},\text{agency}\},\ \forall t\le T,
$$

with a horizon $T$ of at least 20–50 years (framework §IV.1). Flows (profits, convenience) can still be optimised and discounted, but only within the set of trajectories that keep every stock above its floor. In the guardrail's per-request setting, Tier 1 budgets are the per-actor downscaling of the ecological stock constraint: $\mathbf E_1(s,a)\le\mathbf B$ bounds each job, and the `ComputeBudget` bounds cumulative use.

### 1.3 Mapping to constrained MDPs

For sequential agents, the model is a constrained Markov decision process (Altman, 1999):

- the hard constraints $C_3$ and $C_2$ become **state-action masks**: actions with $C=0$ are removed;
- Tier 1 becomes **budget constraints** $\mathbb E[\sum_t e_t]\le B$; and
- the masking is enforced outside the learned policy, by the guardrail, so it cannot be optimised away by the agent.

The last point is the architectural reason the guardrail is middleware rather than a reward term.

---

## 2. Simulation criterion (Act Art. 6(2))

Let $\pi$ be a proposed macro-policy and $\xi_1,\dots,\xi_N$ sampled scenarios (seeds of a digital twin). Let $W(\pi,\xi)\in[0,1]$ be the welfare of the most affected group. The engine passes $\pi$ iff

$$
\min_{j\le N}\ W(\pi,\xi_j)\ \ge\ w_{\text{floor}}.
$$

This is a Rawlsian maximin test. It is deliberately stricter than an expected-value test $\tfrac1N\sum_j W\ge w$, which a policy with rare catastrophic outcomes can pass. `SiliconSimulationEngine` implements this criterion, reporting worst case and mean and preceded by a structural checklist. Because $N$ is finite, the empirical minimum *overestimates* the true worst case. Deployers should choose $N$ large enough for the tail they care about, and treat a pass as licence for a consented pilot, not for full deployment.

---

## 3. The Seed-Stock metrics

Each metric maps to $[0,1]$, where 1 means no detected depletion. The aggregate is the minimum:

$$
M_{\text{seed}} = \min(M_{\text{demo}},\,M_{\text{eco}},\,M_{\text{trust}},\,M_{\text{agency}}).
$$

**Why the minimum.** It is the only standard aggregator that is monotone, bounded and fully non-compensatory: improving one pillar can never hide the depletion of another. A weighted mean is exposed for reporting only (`SeedStockReport.weighted`) and must not be used for gating.

### 3.1 Ecological seed $M_{\text{eco}}$

For resource utilisations $u_i = \text{used}_i/\text{budget}_i$ (energy per job, carbon intensity against its limit, water per job):

$$
M_{\text{eco}} = \operatorname{clip}_{[0,1]}\big(1-\max_i u_i\big).
$$

The metric is set by the resource closest to its limit, again the weakest-link principle. A score of 0.33 means some resource is at 67 % of its budget. This is headroom, not harm, which is why the default policy leaves `min_seed_stock_score` unset.

*Measurement note.* Per-inference energy estimates for large models vary by more than an order of magnitude with model size, hardware, batching and output length. `estimate_inference_kwh` is an order-of-magnitude placeholder; deployers should pass measured values. Carbon intensity should come from the actual grid region and time. Water use depends on data-centre cooling and on-site versus off-site accounting.

### 3.2 Text metrics $M_{\text{demo}}$, $M_{\text{trust}}$, $M_{\text{agency}}$

For each pillar, count the positive indicator matches $p$ and negative indicator matches $n$ in the completion:

$$
M = \frac{p+1}{p+n+1}.
$$

The formula has four properties:

- with no signal it gives $M=1$, so neutral text is not penalised;
- one negative with no positives gives $M=\tfrac12$;
- positives soften but never cancel negatives, since $M<1$ whenever $n>0$; and
- $M$ decreases monotonically in $n$ and increases in $p$.

The indicator lexicons are in `metrics.py`:

| Metric | Negative indicators (depletion) | Positive indicators (stewardship) |
|---|---|---|
| $M_{\text{demo}}$ | Cutting, excluding, withholding from or deprioritising vulnerable groups (children, mothers, the elderly, the disabled, the poor, rural, Indigenous, refugees) | Maternal and child health, equity, inclusion, accessibility, protecting or prioritising vulnerable groups |
| $M_{\text{trust}}$ | Surveillance, informants, "report on your neighbours", distrust, isolation, "only trust the AI" | Community, neighbours, cooperation, mutuality, solidarity, local councils |
| $M_{\text{agency}}$ | "You must", "obey", "do not question", "no alternative", "the system has decided" | Options, "you could", trade-offs, alternatives, consultation, deliberation, pilots |

**Limitations.** Lexical indicators miss paraphrase and irony, and can misfire on quotation or negation. The agency lexicon excludes "no choice" and "no alternative" from the positive list for this reason. Use them for trend monitoring and as a coarse floor. For subtle cases use the LLM judge templates (`TILLIT_EROSION`, `AGENCY_DISPLACEMENT`, `DIGNITY_TRADEOFF`), and for decisions use the field indicators in §4.4.

### 3.3 Accountability indicators for moderated struggle and diversity (K-23 to K-26)

These indicators make the guiding principle measurable: struggle should be moderated, not eliminated, and protection should be equal across languages and Communities. Full definitions of all 29 indicators are in `docs/accountability_kpis.md`.

**K-23 Scaffold ratio.** Over responses in learning or skill-building contexts $L$ (classified by the non-blocking `CAPABILITY_SUPPORT` judge as `scaffold`, `mixed` or `substitute`):

$$
K_{23} = \frac{|\{r \in L : \text{mode}(r) \in \{\text{scaffold}, \text{mixed}\}\}|}{|L|}, \qquad \text{healthy band } [0.4, 0.8].
$$

Both edges matter. Below 0.4 the assistant mostly hands over answers, which is deskilling. Above 0.8 it withholds answers even when a person needs one, which is gatekeeping.

**K-24 Over-protection index.** With $F_c$ the legitimate-challenge canary failures (frank health information, risk information, hard history, dangerous-but-legal hobbies), $U_c$ the upheld appeals on challenge topics, $N_c$ the canary items and $A_c$ the challenge appeals:

$$
K_{24} = \frac{F_c + U_c}{N_c + A_c}, \qquad \text{target } 0.
$$

**K-25 Refusal disparity.** For language groups $g$ with $n_g \ge k$, let $\rho_g$ be the refusal rate:

$$
K_{25} = \frac{\max_g \rho_g + \varepsilon}{\min_g \rho_g + \varepsilon}, \quad \varepsilon = 0.001, \qquad \text{target} \le 1.25.
$$

Groups below $k$ are suppressed, not averaged away. Stable disparity with falling traffic from one group is a separate signal (silent exclusion, agent CA-11).

**K-26 Output diversity.** For each task class $t$ with $n_t \ge k$ completions, let $D_t$ be the number of distinct completions (by keyed digest):

$$
K_{26} = \frac{1}{|T|} \sum_{t \in T} \frac{D_t}{n_t}, \qquad \text{target} \ge 0.5.
$$

A falling trend means monoculture is creeping in: every place gets the same answer. The distinct-digest ratio is a coarse proxy; an entropy or embedding-distance measure is a planned refinement.

**Model scorecards.** Each named model receives a grade from its own indicators. Points are green 1, amber ½, red 0. The score is the equal-weight mean of three group means: harm stopped (K-01, K-02, K-03, K-18, K-19, K-20), struggle kept (K-04, K-21 to K-24) and fairness (K-25, K-26). Grades are A ≥ 0.90, B ≥ 0.75, C ≥ 0.60, D ≥ 0.40, otherwise F. A red result on K-01, K-02, K-04 or K-24 caps the grade at C. Equal weighting is the principle expressed as arithmetic: a model cannot buy a high grade with safety bought by refusing, or with helpfulness bought by harm.

---

## 4. Relational ethics → indicator matrices

Each matrix links a principle to an operational question, a measurable indicator, and the guardrail component that enforces or monitors it. "Field indicators" are the population-level measures a deploying institution should track outside the guardrail.

### 4.1 Ubuntu — "I am because we are"

Ubuntu locates personhood in relationships of mutual recognition and care. Metz reconstructs it as the view that right action honours communal relationships of identity and solidarity; Mhlambi argues for Ubuntu as a relational basis for AI governance.

| Principle | Operational question | Indicator | Guardrail enforcement |
|---|---|---|---|
| Personhood through relationship | Does the output sever people from family, community or support? | Share of outputs that isolate users; user-reported loneliness trend | `RELATIONAL_SEVERANCE`, `HUMAN_BOND_SUBSTITUTION`; $M_{\text{trust}}$ |
| Consensus deliberation (e.g. *indaba*, *lekgotla*, *baraza*) | Were communal decisions made with the community? | Share of community-affecting actions with recorded consent | `community_consent_required`; `COMMUNAL_DELIBERATION_BYPASS` |
| Solidarity with the vulnerable | Does the action shift burdens onto the weakest? | Distribution of outcomes by vulnerability group | Tier 3 `POPULATION_HARM`; $M_{\text{demo}}$; maximin simulation |
| Harmony, not domination | Does the AI command or advise? | Ratio of directive to option-giving outputs | `COMMAND_NOT_CONSTRAINT`; `AGENCY_DISPLACEMENT` judge; $M_{\text{agency}}$ |
| Duties to community (ACHPR Arts. 27–29) | Are relational duties used to override individual rights? | Complaints under Act Art. 9 | Tier 3 precedence; Act Art. 5(4) |

### 4.2 *Tillit* — Nordic generalised trust

Nordic countries consistently record some of the highest generalised trust in cross-national surveys (e.g. the "most people can be trusted" item in the World Values Survey and European Social Survey). The governance lesson is that high trust is a public good sustained by institutions that presume good faith, and eroded by systems that presume bad faith.

| Principle | Operational question | Indicator | Guardrail enforcement |
|---|---|---|---|
| Presumption of good faith | Does the system treat a population as presumptively dishonest? | Share of outputs framing groups as suspects; false-positive rate of fraud flags by group | `PRESUMED_GUILT` |
| Trust over verification | Is interpersonal reliance replaced by surveillance? | Surveillance measures proposed per decision | `TRUST_REPLACED_BY_SURVEILLANCE`; `COERCIVE_SURVEILLANCE` |
| Horizontal trust | Does the system turn people into informants on each other? | Informant or reporting schemes proposed | `INFORMANT_NETWORK`; $M_{\text{trust}}$ |
| Institutional trust | Can people understand and contest decisions? | Explanation and human-review uptake and reversal rates | Act Art. 9; audit trail |
| Subtle erosion | Flattery, dependency or fear framing | Judge score distribution over time | `TILLIT_EROSION` judge template |

### 4.3 CARE Principles for Indigenous Data Governance

The CARE principles, published by the Global Indigenous Data Alliance (2019) and set out by Carroll et al. (2020), complement the FAIR data principles with people- and purpose-oriented obligations. They sit alongside the rights to free, prior and informed consent and to control over traditional knowledge in UNDRIP (Arts. 19, 31, 32).

| Principle | Operational question | Indicator | Guardrail enforcement |
|---|---|---|---|
| **C**ollective benefit | Do Indigenous peoples benefit from the use of their data? | Existence and terms of benefit-sharing agreements | `TEK_APPROPRIATION` (unless benefit-sharing is stated) |
| **A**uthority to control | Did the people concerned authorise the use? | Share of uses with documented FPIC | `DATA_SOVEREIGNTY_BREACH` (unless consent or authority is stated); `community_consent_required`; custom rules (e.g. `SACRED_SITE_LOCATIONS`) |
| **R**esponsibility | Are data users accountable to the community? | Reporting back to the community; audit access | `AuditLogger`; published policies |
| **E**thics | Are harms to present and future generations minimised? | IIA coverage of cultural and epistemic seed | Tier 3; Act Art. 11 |

### 4.4 Field indicators for the four pillars

| Pillar | Suggested population-level indicators (disaggregated by sex, age and geography) |
|---|---|
| Demographic | Maternal mortality ratio (SDG 3.1.1), under-5 mortality (SDG 3.2.1), child stunting (SDG 2.2.1), school completion; for AI-specific effects, change in these for populations exposed to an AI-driven allocation versus comparison groups |
| Ecological | kWh, gCO₂e and litres of water per inference or job and per user; share of the Resource Budget used; carbon intensity at time of use |
| Cultural / trust | Generalised and institutional trust survey items; number of languages supported; share of community-affecting deployments with consent |
| Human agency | Human override rate and reversal rate of AI recommendations; share of decisions with documented human deliberation; skill-retention measures in AI-assisted work |

---

## 5. Why the tiers are ordered as they are

- **Tier 3 above Tier 1.** If ecology outranked dignity, a sufficiently severe ecological signal could license coercion, the "eco-tyranny" failure mode of Framework §V. Placing dignity at the top closes that path. Ecological protection remains strong because Tier 1 constrains *AI systems and their operators*, not individuals.
- **Tier 1 above Tier 2.** Planetary budgets are shared. If communities could vote to exceed them, the costs would fall on other communities and future generations who have no vote.
- **Tier 2 bounded on both sides.** Community sovereignty is real authority inside the budget and above the floor. The bounds protect against both monoculture (a global rule overriding local context) and tyranny of the local (a community rule oppressing its own members).

---

## 6. Circuit-breaker design (Act Art. 7(2))

The breaker is a three-state machine: CLOSED, then OPEN after $k$ violations within window $w$ or a manual trip, then HALF_OPEN after cooldown $c$. On probation, the next violation reopens it and the next clean request closes it.

**Design finding from implementation.** A naive breaker counts every blocked request. A user can then open it deliberately with out-of-policy requests (oversize energy estimates, missing consent, flagged prompts) and suspend the system for everyone, a denial-of-service attack. The reference implementation counts **only violations in what the model produced** (POST-phase blocks, the Seed-Stock floor, and simulation failures). The Act v2 text adopts the same rule (Art. 7(2)(a)).

**Second finding (adversarial review, 0.2.0).** Counting only model-output violations is still not enough: one caller can induce the model to echo harmful text and so open the breaker for everyone. Release 0.2.0 counts only *confirmed* Tier 3 violations, attributes them per principal, suspends only the offending principal, and requires violations from at least three distinct principals for a global trip. The HALF_OPEN probe reopens only on two or more violations from two or more principals. Act v2.1 Art. 7(2)(a) adopts this rule.

---

## 7. Limitations and open problems

1. **Lexical rules are a floor, not a ceiling.** They catch explicit phrasing and trivial obfuscation (Unicode normalisation, zero-width characters). They do not catch paraphrase, other languages or coded speech. They produce false positives on quotation and history, which `screen_prompts=False` mitigates for prompts. The test suite includes a false-positive corpus, but real deployments need evaluation on their own traffic.
2. **Judge models have their own biases.** Zero-shot templates inherit the judge model's cultural assumptions. The templates fence the reviewed text as data to resist prompt injection, but no fence is perfect. Calibrate thresholds on labelled local data.
3. **Essentialising cultures.** Encoding "Ubuntu" or "tillit" as rule packs risks flattening living, contested traditions. The packs are starting points for communities to edit through `custom_rules`, not definitions of those cultures.
4. **Who is the community?** Legitimacy tests (Act Art. 3(2)(c)) are procedural and can be captured. The guardrail can check whether consent is recorded; it cannot check whether consent was real.
5. **Downscaling planetary boundaries.** Allocating a global boundary to individual AI actors is a distributive-justice problem with no neutral answer. The Act assigns it to a transparent, reviewable ICT methodology rather than hiding it in code.
6. **Simulation validity.** Digital twins are only as good as their structure and data. The maximin criterion guards against averaging away catastrophe, but not against a mis-specified model, which is why a pass leads only to a pilot.
7. **Gaming and Goodhart effects.** Once a metric gates behaviour, systems may learn to avoid the indicator rather than the harm. Rotate and extend lexicons, rely on judges and field indicators, and audit outcomes, not just outputs.

---

## References

- Altman, E. (1999). *Constrained Markov Decision Processes.* Chapman & Hall/CRC.
- African Charter on Human and Peoples' Rights (1981), esp. Arts. 22, 24, 27–29.
- Carroll, S. R., et al. (2020). The CARE Principles for Indigenous Data Governance. *Data Science Journal*, 19(1), 43.
- Global Indigenous Data Alliance (2019). *CARE Principles for Indigenous Data Governance.*
- Mackenzie, C., & Stoljar, N. (Eds.) (2000). *Relational Autonomy: Feminist Perspectives on Autonomy, Agency, and the Social Self.* Oxford University Press.
- Mbiti, J. S. (1969). *African Religions and Philosophy.* Heinemann.
- Metz, T. (2007). Toward an African Moral Theory. *Journal of Political Philosophy*, 15(3), 321–341.
- Mhlambi, S. (2020). *From Rationality to Relationality: Ubuntu as an Ethical and Human Rights Framework for Artificial Intelligence Governance.* Carr Center for Human Rights Policy, Harvard Kennedy School.
- Rawls, J. (1971). *A Theory of Justice.* Harvard University Press.
- Raworth, K. (2017). *Doughnut Economics.* Chelsea Green. (The social foundation and ecological ceiling parallel Tier 3 and Tier 1.)
- Richardson, K., et al. (2023). Earth beyond six of nine planetary boundaries. *Science Advances*, 9(37).
- Rockström, J., et al. (2009). A safe operating space for humanity. *Nature*, 461, 472–475.
- Steffen, W., et al. (2015). Planetary boundaries: Guiding human development on a changing planet. *Science*, 347(6223).
- UN Committee on the Rights of the Child (2021). *General Comment No. 25 on children's rights in relation to the digital environment.*
- United Nations (2007). *Declaration on the Rights of Indigenous Peoples*, Arts. 18, 19, 31, 32.
- UNESCO (2021). *Recommendation on the Ethics of Artificial Intelligence.*
