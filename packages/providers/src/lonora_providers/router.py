"""Model routing with classified recovery across an ordered candidate chain.

Candidates: the model a Run was started with (a subagent's chosen model), the
Agent's own primary model (the owner's assignment, or Lonora's model it inherited),
the global route for the capability, the Agent's fallbacks, then the global backups.
Each candidate
is admitted against its own window, retried a bounded number of times for
transient failures (honouring a short ``Retry-After``), corrected once when its
output budget is rejected or cut off, and benched for a short period when it
gives up so later requests skip it. Nothing here repeats tool calls or external
effects: a model request has none, and a reply whose tool input was cut off is
never returned.
"""

import asyncio
import logging
import random
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from time import monotonic

from lonora_adapter_kit.model import ModelAdapter
from lonora_adapter_kit.model_errors import FailureReason, ModelProviderError
from lonora_adapter_kit.types import ModelMessage, ModelReply, ToolDefinition
from lonora_contracts.model_catalog import ModelDescriptor
from lonora_contracts.model_context import UNKNOWN_OUTPUT_TOKENS, ModelContextPolicy
from lonora_contracts.model_routing import (
    TEXT_CAPABILITIES,
    AgentModelRecord,
    Capability,
    ModelSelection,
    RoutingPolicy,
)
from lonora_core.model_routing import select_model
from lonora_core.user_error import LonoraError
from lonora_db.agent_models import agent_model_preference
from lonora_db.client import Database
from lonora_db.transactions import SettingsRepository

from .context import (
    ContextLimits,
    PreparedContext,
    context_limits,
    output_ceiling,
    prepare_context,
)
from .credentials import ProviderCredentials
from .default_model import choose_default_model
from .registry import build_adapter, model_adapter
from .resilience import (
    MAXIMUM_INLINE_WAIT_SECONDS,
    RECOVERY,
    ProviderHealth,
    backoff_delay,
    classified,
    credential_fingerprint,
)

log = logging.getLogger("lonora.model_router")

# Distinct candidates one request may try, primary included.
MAXIMUM_CANDIDATES = 6
# After no default model could be chosen, how long before the providers are asked again.
UNCHOOSABLE_SECONDS = 60.0
# A request without streaming keeps its budget where an HTTP read cannot stall.
NON_STREAM_OUTPUT_TOKENS = 16384
NON_STREAM_BOOST_TOKENS = 32768
# The smallest budget a correction may set after a provider rejects one.
MINIMUM_OUTPUT_TOKENS = 128
_TEXT_CAPABILITIES = frozenset(
    {Capability.CONVERSATION, Capability.REASONING, Capability.RESEARCH, Capability.BACKGROUND}
)


@dataclass(frozen=True)
class Route:
    choices: list[ModelSelection]
    policy: ModelContextPolicy
    catalogs: dict[str, list[ModelDescriptor]]

    def descriptor(self, selection: ModelSelection) -> ModelDescriptor | None:
        return next(
            (
                item
                for item in self.catalogs.get(selection.provider, [])
                if item.id == selection.model and item.provider == selection.provider
            ),
            None,
        )


def agent_route_applies(capability: Capability, descriptor: ModelDescriptor | None) -> bool:
    """Whether an Agent's own model serves this capability.

    Text capabilities always use it. Vision uses it unless the catalog verifies
    the model as text-only; speech keeps its dedicated global routes.
    """
    if capability in _TEXT_CAPABILITIES:
        return True
    if capability is Capability.VISION:
        return not (descriptor and descriptor.verified and "vision" not in descriptor.capabilities)
    return False


def boosted_output(
    current: int,
    ceiling: int | None,
    prepared: PreparedContext,
    *,
    streaming: bool,
) -> int | None:
    """A larger budget for one retry after a cut-off reply, or ``None``.

    Double the budget (at least 8192), never above the model's documented
    maximum (twice the unknown-model cap when none is known) nor what the
    window leaves after the admitted input.
    """
    target = max(current * 2, 8192)
    target = min(target, ceiling or UNKNOWN_OUTPUT_TOKENS * 2)
    window = prepared.diagnostics.get("context_window")
    estimated = prepared.diagnostics.get("estimated_input_tokens")
    safety = prepared.diagnostics.get("safety_tokens") or 0
    if isinstance(window, int) and isinstance(estimated, int):
        target = min(target, window - estimated - int(safety))
    if not streaming:
        target = min(target, NON_STREAM_BOOST_TOKENS)
    return target if target > current else None


class GlobalModelRouter:
    def __init__(
        self,
        db: Database,
        credentials: ProviderCredentials,
        factory: Callable[..., ModelAdapter] = model_adapter,
        *,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        clock: Callable[[], float] = monotonic,
        jitter: Callable[[], float] = random.random,
    ):
        self.db, self.credentials, self.factory = db, credentials, factory
        self.sleep, self.jitter = sleep, jitter
        self.health = ProviderHealth(clock)
        self.choosing = asyncio.Lock()
        self.clock, self.unchoosable_until = clock, 0.0

    async def route(
        self,
        capability: Capability,
        *,
        owner_id: str | None = None,
        agent_id: str | None = None,
        choices: Sequence[ModelSelection] | None = None,
        run_choice: ModelSelection | None = None,
    ) -> Route:
        """The ordered, de-duplicated candidates for one request.

        ``run_choice`` is the model a Run was started with; it leads the Agent's own
        chain, which stays behind it as the fallback.
        """
        record: AgentModelRecord | None = None
        async with self.db.sessions() as session:
            settings = SettingsRepository()
            policy = ModelContextPolicy.model_validate(await settings.get(session, "model_context"))
            if choices is not None:
                ordered = list(choices)
            else:
                routing = RoutingPolicy.model_validate(await settings.get(session, "model_routing"))
                try:
                    primary: ModelSelection | None = select_model(routing, capability)
                except LonoraError as error:
                    if error.code != "model_not_configured":
                        raise
                    primary = None
                backups = await settings.get(session, "model_backups")
                if owner_id and agent_id:
                    record = await agent_model_preference(session, owner_id, agent_id)
                preference = record.preference if record else None
                ordered = [
                    *([run_choice] if run_choice else []),
                    *([preference.primary] if preference and preference.primary else []),
                    *([primary] if primary else []),
                    *(preference.fallbacks if preference else []),
                    *(ModelSelection.model_validate(item) for item in backups.get("choices", [])),
                ]
            catalogs: dict[str, list[ModelDescriptor]] = {}
            for provider in dict.fromkeys(item.provider for item in ordered):
                payload = await settings.get(session, "catalog:" + provider)
                catalogs[provider] = [
                    ModelDescriptor.model_validate(item) for item in payload.get("models", [])
                ]
        route = Route([], policy, catalogs)
        owned: set[tuple[str, str]] = set()
        if record:
            chosen = [record.preference.primary, *record.preference.fallbacks]
            owned = {(item.provider, item.model) for item in chosen if item}
        if run_choice:
            owned.add((run_choice.provider, run_choice.model))
        seen: set[tuple[str, str]] = set()
        for selection in ordered:
            identity = (selection.provider, selection.model)
            if identity in seen:
                continue
            if identity in owned and not agent_route_applies(
                capability, route.descriptor(selection)
            ):
                continue
            seen.add(identity)
            route.choices.append(selection)
        del route.choices[MAXIMUM_CANDIDATES:]
        if not route.choices:
            raise LonoraError("model_not_configured", 409)
        return route

    async def usable_route(
        self,
        capability: Capability,
        *,
        owner_id: str | None = None,
        agent_id: str | None = None,
        choices: Sequence[ModelSelection] | None = None,
        run_choice: ModelSelection | None = None,
    ) -> Route:
        """``route`` for a request that is about to be made. When text work has no model
        at all and a provider key exists, the default is chosen and recorded once
        (``default_model``), so a new installation answers without a routing setting."""
        try:
            return await self.route(
                capability,
                owner_id=owner_id,
                agent_id=agent_id,
                choices=choices,
                run_choice=run_choice,
            )
        except LonoraError as error:
            if (
                error.code != "model_not_configured"
                or choices is not None
                or capability not in TEXT_CAPABILITIES
            ):
                raise
        async with self.choosing:
            try:
                # Another request chose while this one waited.
                return await self.route(
                    capability, owner_id=owner_id, agent_id=agent_id, run_choice=run_choice
                )
            except LonoraError as error:
                if error.code != "model_not_configured" or self.clock() < self.unchoosable_until:
                    raise
            if await choose_default_model(self.db, self.credentials, self.factory) is None:
                # Nothing to choose: do not ask the providers again on every request.
                self.unchoosable_until = self.clock() + UNCHOOSABLE_SECONDS
        return await self.route(
            capability, owner_id=owner_id, agent_id=agent_id, run_choice=run_choice
        )

    async def context_limits(
        self,
        capability: Capability,
        *,
        owner_id: str | None = None,
        agent_id: str | None = None,
        input_scale: float = 1.0,
        run_choice: ModelSelection | None = None,
    ) -> ContextLimits:
        """Admission limits of the model ``complete`` tries first for ``capability``.

        Runtime compaction plans against these; every attempt, fallbacks included,
        is still admitted separately against its own window.
        """
        route = await self.usable_route(
            capability, owner_id=owner_id, agent_id=agent_id, run_choice=run_choice
        )
        choice = route.choices[0]
        return context_limits(
            route.descriptor(choice),
            route.policy,
            provider=choice.provider,
            model=choice.model,
            input_scale=input_scale,
        )

    async def complete(
        self,
        capability: Capability,
        messages: list[ModelMessage],
        tools: list[ToolDefinition],
        *,
        on_delta: Callable[[str], Awaitable[None]] | None = None,
        on_attempt: Callable[[ModelSelection], Awaitable[None]] | None = None,
        owner_id: str | None = None,
        agent_id: str | None = None,
        input_scale: float = 1.0,
        choices: Sequence[ModelSelection] | None = None,
        run_choice: ModelSelection | None = None,
    ) -> tuple[ModelReply, ModelSelection]:
        """One model reply from the first candidate that can give one.

        ``choices`` replaces the routed chain (a consultation names its model);
        ``run_choice`` leads it (a subagent started on a chosen model); ``input_scale``
        tightens admission after a provider-proven overflow.
        """
        started = monotonic()
        route = await self.usable_route(
            capability,
            owner_id=owner_id,
            agent_id=agent_id,
            choices=choices,
            run_choice=run_choice,
        )
        routing_ms = round((monotonic() - started) * 1000, 2)
        failures: list[tuple[ModelSelection, ModelProviderError]] = []
        waits: list[float] = []
        for index, selection in enumerate(route.choices):
            alone = index == len(route.choices) - 1
            credentials_started = monotonic()
            try:
                secret = await self.credentials.resolve(selection.provider)
            except LonoraError as error:
                if error.code != "model_not_configured":
                    raise
                failures.append((selection, ModelProviderError(FailureReason.NOT_CONFIGURED)))
                continue
            endpoint = await self.credentials.endpoint(selection.provider)
            # A new base URL is a new credential: its health starts fresh.
            fingerprint = credential_fingerprint(secret + "\n" + endpoint if endpoint else secret)
            bench = self.health.benched(selection, fingerprint)
            if bench is not None:
                state, remaining = bench
                failures.append(
                    (selection, ModelProviderError(state.reason, retry_after=remaining))
                )
                if RECOVERY[state.reason].transient:
                    waits.append(remaining)
                continue
            adapter = build_adapter(self.factory, selection.provider, secret, endpoint)
            credentials_ms = round((monotonic() - credentials_started) * 1000, 2)
            try:
                reply = await self._complete_with(
                    adapter,
                    selection,
                    route,
                    messages,
                    tools,
                    alone=alone,
                    input_scale=input_scale,
                    on_delta=on_delta,
                    on_attempt=on_attempt,
                    timings={
                        "routing_configuration_ms": routing_ms,
                        "credentials_and_adapter_ms": credentials_ms,
                    },
                    started=started,
                )
            except LonoraError as raw:
                error = classified(raw)
                if error is None:
                    raise
                recovery = RECOVERY[error.reason]
                seconds = self.health.record_failure(selection, fingerprint, error)
                log.warning(
                    "model_candidate_failed provider=%s reason=%s status=%s benched_seconds=%s",
                    selection.provider,
                    error.reason.value,
                    error.http_status,
                    round(seconds, 1),
                )
                failures.append((selection, error))
                if recovery.transient:
                    waits.append(max(error.retry_after or 0.0, seconds))
                if not recovery.fallback:
                    raise error from None
                continue
            finally:
                await adapter.close()
            self.health.record_success(selection, fingerprint)
            if failures:
                reply.provider_metadata["route_failures"] = [
                    {
                        "provider": failed.provider,
                        "model": failed.model,
                        "reason": error.reason.value,
                    }
                    for failed, error in failures
                ]
            return reply, selection
        raise self._exhausted(failures, waits)

    def _exhausted(
        self, failures: list[tuple[ModelSelection, ModelProviderError]], waits: list[float]
    ) -> ModelProviderError:
        """The failure that best describes an exhausted chain.

        A transient failure wins (the Run backs off and the chain may recover),
        carrying the shortest wait after which a candidate leaves its bench;
        otherwise the first real failure, never a merely unconfigured backup.
        """
        errors = [error for _, error in failures]
        transient = [error for error in errors if RECOVERY[error.reason].transient]
        if transient:
            first = transient[0]
            positive = [wait for wait in waits if wait > 0]
            return ModelProviderError(
                first.reason,
                http_status=first.http_status,
                retry_after=min(positive) if positive else first.retry_after,
                provider_type=first.diagnostic_type,
            )
        configured = [error for error in errors if error.reason is not FailureReason.NOT_CONFIGURED]
        if configured:
            return configured[0]
        return ModelProviderError(FailureReason.NOT_CONFIGURED)

    def _retry_wait(self, error: ModelProviderError, attempt: int) -> float | None:
        if error.retry_after is not None:
            if error.retry_after > MAXIMUM_INLINE_WAIT_SECONDS:
                return None
            return error.retry_after + self.jitter() * min(1.0, error.retry_after * 0.1)
        return backoff_delay(attempt, self.jitter)

    async def _complete_with(
        self,
        adapter: ModelAdapter,
        selection: ModelSelection,
        route: Route,
        messages: list[ModelMessage],
        tools: list[ToolDefinition],
        *,
        alone: bool,
        input_scale: float,
        on_delta: Callable[[str], Awaitable[None]] | None,
        on_attempt: Callable[[ModelSelection], Awaitable[None]] | None,
        timings: dict[str, float],
        started: float,
    ) -> ModelReply:
        descriptor = route.descriptor(selection)
        preparing = monotonic()
        # Rebuild from the original working messages for EVERY candidate.
        prepared = prepare_context(
            messages,
            tools,
            descriptor,
            route.policy,
            provider=selection.provider,
            model=selection.model,
            input_scale=input_scale,
        )
        context_ms = round((monotonic() - preparing) * 1000, 2)
        output = prepared.output_tokens
        ceiling = output_ceiling(descriptor, selection.model)
        learned = self.health.output_cap(selection)
        if learned is not None:
            output = min(output, learned)
            ceiling = min(ceiling, learned) if ceiling else learned
        if on_delta is None:
            output = min(output, NON_STREAM_OUTPUT_TOKENS)
        recovery_attempts: list[str] = []
        retries = 0
        boosted = corrected = False
        while True:
            admission_started = monotonic()
            if on_attempt:
                await on_attempt(selection)
            admission_ms = round((monotonic() - admission_started) * 1000, 2)
            provider_started = monotonic()
            provider_first_text_ms: float | None = None

            async def observed_delta(chunk: str, request_started: float = provider_started) -> None:
                nonlocal provider_first_text_ms
                if chunk and provider_first_text_ms is None:
                    provider_first_text_ms = round((monotonic() - request_started) * 1000, 2)
                if on_delta:
                    await on_delta(chunk)

            try:
                reply = await adapter.complete(
                    selection.model,
                    prepared.messages,
                    tools,
                    max_output_tokens=output,
                    on_delta=observed_delta if on_delta else None,
                )
            except LonoraError as raw:
                error = classified(raw)
                if error is None:
                    raise
                if error.reason is FailureReason.TRUNCATED and not boosted:
                    larger = boosted_output(
                        output, ceiling, prepared, streaming=on_delta is not None
                    )
                    if larger is not None:
                        boosted, output = True, larger
                        recovery_attempts.append("output_boosted")
                        continue
                if error.reason is FailureReason.OUTPUT_LIMIT and not corrected:
                    limit = error.output_limit or output // 2
                    if MINIMUM_OUTPUT_TOKENS <= limit < output:
                        corrected, output = True, limit
                        ceiling = min(ceiling, limit) if ceiling else limit
                        self.health.learn_output_cap(selection, limit)
                        recovery_attempts.append("output_corrected")
                        continue
                recovery = RECOVERY[error.reason]
                allowed = recovery.retries_alone if alone else recovery.retries
                wait = self._retry_wait(error, retries + 1)
                if retries < allowed and wait is not None:
                    retries += 1
                    recovery_attempts.append("retried_" + error.reason.value)
                    await self.sleep(wait)
                    continue
                raise error from None
            if reply.provider_metadata.get("output_truncated") and not boosted:
                larger = boosted_output(output, ceiling, prepared, streaming=on_delta is not None)
                if larger is not None:
                    boosted, output = True, larger
                    recovery_attempts.append("output_boosted")
                    continue
            reply.provider_metadata["request_timings"] = {
                **timings,
                "context_preparation_ms": context_ms,
                "generation_admission_ms": admission_ms,
                "provider_first_text_ms": provider_first_text_ms,
                "provider_request_ms": round((monotonic() - provider_started) * 1000, 2),
                "router_total_ms": round((monotonic() - started) * 1000, 2),
            }
            reply.provider_metadata["context_budget"] = {
                **prepared.diagnostics,
                "requested_output_tokens": output,
                "actual_input_tokens": reply.usage.input_tokens or None,
                "actual_output_tokens": reply.usage.output_tokens or None,
            }
            if recovery_attempts:
                reply.provider_metadata["provider_recovery"] = recovery_attempts
            return reply
