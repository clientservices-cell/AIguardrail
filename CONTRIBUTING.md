# Contributing

Thank you for helping build intergenerational guardrails. Contributions of code, rules, translations, policy analysis and community rule packs are all welcome.

## Setup

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate    macOS/Linux: source .venv/bin/activate
pip install -e ".[dev]"
```

## Before opening a pull request

```bash
pytest --cov=seed_first_guardrail --cov-fail-under=95
ruff check src tests
ruff format --check src tests
mypy
```

All four must pass. CI should run the same commands.

## Adding or changing a lexical rule

Rules live in `evaluators/tier3.py` (the inviolable floor) and `evaluators/tier2.py` (community packs).

1. **Cite the article.** Every `PatternRule` needs an `article` from the [Act](docs/seed_first_ai_act.md).
2. **Add a positive test *and* a false-positive test.** Put harmful phrasing in `VIOLATIONS` and at least one benign look-alike in `BENIGN` (see `tests/test_tier3.py`). A rule that blocks history lessons, medical advice or news reporting does real harm too.
3. **Prefer `unless` over weaker patterns.** If a rule should not fire when consent, mitigation or an educational context is stated, use `unless=` rather than narrowing the main pattern until it misses real cases.
4. **Keep patterns bounded.** Use `GAP2`/`GAP3` or `[^.;]{0,N}` rather than `.*`, to avoid catastrophic backtracking and runaway matches across sentences.

## Community rule packs

Cultural context packs are starting points written from published sources, not definitions of living traditions. If you belong to a community whose context is represented, or want one added, we especially welcome your input:

- For local rules, publish them in your own policy's `custom_rules`; no code change is needed.
- For shared packs, open an issue describing the principle, its source, and example phrasings that should and should not match.

## Policy and legal text

- Changes to `docs/seed_first_ai_act.md` should add a row to its change log explaining the problem and the fix.
- Crosswalk entries you are not certain of must carry `"verify": true`. Never invent article numbers.
- Nothing in this repository is legal advice. Please say so where relevant.

## Judge templates

Templates in `classifiers/prompts.py` must:

- request the strict JSON verdict (`violation`, `score`, `rationale`);
- keep reviewed text inside the fenced `<prompt>`/`<completion>` tags; and
- list explicit "Do NOT count" cases to limit false positives.

## Code of conduct

Be respectful. This project exists to protect dignity; that starts with how we treat each other.
