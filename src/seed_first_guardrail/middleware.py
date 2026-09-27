"""SeedFirstGuardrailProxy -- the unified guardrail around a model call.

Request flow (each step short-circuits on the first failure):

    circuit breaker open?                       -> BLOCKED (CIRCUIT_BREAKER)
    PRE  : Tier 1 budget -> Tier 3 prompt screen -> Tier 2 consent
           (PRE blocks reject the request; they do not count toward the breaker)
    reserve energy budget
    call the model
    POST : Tier 3 completion screen -> Tier 2 rule packs -> LLM judge -> extras
    Seed-Stock floor (if configured)
    Silicon simulation (macro-policy proposals)
    -> APPROVED

Only violations in what the model *produced* (POST, Seed-Stock floor,
simulation) count toward the circuit breaker (Art. 7(2)).

Cheap, pre-execution checks run first so a doomed request spends no compute.
Normative precedence (Tier 3 > Tier 1 > Tier 2) is enforced by the fact that
every tier is a hard constraint: nothing downstream can override a block.
"""

from __future__ import annotations

import dataclasses
import logging
from collections.abc import Awaitable, Callable, Sequence
from typing import Any

from .audit import AuditLogger
from .circuit_breaker import CircuitBreaker
from .config import PolicyConfig
from .evaluators.base import Evaluator
from .evaluators.judge import JudgeFn, LLMJudgeEvaluator
from .evaluators.tier1 import ComputeBudget, Tier1PlanetaryEvaluator
from .evaluators.tier2 import Tier2CommunityEvaluator
from .evaluators.tier3 import Tier3InviolableEvaluator
from .metrics import PILLAR_TIER, compute_seed_stock
from .simulation import SiliconSimulationEngine
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
    ) -> None:
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
        )
        self.tier3_eval = Tier3InviolableEvaluator(screen_prompts=cfg.screen_prompts)
        if judge is None or isinstance(judge, LLMJudgeEvaluator):
            self.judge_eval = judge
        else:
            self.judge_eval = LLMJudgeEvaluator(
                judge,
                context=cfg.cultural_context,
                threshold=cfg.judge_threshold,
                fail_closed=cfg.fail_closed,
            )
        self.simulation_engine = simulation_engine or SiliconSimulationEngine(
            runs=cfg.simulation_runs, worst_case_floor=cfg.simulation_worst_case_floor
        )
        self.circuit_breaker = circuit_breaker or CircuitBreaker(
            cfg.circuit_breaker_threshold,
            cfg.circuit_breaker_window_s,
            cfg.circuit_breaker_cooldown_s,
        )
        self.audit = audit_logger or AuditLogger(include_text=cfg.audit_include_text)
        self.extra_evaluators = list(extra_evaluators)

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
                reason=f"Evaluator {ev.name} raised {type(exc).__name__}: {exc}",
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

    def _base_metadata(self) -> dict[str, Any]:
        return {
            "jurisdiction_id": self.config.jurisdiction_id,
            "cultural_framework": self.config.cultural_context.value,
            "circuit_breaker": self.circuit_breaker.state.value,
        }

    def _finish(
        self, decision: GuardrailDecision, prompt: str, completion: str | None
    ) -> GuardrailDecision:
        self.audit.record(
            decision,
            prompt=prompt,
            completion=completion,
            jurisdiction_id=self.config.jurisdiction_id,
            cultural_context=self.config.cultural_context.value,
        )
        return decision

    def _block(
        self,
        failure: EvaluationResult,
        results: list[EvaluationResult],
        prompt: str,
        completion: str | None,
        *,
        track: bool,
    ) -> GuardrailDecision:
        tier = failure.failing_tier
        level = logging.WARNING if tier is FrameworkTier.TIER_2_COMMUNITY else logging.ERROR
        logger.log(
            level,
            "GUARDRAIL BLOCK [%s:%s] %s",
            tier.value if tier else "?",
            failure.code,
            failure.reason,
        )
        if track:
            self.circuit_breaker.record_violation(f"{failure.code}: {failure.reason}")
        decision = GuardrailDecision(
            status=Status.BLOCKED,
            tier=tier,
            reason=failure.reason,
            code=failure.code,
            results=results,
            governance_metadata={
                **self._base_metadata(),
                "evaluator": failure.evaluator,
                **failure.metrics,
            },
        )
        return self._finish(decision, prompt, completion)

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
    ) -> GuardrailDecision:
        """Guard one model call. Exceptions raised by ``model_completion_func`` propagate."""
        return await self._execute(
            prompt,
            model_completion_func,
            EvaluationContext(
                prompt=prompt,
                estimated_kwh=self.config.default_job_kwh
                if estimated_kwh is None
                else estimated_kwh,
                carbon_intensity_g_kwh=current_carbon_g_kwh,
                water_liters=water_liters,
                is_macro_policy_proposal=is_macro_policy_proposal,
                affects_community=affects_community,
                community_consent=community_consent,
                metadata=dict(metadata or {}),
            ),
            track=True,
        )

    async def check_text(
        self,
        prompt: str,
        completion: str,
        *,
        is_macro_policy_proposal: bool = False,
        affects_community: bool = False,
        community_consent: bool | None = None,
    ) -> GuardrailDecision:
        """Evaluate an existing prompt/completion pair offline.

        Spends no energy budget and does not count toward the circuit breaker.
        """

        async def fixed(_: str) -> str:
            return completion

        return await self._execute(
            prompt,
            fixed,
            EvaluationContext(
                prompt=prompt,
                estimated_kwh=0.0,
                is_macro_policy_proposal=is_macro_policy_proposal,
                affects_community=affects_community,
                community_consent=community_consent,
            ),
            track=False,
        )

    async def _execute(
        self,
        prompt: str,
        model_completion_func: CompletionFn,
        ctx: EvaluationContext,
        *,
        track: bool,
    ) -> GuardrailDecision:
        results: list[EvaluationResult] = []

        if track and not self.circuit_breaker.allow_request():
            breaker = EvaluationResult(
                passed=False,
                failing_tier=FrameworkTier.CIRCUIT_BREAKER,
                code="CIRCUIT_OPEN",
                evaluator="circuit_breaker",
                reason=(
                    "System suspended by the automated circuit breaker (Art. 7(2)): "
                    f"{self.circuit_breaker.last_reason}"
                ),
            )
            return self._block(breaker, [breaker], prompt, None, track=False)

        # PRE: nothing has been spent yet. PRE blocks are caused by the *request*
        # (budget, consent, prompt), not by the model, so they never count toward
        # the circuit breaker -- otherwise any caller could suspend the system for
        # everyone by sending out-of-policy requests.
        failure = await self._run_phase(ctx, results)
        if failure:
            return self._block(failure, results, prompt, None, track=False)

        if self.config.resource_exhaustion_circuit_breaker:
            if not self.budget.try_consume(ctx.estimated_kwh):
                failure = self.tier1_eval._fail(
                    "RESOURCE_BUDGET_EXHAUSTED",
                    f"Cumulative budget of {self.budget.limit_kwh} kWh exhausted by "
                    "concurrent requests.",
                )
                results.append(failure)
                return self._block(failure, results, prompt, None, track=False)
        else:
            self.budget.consume(ctx.estimated_kwh)

        raw = await model_completion_func(prompt)
        completion = raw if isinstance(raw, str) else str(raw)

        # POST: judge what the model actually produced.
        post_ctx = dataclasses.replace(ctx, completion=completion, phase=Phase.POST)
        failure = await self._run_phase(post_ctx, results)
        if failure:
            return self._block(failure, results, prompt, completion, track=track)

        t1_metrics = results[0].metrics if results else {}
        seed = compute_seed_stock(
            completion,
            t1_metrics.get("kwh_utilisation", 0.0),
            t1_metrics.get("carbon_utilisation", 0.0),
            t1_metrics.get("water_utilisation", 0.0),
        )
        floor = self.config.min_seed_stock_score
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
                metrics={"seed_stock": seed.as_dict()},
            )
            results.append(failure)
            return self._block(failure, results, prompt, completion, track=track)

        simulation: dict[str, Any] | None = None
        if ctx.is_macro_policy_proposal and self.config.require_simulation_for_macro_policy:
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
                return self._block(failure, results, prompt, completion, track=track)

        if track:
            self.circuit_breaker.record_success()
        governance: dict[str, Any] = {
            "tier_1": "PASS",
            "tier_2": "PASS",
            "tier_3": "PASS",
            **self._base_metadata(),
            "seed_stock": seed.as_dict(),
            "energy": {
                "estimated_kwh": ctx.estimated_kwh,
                "budget_used_kwh": self.budget.used_kwh,
                "budget_remaining_kwh": self.budget.remaining_kwh,
            },
        }
        if self.judge_eval is not None:
            governance["judge"] = "PASS"
        if simulation is not None:
            governance["simulation"] = simulation
        decision = GuardrailDecision(
            status=Status.APPROVED,
            completion=completion,
            results=results,
            governance_metadata=governance,
        )
        return self._finish(decision, prompt, completion)


SeedFirstMiddleware = SeedFirstGuardrailProxy
