"""Command-line interface.

    seed-first-guardrail validate-policy FILE...
    seed-first-guardrail check [--policy FILE] --prompt TEXT [--completion TEXT] [--macro-policy]
    seed-first-guardrail schema
    seed-first-guardrail kpi-export --audit AUDIT.jsonl [--events EVENTS.jsonl] [--policy FILE] --out SNAPSHOT.json
    seed-first-guardrail monitor --audit AUDIT.jsonl [--events EVENTS.jsonl] [--out ALERTS.jsonl]
    seed-first-guardrail policy-diff OLD.json NEW.json
    seed-first-guardrail dashboard --snapshot SNAPSHOT.json --out index.html

🧒 The buttons you can press from the keyboard: check a rulebook, test a sentence, make
the public scoreboard, wake up the lookouts, or compare an old rulebook with a new one.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from collections.abc import Sequence
from datetime import datetime, timezone
from typing import Any

from .accountability.agents import ComplianceMonitor, PolicyGovernanceAgent, default_agents
from .accountability.events import load_jsonl, parse_time
from .accountability.snapshot import build_snapshot
from .audit import KEY_ENV, AuditLogger
from .config import PolicyConfig, load_policy_file, load_policy_schema, validate_policy_document
from .dashboard import render as render_dashboard
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
    guardrail = SeedFirstGuardrailProxy(config, audit_logger=AuditLogger(sinks=[], key=b"cli"))
    decision = asyncio.run(
        guardrail.check_text(
            args.prompt, args.completion, is_macro_policy_proposal=args.macro_policy
        )
    )
    print(json.dumps(decision.to_dict(), indent=2))
    return EXIT_OK if decision.approved else EXIT_BLOCKED


def _inputs(args: argparse.Namespace) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    records = load_jsonl(args.audit)
    events = load_jsonl(args.events) if args.events else []
    return records, events


def _audit_key() -> str | None:
    return os.environ.get(KEY_ENV)


def _kpi_export(args: argparse.Namespace) -> int:
    records, events = _inputs(args)
    policy = load_policy_file(args.policy) if args.policy else None
    now = parse_time(args.now) if args.now else datetime.now(timezone.utc)
    key = _audit_key()
    snapshot = build_snapshot(
        records,
        events,
        now=now,
        delay_days=args.delay_days,
        k=args.k,
        policy=policy,
        audit_key=key,
        demonstration=args.demonstration,
        monitor=ComplianceMonitor(default_agents(key)),
    )
    text = json.dumps(snapshot, indent=2, ensure_ascii=False)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            fh.write(text + "\n")
        print(
            f"wrote {args.out}: {len(snapshot['kpis'])} KPIs, {len(snapshot['alerts'])} public alerts"
        )
    else:
        print(text)
    return EXIT_OK


def _monitor(args: argparse.Namespace) -> int:
    records, events = _inputs(args)
    now = parse_time(args.now) if args.now else None
    alerts = ComplianceMonitor(default_agents(_audit_key())).run(records, events, now=now)
    lines = [json.dumps(a.__dict__, ensure_ascii=False) for a in alerts]
    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            fh.write("".join(line + "\n" for line in lines))
    for a in alerts:
        print(f"[{a.severity.upper():8s}] {a.agent} {a.code}: {a.title}")
    return EXIT_BLOCKED if any(a.severity == "critical" for a in alerts) else EXIT_OK


def _policy_diff(args: argparse.Namespace) -> int:
    old, new = load_policy_file(args.old), load_policy_file(args.new)
    alerts = PolicyGovernanceAgent().review(old, new)
    for a in alerts:
        print(f"[{a.severity.upper():8s}] {a.code}: {a.title}\n           {a.public_summary}")
    if not alerts:
        print("No relaxations or invalid rules found.")
    return EXIT_BLOCKED if any(a.severity == "critical" for a in alerts) else EXIT_OK


def _dashboard(args: argparse.Namespace) -> int:
    with open(args.snapshot, encoding="utf-8") as fh:
        snapshot = json.load(fh)
    with open(args.out, "w", encoding="utf-8") as fh:
        fh.write(render_dashboard(snapshot))
    print(f"wrote {args.out}")
    return EXIT_OK


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="seed-first-guardrail",
        description="Seed-First AI Guardrail: policies, screening, KPIs and compliance agents.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    v = sub.add_parser("validate-policy", help="Validate policy JSON files against the schema.")
    v.add_argument("paths", nargs="+")

    c = sub.add_parser("check", help="Screen a prompt/completion pair offline (exit 2 if blocked).")
    c.add_argument("--policy", help="Policy JSON file (defaults to built-in defaults).")
    c.add_argument("--prompt", required=True)
    c.add_argument("--completion", default="")
    c.add_argument(
        "--macro-policy",
        action="store_true",
        help="Treat the completion as a macro-policy proposal (runs simulation).",
    )

    sub.add_parser("schema", help="Print the policy JSON schema.")

    for name, helptext in (
        ("kpi-export", "Build the privacy-safe public KPI snapshot."),
        ("monitor", "Run the compliance agents (exit 2 on a critical alert)."),
    ):
        p = sub.add_parser(name, help=helptext)
        p.add_argument("--audit", required=True, help="Audit trail (JSON lines).")
        p.add_argument("--events", help="Accountability events (JSON lines).")
        p.add_argument("--out", help="Output file (default: stdout / console summary).")
        p.add_argument("--now", help="Evaluate as of this ISO-8601 time.")
        if name == "kpi-export":
            p.add_argument("--policy", help="Policy JSON (for K-12 and publication consent).")
            p.add_argument("--delay-days", type=int, default=7)
            p.add_argument("--k", type=int, default=20, help="Minimum group size to publish.")
            p.add_argument(
                "--demonstration", action="store_true", help="Mark the data as synthetic."
            )

    d = sub.add_parser("policy-diff", help="Review a policy change before deployment (agent CA-5).")
    d.add_argument("old")
    d.add_argument("new")

    h = sub.add_parser("dashboard", help="Render the public dashboard HTML from a snapshot.")
    h.add_argument("--snapshot", required=True, help="Snapshot JSON from kpi-export.")
    h.add_argument("--out", required=True, help="Output HTML file.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    commands = {
        "validate-policy": lambda: _validate(args.paths),
        "check": lambda: _check(args),
        "kpi-export": lambda: _kpi_export(args),
        "monitor": lambda: _monitor(args),
        "policy-diff": lambda: _policy_diff(args),
        "dashboard": lambda: _dashboard(args),
    }
    if args.command in commands:
        return commands[args.command]()
    print(json.dumps(load_policy_schema(), indent=2))
    return EXIT_OK


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
