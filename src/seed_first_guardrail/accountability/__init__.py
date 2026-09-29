"""Accountability layer: KPIs, model scorecards, predictive compliance agents and the public snapshot.

🧒 The report card (KPIs), the lookouts (compliance agents) and the classroom-wall
poster (public snapshot) -- so everyone can see how the AI is behaving.
"""

from .agents import ALL_AGENTS, Alert, ComplianceMonitor, ComplianceSink, default_agents
from .events import load_jsonl
from .kpis import KPI_BY_ID, KPI_DEFINITIONS, KPIDefinition, KPIResult, compute_kpis, wilson
from .scorecards import model_scorecards, rating_method
from .snapshot import build_snapshot, load_snapshot_schema

__all__ = [
    "ALL_AGENTS",
    "KPI_BY_ID",
    "KPI_DEFINITIONS",
    "Alert",
    "ComplianceMonitor",
    "ComplianceSink",
    "KPIDefinition",
    "KPIResult",
    "build_snapshot",
    "compute_kpis",
    "default_agents",
    "load_jsonl",
    "load_snapshot_schema",
    "model_scorecards",
    "rating_method",
    "wilson",
]
