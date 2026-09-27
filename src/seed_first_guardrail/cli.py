"""Command-line interface: ``seed-first-guardrail {validate-policy,check,schema}``."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from collections.abc import Sequence

from .audit import AuditLogger
from .config import PolicyConfig, load_policy_file, load_policy_schema, validate_policy_document
from .middleware import SeedFirstGuardrailProxy
from .types import PolicyValidationError

EXIT_OK, EXIT_INVALID, EXIT_BLOCKED = 0, 1, 2


def _validate(paths: Sequence[str]) -> int:
    status = EXIT_OK
    for path in paths:
        try:
            validate_policy_document(load_policy_file(path))
            PolicyConfig.from_file(path)
        except (PolicyValidationError, OSError) as exc:
            print(f"INVALID  {path}\n{exc}", file=sys.stderr)
            status = EXIT_INVALID
        else:
            print(f"VALID    {path}")
    return status


def _check(args: argparse.Namespace) -> int:
    try:
        config = PolicyConfig.from_file(args.policy) if args.policy else PolicyConfig()
    except (PolicyValidationError, OSError) as exc:
        print(exc, file=sys.stderr)
        return EXIT_INVALID
    guardrail = SeedFirstGuardrailProxy(config, audit_logger=AuditLogger(sinks=[]))
    decision = asyncio.run(
        guardrail.check_text(
            args.prompt, args.completion, is_macro_policy_proposal=args.macro_policy
        )
    )
    print(json.dumps(decision.to_dict(), indent=2))
    return EXIT_OK if decision.approved else EXIT_BLOCKED


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="seed-first-guardrail",
        description="Seed-First AI Guardrail: validate policies and screen text.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    v = sub.add_parser("validate-policy", help="Validate policy JSON files against the schema.")
    v.add_argument("paths", nargs="+")

    c = sub.add_parser("check", help="Screen a prompt/completion pair (exit 2 if blocked).")
    c.add_argument("--policy", help="Policy JSON file (defaults to built-in defaults).")
    c.add_argument("--prompt", required=True)
    c.add_argument("--completion", default="")
    c.add_argument(
        "--macro-policy",
        action="store_true",
        help="Treat the completion as a macro-policy proposal (runs simulation).",
    )

    sub.add_parser("schema", help="Print the policy JSON schema.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "validate-policy":
        return _validate(args.paths)
    if args.command == "check":
        return _check(args)
    print(json.dumps(load_policy_schema(), indent=2))
    return EXIT_OK


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
