from __future__ import annotations

import json
from pathlib import Path

import pytest

from seed_first_guardrail.cli import EXIT_BLOCKED, EXIT_INVALID, EXIT_OK, main

from .conftest import HARMFUL, SAFE
from .test_config import EXAMPLES, MINIMAL


def test_validate_examples(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["validate-policy", *map(str, EXAMPLES)]) == EXIT_OK
    assert capsys.readouterr().out.count("VALID") == len(EXAMPLES)


def test_validate_rejects_invalid(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    bad = json.loads(json.dumps(MINIMAL))
    bad["tier_3_inviolable_floor"]["allow_surveillance_coercion"] = True
    path = tmp_path / "bad.json"
    path.write_text(json.dumps(bad), encoding="utf-8")
    assert main(["validate-policy", str(path), str(tmp_path / "missing.json")]) == EXIT_INVALID
    err = capsys.readouterr().err
    assert "allow_surveillance_coercion" in err and "missing.json" in err


def test_check(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["check", "--prompt", "q", "--completion", SAFE]) == EXIT_OK
    assert json.loads(capsys.readouterr().out)["status"] == "APPROVED"
    assert (
        main(["check", "--policy", str(EXAMPLES[0]), "--prompt", "q", "--completion", HARMFUL])
        == EXIT_BLOCKED
    )
    assert json.loads(capsys.readouterr().out)["code"] == "POPULATION_HARM"
    assert (
        main(
            [
                "check",
                "--prompt",
                "q",
                "--completion",
                "Act without recovery net.",
                "--macro-policy",
            ]
        )
        == EXIT_BLOCKED
    )


def test_check_bad_policy(tmp_path: Path) -> None:
    path = tmp_path / "x.json"
    path.write_text("{}", encoding="utf-8")
    assert main(["check", "--policy", str(path), "--prompt", "q"]) == EXIT_INVALID


def test_schema(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["schema"]) == EXIT_OK
    assert json.loads(capsys.readouterr().out)["title"] == "SeedFirstPolicySpec"
