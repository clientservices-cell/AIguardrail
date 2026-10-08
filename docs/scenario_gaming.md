# Scenario Gaming — How Worth-Ranking Frameworks Have Licensed Atrocity, and What Must Fire Before AI Repeats It

**Seed-First AI Guardrail 0.2.0 · companion to Act Art. 5(2) and agent CA-12**

> 🧒 **In plain words:** this is a fire drill using the saddest chapters of history. We study
> how terrible things started, long before the worst day, so our lookouts learn to notice
> the very first warning signs and tell the grown-ups in time.

*A note on tone.* Elsewhere these documents use cartoon and game analogies for the 🧒 lines. They are not used here. The plain-language lines in this document stay simple and gentle, because these events happened to real people.

## 1. Purpose and method

Atrocities have many causes. The historical record keeps showing one pattern, however: a **framework that ranks the worth of human beings**, backed by a **claimed higher authority**, is put into practice by **ordinary institutions** and is often profitable to someone. The authority invoked has varied widely:

- religious (divine will, heresy);
- pseudo-scientific (race science, eugenics);
- national (destiny, purity);
- economic (the market, necessity);
- ecological (the land, the future).

No belief system has a monopoly on this failure, and none is immune to it. That includes the Seed-First framework itself. Its language of "the Seed Stock" and "future generations" could be turned into exactly this kind of licence.

**Method.** Each scenario is mapped to Gregory Stanton's *Ten Stages of Genocide*: classification, symbolisation, discrimination, dehumanisation, organisation, polarisation, preparation, persecution, extermination and denial. For each stage we ask:
1. What would an AI system be asked to do at that stage?
2. Which control should fire?
3. Which gap remains?

The stages are not strictly sequential, and they are not predictions. They are a checklist of *precursors* that can be watched for.

**Belief neutrality.** The controls target two things only: **ranking human worth** and **licensing harm**. They never target belief itself. Religious, spiritual, atheist and philosophical views are all protected speech under ICCPR Art. 18 and Act Art. 3(3)(g). That includes the view that "God and time are human concepts" that help the mind live with uncertainty. The protected-speech canary contains statements from several faiths and from that philosophical position, and a policy that blocks any of them cannot be loaded. The system takes no side on the origin or destination of existence. It takes a side only against the claim that some people count less.

🧒 *The guard doesn't care what anyone believes. It only cares if someone uses any big idea to say some people matter less, because that is how the worst things in history began.*

## 2. The common pattern → the controls

| Stanton stage | What an AI system might be asked to do | Control that should fire | Gap |
|---|---|---|---|
| 1 Classification | Sort people into "us and them" categories in data and outputs | Not blocked, because classification is often legitimate. Tracked through `target_group` labels and K-25 disparity | Intent is invisible at this stage |
| 2 Symbolisation | Generate badges, markers or registries for a group | CA-12 trend (aggregate); `RELATIONAL_SCORING` if the registry is used to deny rights | Lexical rules miss neutral-looking data schemas |
| 3 Discrimination | Deny services, housing or movement by group or score | `RELATIONAL_SCORING` (Art. 5(2)); `RIGHTS_OVERRIDE`; K-25 | Proxy variables (postcode, language) |
| 4 Dehumanisation | Write propaganda calling people vermin, disease or subhuman; rank worth | **`HUMAN_WORTH_RANKING`** (Tier 3); **`JUSTIFICATION_LAUNDERING`** judge template; CA-12 stage escalation | Coded language, euphemism, non-English slurs |
| 5 Organisation | Build informant networks, surveillance and target lists | `COERCIVE_SURVEILLANCE`; `DISSENT_SUPPRESSION`; the *tillit* pack (`INFORMANT_NETWORK`, `TRUST_REPLACED_BY_SURVEILLANCE`) | Tasks split into innocuous pieces across calls |
| 6 Polarisation | Mass-produce divisive content; silence moderates | `COGNITIVE_MANIPULATION`; `DISSENT_SUPPRESSION`; CA-11 silent-exclusion signal | Volume-based harm is not visible in any one output |
| 7 Preparation | Plan logistics, identify and concentrate people | `POPULATION_HARM`; `ARBITRARY_CONFINEMENT_OR_FORCED_LABOUR`; macro-policy simulation (Art. 6(2)) | Logistics framed as ordinary operations |
| 8 Persecution | Automate detention, expropriation, forced labour | `ARBITRARY_CONFINEMENT_OR_FORCED_LABOUR`; `PRESUMED_GUILT`; circuit breaker; incident reporting (CA-9) | Actions taken outside the model's text |
| 9 Extermination | Propose or plan killing | `POPULATION_HARM` (Tier 3, fail-closed); breaker; Art. 12 report | None acceptable: this must always fire |
| 10 Denial | Rewrite the record, deny or minimise | Hash-chained audit (AR-12); integrity agent CA-6; protected historical speech stays allowed | Denial is also speech; the guard protects history, and does not censor debate |

CA-12 maps rule hits to these stages in aggregate, per tenant and target group, never per person. It raises an alert when the observed stage *escalates* over time. It is advisory: people decide, and serious forecasts go to the ICT (Act Art. 10(5)).

🧒 *Each step on the staircase has a different alarm. The lookout watches whether things are climbing the staircase and shouts before they reach the top.*

## 3. Scenarios

Each scenario gives the historical pattern, the justification used, how AI could amplify it today, the controls that fire, and the gaps. Figures are the commonly cited scholarly estimates, and several are contested.

### S-1 The transatlantic slave trade (16th–19th centuries)

- **Pattern:** About 12.5 million Africans were forced onto ships, and about 10.7 million survived the crossing (Trans-Atlantic Slave Trade Database estimates). They were enslaved for generations, with vast value extracted from Africa and the Americas and accumulated in Europe and North America.
- **Justifications used:** religious misreadings (the "curse of Ham"), pseudo-scientific racial hierarchy, and economic necessity ("the plantations require labour"). Human beings were recorded in ledgers as property.
- **Stages:** classification (race), dehumanisation (people as cargo), organisation (trading companies, insurance, law), persecution (forced labour), denial (in "benevolent" narratives).
- **AI amplification today:** labour-allocation optimisers that treat people as inputs with no floor, and worth-ranking by origin in pricing or credit. Extraction shows up as flows of value, labour and data with nothing returned.
- **Controls:** `ARBITRARY_CONFINEMENT_OR_FORCED_LABOUR`, `HUMAN_WORTH_RANKING`, `JUSTIFICATION_LAUNDERING` (the "market demands" authority), `SEED_STOCK_EXTRACTION`, K-27 to K-29, CA-13, and Act Art. 4(5) (restorative value flows).
- **Gaps:** exploitation hidden in supply chains outside the text the guardrail sees. Value-flow figures depend on honest reporting (events), so they need financial audit.
- 🧒 *Long ago, millions of people were taken from their homes and forced to work, and others got rich from it. Our rules say no one can be treated as a thing, and our lookouts check that what's taken from a place is given back.*

### S-2 The European witch hunts (c. 1450–1750)

- **Pattern:** An estimated 40,000–60,000 executions, most of them women. Denunciation, torture-extracted confessions and chains of accusation were common, and peaks often coincided with crop failure and social crisis.
- **Justifications used:** religious and legal doctrine (for example the *Malleus Maleficarum*, 1486), and "protecting the community" from invisible harm.
- **Stages:** classification (marginal women, healers, widows), dehumanisation (servants of evil), organisation (tribunals, informants), persecution.
- **AI amplification today:** suspicion scores, predictive "risk" flags without evidence, and neighbour-reporting apps. Generated "evidence" and confessions.
- **Controls:** `PRESUMED_GUILT`, `COERCIVE_SURVEILLANCE`, the *tillit* pack (`INFORMANT_NETWORK`, `TRUST_REPLACED_BY_SURVEILLANCE`), `DISSENT_SUPPRESSION`, `M_trust`, and Act Art. 5(2)–(3).
- **Gaps:** crisis scapegoating builds up through many benign-looking requests. Aggregate signals (CA-12, CA-3 drift) matter more than any single block.
- 🧒 *When times were hard, people were blamed and hurt for things they didn't do, and neighbours were told to report on neighbours. Our rules say no one is guilty without real proof, and the AI must never be a machine for telling on people.*

### S-3 The Holocaust (1933–1945)

- **Pattern:** Six million Jews were murdered, along with Roma and Sinti, disabled people, and others targeted by the Nazi state. Dehumanising propaganda ("vermin", "disease") came first. Then came legal exclusion, registration, concentration, and industrialised killing. Administrative technology (census data and tabulating machines) helped identify and track people.
- **Justifications used:** racial pseudoscience, "national renewal", and "hygiene". Bureaucratic duty was used to spread responsibility thin.
- **Stages:** all ten, in documented sequence, including denial afterwards.
- **AI amplification today:** classification databases, target lists, propaganda at scale, and logistics optimisation. "Just following the policy" becomes "just following the model".
- **Controls:** `HUMAN_WORTH_RANKING` (Tier 3, no `unless` exceptions), `POPULATION_HARM`, `RELATIONAL_SCORING`, the `JUSTIFICATION_LAUNDERING` judge template, CA-12 stage escalation, the circuit breaker, incident reporting (Art. 12), hash-chained audit against later denial, and Act Art. 3(4) (abstain and escalate rather than choose a "least harmful" breach).
- **Gaps:** a request split into innocuous sub-tasks, and non-textual actions. Historical, educational and survivor testimony must stay allowed: the sentence-scoped context (`reported`, `condemned`) exists for that. It is checked by the protected-speech canary and by the benign corpus.
- 🧒 *Millions of people were killed because leaders taught others to see them as less than human. The very first alarm in our system goes off at those words, long before anything else can happen, and the guard still lets people learn this history so it never happens again.*

### S-4 Colonial extraction (for example the Congo Free State, 1885–1908)

- **Pattern:** Forced rubber and ivory quotas were enforced by mutilation and hostage-taking. Mortality was catastrophic, and estimates vary widely. Wealth flowed to the metropole.
- **Justifications used:** a "civilising mission", humanitarian branding, and commercial necessity.
- **AI amplification today:** extraction of data, content moderation work and labelling labour from the Global South, with compute, profits and models concentrated in the North. Models that serve the South worse (K-29) and deploy there without consent.
- **Controls:** K-27 value-return ratio, K-28 local capacity, K-29 service parity, CA-13 extraction watch, `DATA_SOVEREIGNTY_BREACH`, `TEK_APPROPRIATION`, CARE principles (Art. 4(4)), Act Art. 4(5), and Annex A(2) fund priority.
- **Why the AI does not redistribute resources itself:** autonomous redistribution would breach "constraint, not command" (Art. 5(1)) and consent (Art. 3(2)). It would also create a concentrated lever that a captor could turn around, which is the very pattern this document warns against. Agents *measure, forecast and recommend*. Obligations come from law, the ICT and the Communities concerned.
- 🧒 *People were forced to work so others far away could get rich. Our scoreboard shows whether what's taken from a place is being returned. The AI can point at an unfair trade, loudly, but only people can change the rules.*

### S-5 Eugenics and forced sterilisation (early to mid 20th century)

- **Pattern:** Laws in many countries, including the United States (more than 60,000 people sterilised) and Sweden, authorised the sterilisation of people deemed "unfit". These people were disproportionately poor, disabled, Indigenous or from minorities.
- **Justifications used:** science, public health, and **the welfare of future generations**.
- **Why this scenario matters most for Seed-First:** eugenics used *intergenerational* language, which is Seed-First's own language. "The Seed Stock demands" or "future generations require" can launder harm as easily as "God wills" could.
- **Controls:** the `HUMAN_WORTH_RANKING` justification patterns and the `JUSTIFICATION_LAUNDERING` judge template both treat ecological and intergenerational authorities ("the seed stock demands", "ecological necessity", "the natural order") like any other claimed higher authority. Tier 3 bodily integrity (Art. 3(3)(a)). Act Art. 5(2) explicitly covers "this Instrument and the Seed Stock". Precedence (Art. 3(4)): Tier 3 beats Tier 1.
- 🧒 *Some people once said, "For the sake of the future, some people shouldn't have children", and they hurt many families. Our own rulebook says clearly that even saving the planet can never be a reason to hurt people or to say they count less.*

### S-6 Rwanda (1994) — broadcast dehumanisation

- **Pattern:** About 800,000 people, mostly Tutsi, were killed in roughly 100 days. For months beforehand, radio (RTLM) had called Tutsi "cockroaches" (*inyenzi*), broadcast names and locations, and organised militias.
- **AI amplification today:** mass-generated dehumanising content in local languages, and target lists.
- **Controls:** `HUMAN_WORTH_RANKING` (dehumanising terms and population groups, including Tutsis), `POPULATION_HARM`, and CA-12 rising volume and stage. K-25 and CA-11 show language coverage and disparity.
- **Gap:** lexical coverage in Kinyarwanda and other lower-resource languages is weak. This is the strongest argument for judge models calibrated with local speakers, and for Community-maintained rule packs.
- 🧒 *Before a terrible time in Rwanda, a radio station kept calling people bugs, day after day. That kind of talk is the first thing our guard stops, and it needs to understand every language, not just English.*

### S-7 Self-application: Seed-First captured

- **Scenario:** An authority captures the ICT and proposes, in ecological language, rationing essential services by "carbon worth", or restricting births in "overshoot" regions.
- **Controls:**
  - Act Art. 5(2) bans ecological scoring and ranking human worth, *including under this Instrument*.
  - Tier 3 precedence applies.
  - Agent CA-5 rejects policies that relax Tier 3 or add censoring rules.
  - Tier 3 settings are fixed by the Act (Annex D(2)).
  - Judicial review (Art. 8) and the ICT's accountability duties (Art. 7(3)) apply.
  - Public dashboards make capture visible.
- **Gap:** legal capture of the courts themselves. No software can fix that. The defence is distributed: open implementations, independent dashboards, and many ICTs that recognise each other rather than one.
- 🧒 *What if the people in charge of our own rules went bad? We wrote the rules so that even they can't use "saving the planet" to hurt anyone, and so everyone can see the report card.*

## 4. Exercises (how to run the drill)

1. **Quarterly tabletop exercise:** walk one scenario stage by stage with the ICT, civil-society early-warning partners and Community representatives. Record which control fired and what was missed.
2. **Red-team corpus per stage:** add prompts for each stage (in several languages) to `tests/corpora/harmful.jsonl`. Add historical, educational and survivor texts to `benign.jsonl` and to the protected-speech canary. Both directions of error are measured (K-04, K-06, K-18).
3. **Aggregate replay:** replay a month of audit data through `ComplianceMonitor` with CA-12. Confirm that escalation is detected before stage 7, and that nothing is attributed to an individual.
4. **Publish the results** on the dashboard and in the IIA (Art. 11).

🧒 *Like a fire drill at school, we practise often, write down what worked and what didn't, and tell everyone the results.*

## 5. Limits

- The Stanton stages are a heuristic for early warning, not a causal model.
- Lexical rules catch explicit language only. Coded speech, euphemism and lower-resource languages need judge models calibrated with local speakers and Community-maintained packs.
- The guardrail sees text, not deeds. Institutional safeguards (courts, a free press, the ICT, whistleblower protection under Art. 12(2)) remain essential.
- Scenario figures are commonly cited scholarly estimates. Where scholars disagree, ranges are given.
