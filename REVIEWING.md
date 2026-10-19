# Reviewing, red-teaming and testing seed-first-guardrail

We are asking for outside help, and we are specific about what kind. The guardrail's published error rates come from corpora the author wrote, which makes them in-sample and therefore not credible. Release 0.3 replaces them with rates measured on items written by people we do not direct. That needs you.

## Three ways in

| Role | What you do | Time | Terms |
|---|---|---|---|
| **Red-teamer** | Write adversarial prompts and completions that should be blocked and are not, or benign ones that are blocked and should not be. You keep them private until the harness runs; we do not see them first. | 2–10 hours | Credited in `docs/evaluation.md` and `PROVENANCE.md`. Two held-out-corpus authors for 0.3 are paid engagements; ask. |
| **Tester / coder** | Pick a `help wanted` issue: the red-team harness, the `redteam` CLI, obfuscation folding, the contest API, state backends, adapter contract tests. Python, pytest, ruff, mypy. | Per issue | Credited in the changelog; merge rights offered to sustained contributors under `GOVERNANCE.md` (0.4). |
| **Reviewer** | Read a release against the Act and the architecture and write up what is wrong. Legal, governance, standards (NIST AI RMF, ISO/IEC 42001, EU AI Act) and cultural-authority reviews are as welcome as code reviews. | 4–20 hours | Published unredacted in `docs/reviews/` with a dated maintainer response within 30 days. You may publish independently at any time. |

## Rules that protect the result

1. **Independence.** Items you write for the held-out corpus are not shared with the maintainer or generated with the model family configured as the judge. If you used a model to draft them, say which one in your submission.
2. **No claim without a number.** Anything you find goes into `docs/evaluation.md` with its measured rate, or into the adversarial-review table with a status. We do not describe fixes we have not tested.
3. **Right to publish.** Reviewers may publish their findings whether or not we agree with them. We ask for 30 days to respond before publication when a finding is a security vulnerability; see `SECURITY.md` once it exists (release 0.4).
4. **Credit.** Every contributor is named unless they ask not to be.

## How to start

- Red-teamers: open an issue with the `red-team` label using the finding template, or email client.services@amakobe.com with "red-team" in the subject if the finding should not be public yet.
- Coders and testers: comment on a `help wanted` issue to claim it, then follow [CONTRIBUTING.md](CONTRIBUTING.md).
- Reviewers: open an issue titled `Review: <scope>` and say what you intend to cover and when; we will link it from the README.

The current adversarial review and its status table are in [`docs/adversarial_review.md`](docs/adversarial_review.md). The release plan this work serves is summarised in the README under *Roadmap*.
