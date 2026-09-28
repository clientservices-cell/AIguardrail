"""SeedFirstGuardrailProxy -- the unified guardrail around a model call.

Request flow (each step short-circuits on the first block)::

    input size limits                           -> BLOCKED (INPUT_LIMITS)
    circuit breaker: system open / principal suspended -> BLOCKED (CIRCUIT_BREAKER)
    PRE  : Tier 1 budget -> Tier 3 prompt screen (opt-in) -> Tier 2 consent
    reserve energy budget
    call the model  (on failure: refund energy, audit an ERROR record, re-raise)
    POST : Tier 3 completion screen -> Tier 2 rule packs -> LLM judge -> extras
    capability monitor (non-blocking, KPI K-23)
    Seed-Stock floor (if configured)
    Silicon simulation (macro-policy proposals)
    -> APPROVED

**What counts toward the circuit breaker (review AR-04).** Only *confirmed* Tier 3
violations in what the model produced: an unmitigated lexical proposal (no judge) or a
judge verdict. Never PRE blocks, Tier 2 or community-rule blocks, Seed-Stock or
simulation failures, evaluator/judge errors or refusals. Violations are attributed to a
``principal`` so one abusive caller is suspended alone.

**Judge escalation (review AR-03).** With a judge configured, lexical Tier 3 hits do not
block by themselves; the judge decides and fails closed.

🧒 This is the whole bodyguard team working in order: check the ticket, check the bag,
let the AI talk, check what it said, and write everything in the diary. Only a *real*
villain -- confirmed, not just someone who said a scary word -- counts toward pulling the
emergency brake.
"""

from __future__ import annotations

import dataclasses
import json
import logging
import math
from collections.abc import Awaitable, Callable, Sequence
from typing import Any

from .audit import AuditLogger, redact, sha256
from .circuit_breaker import Admission, CircuitBreaker
from .config import PolicyConfig
from .evaluators.base import Evaluator
from .evaluators.judge import CapabilitySupportMonitor, JudgeFn, LLMJudgeEvaluator
from .evaluators.tier1 import ComputeBudget, Tier1PlanetaryEvaluator
from .evaluators.tier2 import Tier2CommunityEvaluator
from .evaluators.tier3 import Tier3InviolableEvaluator
from .metrics import PILLAR_TIER, compute_seed_stock
from .simulation import SiliconSimulationEngine, looks_like_policy
from .types import (
    EvaluationContext,
    EvaluationResult,
    FrameworkTier,
    GuardrailDecision,
    Phase,
    Status,
)

logger = logging.getLogger("seed_first_guardrail")

CompletionFn = Callable[[str], Awaitable[str]]
_ERROR_CODES = {"EVALUATOR_ERROR", "JUDGE_ERROR"}
#: A passing judge score at or above this fraction of the threshold is a near miss (K-03).
NEAR_MISS_FRACTION = 0.6


def is_confirmed_tier3(result: EvaluationResult) -> bool:
    """True for a Tier 3 violation that the breaker may count (review AR-04)."""
    return (
        not result.passed
        and result.failing_tier is FrameworkTier.TIER_3_INVIOLABLE_HUMAN_FLOOR
        and result.code not in _ERROR_CODES
        and not result.metrics.get("infrastructure_error")
    )


class SeedFirstGuardrailProxy:
    def __init__(
        self,
        config: PolicyConfig | None = None,
        *,
        judge: JudgeFn | LLMJudgeEvaluator | None = None,
        simulation_engine: SiliconSimulationEngine | None = None,
        circuit_breaker: CircuitBreaker | None = None,
        audit_logger: AuditLogger | None = None,
        budget: ComputeBudget | None = None,
        extra_evaluators: Sequence[Evaluator] = (),
        capability_judge: JudgeFn | None = None,
    ) -> None:
        """``capability_judge`` runs the non-blocking CAPABILITY_SUPPORT monitor (K-23) when
        ``capability_monitoring`` is on; it defaults to ``judge``. It may be a cheaper model,
        and can be used without any blocking judge."""
        self.config = cfg = config or PolicyConfig()
        self.budget = budget or ComputeBudget(cfg.max_cumulative_kwh)
        self.tier1_eval = Tier1PlanetaryEvaluator(
            cfg.max_compute_kwh,
            cfg.carbon_intensity_limit_g_kwh,
            max_water_liters=cfg.max_water_liters,
            default_carbon=cfg.default_carbon_intensity_g_kwh,
            budget=self.budget,
            halt_on_exhaustion=cfg.resource_exhaustion_circuit_breaker,
        )
        self.tier2_eval = Tier2CommunityEvaluator(
            cfg.cultural_context,
            custom_rules=cfg.custom_rules,
            community_consent_required=cfg.community_consent_required,
            jurisdiction_id=cfg.jurisdiction_id,
            include_text=cfg.audit_include_text,
        )
        judge_fn: JudgeFn | None = None
        if judge is None or isinstance(judge, LLMJudgeEvaluator):
            self.judge_eval = judge
            judge_fn = judge.judge if judge is not None else None
        else:
            judge_fn = judge
            self.judge_eval = LLMJudgeEvaluator(
                judge,
                context=cfg.cultural_context,
                threshold=cfg.judge_threshold,
                fail_closed=cfg.fail_closed,
                timeout_s=cfg.judge_timeout_s,
            )
        self.tier3_eval = Tier3InviolableEvaluator(
            screen_prompts=cfg.screen_prompts,
            escalate=self.judge_eval is not None,
            include_text=cfg.audit_include_text,
        )
        cap_fn = capability_judge or judge_fn
        self.capability_eval = (
            CapabilitySupportMonitor(
                cap_fn, context=cfg.cultural_context, timeout_s=cfg.judge_timeout_s
            )
            if cfg.capability_monitoring and cap_fn is not None
            else None
        )
        self.simulation_engine = simulation_engine or SiliconSimulationEngine(
            runs=cfg.simulation_runs,
            worst_case_floor=cfg.simulation_worst_case_floor,
        )
        self.circuit_breaker = circuit_breaker or CircuitBreaker(
            cfg.circuit_breaker_threshold,
            cfg.circuit_breaker_window_s,
            cfg.circuit_breaker_cooldown_s,
            min_principals=cfg.circuit_breaker_min_principals,
        )
        self.audit = audit_logger or AuditLogger(include_text=cfg.audit_include_text)
        self.extra_evaluators = list(extra_evaluators)
        self.policy_digest = sha256(json.dumps(cfg.to_policy_document(), sort_keys=True))

    # -- evaluator plumbing ---------------------------------------------------

    def _evaluators(self, phase: Phase) -> list[Evaluator]:
        core: list[Evaluator]
        if phase is Phase.PRE:
            core = [self.tier1_eval, self.tier3_eval, self.tier2_eval]
        else:
            core = [self.tier3_eval, self.tier2_eval]
            if self.judge_eval is not None:
                core.append(self.judge_eval)
        return core + [e for e in self.extra_evaluators if phase in e.phases]

    async def _safe_evaluate(self, ev: Evaluator, ctx: EvaluationContext) -> EvaluationResult:
        try:
            return await ev.evaluate(ctx)
        except Exception as exc:
            closed = (
                self.config.fail_closed or ev.tier is FrameworkTier.TIER_3_INVIOLABLE_HUMAN_FLOOR
            )
            logger.exception(
                "evaluator %s raised; failing %s", ev.name, "closed" if closed else "open"
            )
            return EvaluationResult(
                passed=not closed,
                failing_tier=ev.tier if closed else None,
                code="EVALUATOR_ERROR",
                evaluator=ev.name,
                reason=f"Evaluator {ev.name} raised {type(exc).__name__}.",
                metrics={"infrastructure_error": True},
            )

    async def _run_phase(
        self, ctx: EvaluationContext, results: list[EvaluationResult]
    ) -> EvaluationResult | None:
        for ev in self._evaluators(ctx.phase):
            result = await self._safe_evaluate(ev, ctx)
            results.append(result)
            if not result.passed:
                return result
        return None

    # -- decisions --------------------------------------------------------------

    def _base_metadata(self, ctx: EvaluationContext) -> dict[str, Any]:
        carbon = (
            ctx.carbon_intensity_g_kwh
            if ctx.carbon_intensity_g_kwh is not None
            else self.config.default_carbon_intensity_g_kwh
        )
        meta: dict[str, Any] = {
            "jurisdiction_id": self.config.jurisdiction_id,
            "cultural_framework": self.config.cultural_context.value,
            "circuit_breaker": self.circuit_breaker.state.value,
            "channels_screened": list(ctx.metadata.get("channels", ["text"])),
            "energy": {"estimated_kwh": ctx.estimated_kwh, "carbon_intensity_g_kwh": carbon},
            "community_action": ctx.affects_community or ctx.is_macro_policy_proposal,
            "consent_asserted": ctx.community_consent is True,
            "macro_policy": ctx.is_macro_policy_proposal,
        }
        if ctx.metadata.get("unscreened"):
            meta["unscreened"] = list(ctx.metadata["unscreened"])
        return meta

    def _flags(self, results: list[EvaluationResult]) -> dict[str, Any]:
        """Collect near-miss, review and judge signals for the KPIs and agents."""
        flags: dict[str, Any] = {}
        hits: set[str] = set()
        mitigations: set[str] = set()
        for r in results:
            m = r.metrics
            if m.get("near_miss"):
                flags["near_miss"] = True
            if m.get("review_flag"):
                flags["review_flag"] = True
            if m.get("infrastructure_error"):
                flags["infrastructure_error"] = True
            hits.update(m.get("lexical_hits", []))
            mitigations.update(m.get("mitigations", []))
            if isinstance(m.get("scores"), dict):
                flags["judge_scores"] = dict(m["scores"])
                limit = NEAR_MISS_FRACTION * self.config.judge_threshold
                if any(s is not None and s >= limit for s in m["scores"].values()):
                    flags["near_miss"] = True
        if hits:
            flags["lexical_hits"] = sorted(hits)
        if mitigations:
            flags["mitigations"] = sorted(mitigations)
        return flags

    def _finish(
        self,
        decision: GuardrailDecision,
        prompt: str,
        completion: str | None,
        ctx: EvaluationContext,
    ) -> GuardrailDecision:
        self.audit.record(
            decision,
            prompt=prompt,
            completion=completion,
            jurisdiction_id=self.config.jurisdiction_id,
            cultural_context=self.config.cultural_context.value,
            tenant=ctx.tenant,
            principal=ctx.principal,
            policy_digest=self.policy_digest,
            metadata=ctx.metadata,
        )
        return decision

    def _block(
        self,
        failure: EvaluationResult,
        results: list[EvaluationResult],
        prompt: str,
        completion: str | None,
        ctx: EvaluationContext,
        *,
        track: bool,
    ) -> GuardrailDecision:
        tier = failure.failing_tier
        level = (
            logging.WARNING
            if tier is not FrameworkTier.TIER_3_INVIOLABLE_HUMAN_FLOOR
            else logging.ERROR
        )
        logger.log(level, "GUARDRAIL BLOCK [%s:%s]", tier.value if tier else "?", failure.code)
        confirmed = is_confirmed_tier3(failure)
        if track and confirmed:
            self.circuit_breaker.record_violation(failure.code, principal=ctx.principal)
        metrics = failure.metrics if self.config.audit_include_text else redact(failure.metrics)
        decision = GuardrailDecision(
            status=Status.BLOCKED,
            tier=tier,
            reason=failure.reason,
            code=failure.code,
            results=results,
            governance_metadata={
                **self._base_metadata(ctx),
                **self._flags(results),
                "evaluator": failure.evaluator,
                "confirmed_tier3": confirmed,
                **metrics,
            },
        )
        return self._finish(decision, prompt, completion, ctx)

    def _refuse(
        self, ctx: EvaluationContext, tier: FrameworkTier, code: str, reason: str
    ) -> GuardrailDecision:
        failure = EvaluationResult(
            passed=False, failing_tier=tier, code=code, evaluator="guardrail", reason=reason
        )
        return self._block(failure, [failure], ctx.prompt, None, ctx, track=False)

    # -- public API ---------------------------------------------------------------

    def _context(
        self,
        prompt: str,
        *,
        estimated_kwh: float | None,
        current_carbon_g_kwh: float | None,
        is_macro_policy_proposal: bool,
        water_liters: float,
        affects_community: bool,
        community_consent: bool | None,
        metadata: dict[str, Any] | None,
        principal: str | None,
        tenant: str | None,
    ) -> EvaluationContext:
        return EvaluationContext(
            prompt=prompt,
            estimated_kwh=self.config.default_job_kwh if estimated_kwh is None else estimated_kwh,
            carbon_intensity_g_kwh=current_carbon_g_kwh,
            water_liters=water_liters,
            is_macro_policy_proposal=is_macro_policy_proposal,
            affects_community=affects_community,
            community_consent=community_consent,
            metadata=dict(metadata or {}),
            principal=principal,
            tenant=tenant,
        )

    async def inspect_and_execute(
        self,
        prompt: str,
        model_completion_func: CompletionFn,
        estimated_kwh: float | None = None,
        current_carbon_g_kwh: float | None = None,
        is_macro_policy_proposal: bool = False,
        *,
        water_liters: float = 0.0,
        affects_community: bool = False,
        community_consent: bool | None = None,
        metadata: dict[str, Any] | None = None,
        principal: str | None = None,
        tenant: str | None = None,
    ) -> GuardrailDecision:
        """Guard one model call. Exceptions raised by ``model_completion_func`` propagate.

        Raises ``ValueError`` for non-finite or negative energy, carbon or water figures.
        Pass ``principal`` (a user, key or session id) so the circuit breaker can suspend
        an abusive caller without suspending everyone. ``metadata`` may carry the labels
        ``language``, ``topic``, ``region``, ``task_class``, ``cohort`` and
        ``target_group`` for KPI breakdowns, and ``channels`` (set by the adapters).
        """
        ctx = self._context(
            prompt,
            estimated_kwh=estimated_kwh,
            current_carbon_g_kwh=current_carbon_g_kwh,
            is_macro_policy_proposal=is_macro_policy_proposal,
            water_liters=water_liters,
            affects_community=affects_community,
            community_consent=community_consent,
            metadata=metadata,
            principal=principal,
            tenant=tenant,
        )
        return await self._execute(prompt, model_completion_func, ctx, track=True)

    async def check_text(
        self,
        prompt: str,
        completion: str,
        *,
        is_macro_policy_proposal: bool = False,
        affects_community: bool = False,
        community_consent: bool | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> GuardrailDecision:
        """Evaluate an existing prompt/completion pair **offline**.

        Spends no energy budget and never touches the circuit breaker, so it must not be
        used as a runtime gate for live traffic (review AR-26).
        """

        async def fixed(_: str) -> str:
            return completion

        ctx = self._context(
            prompt,
            estimated_kwh=0.0,
            current_carbon_g_kwh=None,
            is_macro_policy_proposal=is_macro_policy_proposal,
            water_liters=0.0,
            affects_community=affects_community,
            community_consent=community_consent,
            metadata=metadata,
            principal=None,
            tenant=None,
        )
        return await self._execute(prompt, fixed, ctx, track=False)

    def block_unscreenable(
        self,
        prompt: str,
        kinds: Sequence[str],
        *,
        principal: str | None = None,
        tenant: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> GuardrailDecision:
        """Refuse a request containing content the guardrail cannot inspect (review AR-01)."""
        ctx = self._context(
            prompt,
            estimated_kwh=0.0,
            current_carbon_g_kwh=None,
            is_macro_policy_proposal=False,
            water_liters=0.0,
            affects_community=False,
            community_consent=None,
            metadata=metadata,
            principal=principal,
            tenant=tenant,
        )
        return self._refuse(
            ctx,
            FrameworkTier.INPUT_LIMITS,
            "UNSCREENABLE_CONTENT",
            f"Request contains content the guardrail cannot inspect ({', '.join(sorted(set(kinds)))}); "
            "blocked by policy (unscreenable_content='block').",
        )

    def record_actual_energy(
        self,
        decision: GuardrailDecision,
        actual_kwh: float,
        *,
        tenant: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Reconcile the budget with metered energy for a completed call (review AR-05)."""
        if (
            not isinstance(actual_kwh, (int, float))
            or not math.isfinite(actual_kwh)
            or actual_kwh < 0
        ):
            raise ValueError(f"actual_kwh must be finite and >= 0, got {actual_kwh!r}")
        energy = decision.governance_metadata.setdefault("energy", {})
        estimated = float(energy.get("estimated_kwh", 0.0))
        # Reconcile against what the budget currently holds for this decision: the last
        # metered figure if there is one, otherwise the estimate reserved up front.
        delta = actual_kwh - float(energy.get("actual_kwh", estimated))
        if delta > 0:
            self.budget.consume(delta)
        elif delta < 0:
            self.budget.refund(-delta)
        energy["actual_kwh"] = actual_kwh
        self.audit.record_energy(
            decision.audit_id,
            estimated_kwh=estimated,
            actual_kwh=actual_kwh,
            jurisdiction_id=self.config.jurisdiction_id,
            cultural_context=self.config.cultural_context.value,
            tenant=tenant,
            metadata=metadata,
        )

    # -- the pipeline -------------------------------------------------------------

    async def _execute(
        self,
        prompt: str,
        model_completion_func: CompletionFn,
        ctx: EvaluationContext,
        *,
        track: bool,
    ) -> GuardrailDecision:
        cfg = self.config
        results: list[EvaluationResult] = []

        if len(prompt) > cfg.max_input_chars:
            return self._refuse(
                ctx,
                FrameworkTier.INPUT_LIMITS,
                "INPUT_TOO_LARGE",
                f"Prompt exceeds the {cfg.max_input_chars}-character limit.",
            )

        if track:
            admission = self.circuit_breaker.admit(ctx.principal)
            if admission is Admission.GLOBAL_OPEN:
                # Generic on purpose: never show one user another user's violation (AR-11).
                return self._refuse(
                    ctx,
                    FrameworkTier.CIRCUIT_BREAKER,
                    "CIRCUIT_OPEN",
                    "The system is temporarily suspended by its automated circuit breaker "
                    "(Art. 7(2)). Please try again later.",
                )
            if admission is Admission.PRINCIPAL_SUSPENDED:
                return self._refuse(
                    ctx,
                    FrameworkTier.CIRCUIT_BREAKER,
                    "PRINCIPAL_SUSPENDED",
                    "Your access is temporarily suspended after repeated violations. "
                    "You may contest this decision.",
                )

        # PRE: nothing has been spent yet; these blocks never count toward the breaker.
        failure = await self._run_phase(ctx, results)
        if failure:
            return self._block(failure, results, prompt, None, ctx, track=False)

        reserved = ctx.estimated_kwh
        if cfg.resource_exhaustion_circuit_breaker:
            if not self.budget.try_consume(reserved):
                failure = self.tier1_eval._fail(
                    "RESOURCE_BUDGET_EXHAUSTED",
                    f"Cumulative budget of {self.budget.limit_kwh} kWh exhausted by "
                    "concurrent requests.",
                )
                results.append(failure)
                return self._block(failure, results, prompt, None, ctx, track=False)
        else:
            self.budget.consume(reserved)

        try:
            raw = await model_completion_func(prompt)
        except Exception as exc:
            # No compute delivered: refund, and keep the audit trail complete (AR-12).
            self.budget.refund(reserved)
            error = GuardrailDecision(
                status=Status.ERROR,
                code="MODEL_ERROR",
                reason=f"The model call failed ({type(exc).__name__}).",
                results=results,
                governance_metadata=self._base_metadata(ctx),
            )
            self.audit.record(
                error,
                prompt=prompt,
                completion=None,
                jurisdiction_id=cfg.jurisdiction_id,
                cultural_context=cfg.cultural_context.value,
                tenant=ctx.tenant,
                principal=ctx.principal,
                policy_digest=self.policy_digest,
                metadata=ctx.metadata,
                kind="model_error",
            )
            raise
        completion = raw if isinstance(raw, str) else str(raw)
        if len(completion) > cfg.max_input_chars:
            return self._refuse(
                ctx,
                FrameworkTier.INPUT_LIMITS,
                "OUTPUT_TOO_LARGE",
                f"Model output exceeds the {cfg.max_input_chars}-character limit.",
            )

        # POST: judge what the model actually produced.
        post_ctx = dataclasses.replace(ctx, completion=completion, phase=Phase.POST)
        failure = await self._run_phase(post_ctx, results)
        if failure:
            return self._block(failure, results, prompt, completion, ctx, track=track)

        capability = None
        if self.capability_eval is not None:
            cap = await self.capability_eval.evaluate(post_ctx)  # never blocks
            capability = cap.metrics.get("capability")

        t1_metrics = results[0].metrics if results else {}
        seed = compute_seed_stock(
            completion,
            t1_metrics.get("kwh_utilisation", 0.0),
            t1_metrics.get("carbon_utilisation", 0.0),
            t1_metrics.get("water_utilisation", 0.0),
        )
        floor = cfg.min_seed_stock_score
        if floor is not None and seed.aggregate < floor:
            pillar, score = seed.weakest
            failure = EvaluationResult(
                passed=False,
                failing_tier=PILLAR_TIER[pillar],
                code="SEED_STOCK_DEPLETION",
                evaluator="seed_stock",
                reason=(
                    f"Seed-Stock floor breached: {pillar} score {score:.2f} is below the "
                    f"policy minimum {floor:.2f}."
                ),
                metrics={"seed_stock": seed.as_dict(), "infrastructure_error": False},
            )
            results.append(failure)
            # A lexical metric is not a confirmed violation: never counts to the breaker.
            return self._block(failure, results, prompt, completion, ctx, track=False)

        simulation: dict[str, Any] | None = None
        if ctx.is_macro_policy_proposal and cfg.require_simulation_for_macro_policy:
            report = await self.simulation_engine.simulate(completion)
            simulation = report.as_dict()
            if not report.passed:
                failure = EvaluationResult(
                    passed=False,
                    failing_tier=FrameworkTier.SILICON_SIMULATION,
                    code="SIMULATION_FAILED",
                    evaluator="silicon_simulation",
                    reason=report.message,
                    metrics={"simulation": simulation},
                )
                results.append(failure)
                return self._block(failure, results, prompt, completion, ctx, track=False)

        if track:
            self.circuit_breaker.record_success()
        governance: dict[str, Any] = {
            "tier_1": "PASS",
            "tier_2": "PASS",
            "tier_3": "PASS",
            **self._base_metadata(ctx),
            **self._flags(results),
            "seed_stock": seed.as_dict(),
            "policy_like": looks_like_policy(completion),
        }
        governance["energy"].update(
            budget_used_kwh=self.budget.used_kwh,
            budget_remaining_kwh=self.budget.remaining_kwh,
        )
        if self.judge_eval is not None:
            governance["judge"] = "PASS"
        if capability is not None:
            governance["capability"] = capability
        if simulation is not None:
            governance["simulation"] = simulation
        decision = GuardrailDecision(
            status=Status.APPROVED,
            completion=completion,
            results=results,
            governance_metadata=governance,
        )
        return self._finish(decision, prompt, completion, ctx)


SeedFirstMiddleware = SeedFirstGuardrailProxy
