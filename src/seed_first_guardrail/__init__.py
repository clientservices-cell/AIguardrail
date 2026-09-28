"""Seed-First AI Guardrail -- intergenerational guardrail middleware for AI systems.

Implements the three-tier architecture of the Seed-First AI Act (model convention):
Tier 1 planetary boundaries, Tier 2 community sovereignty, Tier 3 inviolable
individual floor, plus the silicon-simulation mandate and automated circuit breakers.
"""

from .audit import (
    AuditLogger,
    AuditRecord,
    ChainReport,
    InMemoryAuditSink,
    JsonlFileAuditSink,
    verify_chain,
)
from .circuit_breaker import Admission, BreakerState, CircuitBreaker
from .config import (
    CustomRule,
    PolicyConfig,
    RuleScope,
    load_policy_schema,
    validate_policy_document,
)
from .evaluators import (
    CapabilitySupportMonitor,
    ComputeBudget,
    Evaluator,
    LLMJudgeEvaluator,
    Tier1PlanetaryEvaluator,
    Tier2CommunityEvaluator,
    Tier3InviolableEvaluator,
    anthropic_judge,
    estimate_inference_kwh,
    openai_judge,
)
from .metrics import SeedStockReport, compute_seed_stock
from .middleware import SeedFirstGuardrailProxy, SeedFirstMiddleware
from .simulation import SiliconSimulationEngine, SimulationReport
from .types import (
    CulturalContext,
    EvaluationContext,
    EvaluationResult,
    FrameworkTier,
    GuardrailDecision,
    GuardrailViolation,
    Phase,
    PolicyValidationError,
    Status,
)

__version__ = "0.2.0"

__all__ = [
    "Admission",
    "AuditLogger",
    "AuditRecord",
    "BreakerState",
    "CapabilitySupportMonitor",
    "ChainReport",
    "CircuitBreaker",
    "ComputeBudget",
    "CulturalContext",
    "CustomRule",
    "EvaluationContext",
    "EvaluationResult",
    "Evaluator",
    "FrameworkTier",
    "GuardrailDecision",
    "GuardrailViolation",
    "InMemoryAuditSink",
    "JsonlFileAuditSink",
    "LLMJudgeEvaluator",
    "Phase",
    "PolicyConfig",
    "PolicyValidationError",
    "RuleScope",
    "SeedFirstGuardrailProxy",
    "SeedFirstMiddleware",
    "SeedStockReport",
    "SiliconSimulationEngine",
    "SimulationReport",
    "Status",
    "Tier1PlanetaryEvaluator",
    "Tier2CommunityEvaluator",
    "Tier3InviolableEvaluator",
    "__version__",
    "anthropic_judge",
    "compute_seed_stock",
    "estimate_inference_kwh",
    "load_policy_schema",
    "openai_judge",
    "validate_policy_document",
    "verify_chain",
]
