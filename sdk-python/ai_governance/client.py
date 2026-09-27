from __future__ import annotations

import functools
import inspect
import logging
import os
import uuid
from contextvars import ContextVar, Token
from dataclasses import dataclass, field as dataclass_field
from pathlib import Path
from typing import Any, Callable, TypeVar

from ai_governance.core import EventBuilder, SessionTracker, fingerprint, raw_text_problems, sanitize
from ai_governance.core.actions import (
    DEFAULT_ENFORCEMENT_MODE,
    EXECUTION_ERROR,
    MODE_OBSERVE,
    ActionRequest,
)
from ai_governance.core.decisions import (
    REASON_ALLOWED_BY_POLICY,
    VERDICT_ALLOW,
    VERDICT_DENY,
    VERDICT_REQUIRE_APPROVAL,
    Decision,
)
from ai_governance.enforcement import (
    ActionRecorder,
    Agent7Blocked,
    EnforcementPolicy,
    RemoteDecisionClient,
    authorize_action_local,
    blocked_result,
    build_action_record,
    build_action_request,
    enforce_decision,
    normalize_mode,
    resolve_endpoints,
    verify_approval_token,
)
from ai_governance.sinks import JsonlSink
from ai_governance.sinks.base import EventSink

logger = logging.getLogger(__name__)

F = TypeVar("F", bound=Callable[..., Any])

#: Reserved keyword argument used to hand a trusted approval to a governed call.
APPROVAL_KWARG = "agent7_approval"

ON_DENY_RETURN = "return"
ON_DENY_RAISE = "raise"
_ON_DENY_CHOICES = frozenset({ON_DENY_RETURN, ON_DENY_RAISE})

DEFAULT_ACTIONS_FILENAME = "governance-actions.jsonl"


@dataclass(frozen=True)
class _ActiveTrace:
    run_id: str
    name: str
    session_id: str
    user_id_hash: str | None
    tool_parent_run_id: str
    pin_tool_parent: bool = False


_ACTIVE_TRACE: ContextVar[_ActiveTrace | None] = ContextVar("ai_governance_active_trace", default=None)
_ACTIVE_APPROVAL: ContextVar[Any] = ContextVar("ai_governance_active_approval", default=None)


@dataclass(frozen=True)
class _ToolSpec:
    """Static governance metadata captured when a function is decorated."""

    tool_name: str
    action_type: str
    approval_required: bool | None
    data_classes: tuple[str, ...]
    external_side_effect: bool | None
    reversible: bool | None
    target: str | None
    session_id: str | None
    capability_id: str | None
    capability_status: str | None
    module_path: str | None
    enforcement_mode: str | None
    on_deny: str | None


@dataclass
class _ActionContext:
    """Per-call state shared by the sync and async wrappers."""

    spec: _ToolSpec
    run_id: str
    parent_run_id: str | None
    session_id: str | None
    user_id_hash: str | None
    safe_args: Any
    request: ActionRequest
    decision: Decision
    mode: str
    should_execute: bool
    execution_status: str
    would_have_blocked: bool
    records: bool
    event_ids: list[str] = dataclass_field(default_factory=list)


class GovernanceClient:
    """Framework-neutral event client for custom Python instrumentation."""

    def __init__(
        self,
        *,
        system_id: str,
        deployment_id: str = "local-test",
        environment: str = "local",
        agent_id: str | None = None,
        session_id: str | None = None,
        jsonl_path: str | Path = "governance-events.jsonl",
        api_endpoint: str | None = None,
        api_timeout_seconds: float = 0.5,
        sink: EventSink | None = None,
        source: dict[str, Any] | None = None,
        enforcement_mode: str = DEFAULT_ENFORCEMENT_MODE,
        on_deny: str = ON_DENY_RETURN,
        policy: EnforcementPolicy | None = None,
        record_decisions: bool = False,
        actions_jsonl_path: str | Path | None = None,
        decision_timeout_seconds: float = 1.0,
        remote_decisions: bool | None = None,
        decision_opener: Callable[..., Any] | None = None,
    ) -> None:
        """``decision_opener`` overrides the HTTP opener for both the decision
        endpoint and the action-record endpoint. It exists for testing."""
        if not system_id:
            raise ValueError("system_id must not be empty")
        self.system_id = system_id
        self.deployment_id = deployment_id
        self.environment = environment
        self.agent_id = agent_id or system_id
        self.session_id = session_id or f"{deployment_id}:default"
        self.dropped_events = 0
        endpoint = api_endpoint if api_endpoint is not None else os.environ.get("GOVERNANCE_API_ENDPOINT")
        events_endpoint, api_base = resolve_endpoints(endpoint)
        self.api_base = api_base
        self.sink = sink or JsonlSink(
            jsonl_path, api_endpoint=events_endpoint, api_timeout_seconds=api_timeout_seconds
        )

        # --- enforcement configuration -------------------------------------
        self.enforcement_mode = normalize_mode(enforcement_mode)
        if on_deny not in _ON_DENY_CHOICES:
            raise ValueError(f"on_deny must be one of {sorted(_ON_DENY_CHOICES)}, got {on_deny!r}")
        self.on_deny = on_deny
        self.policy = policy
        self.record_decisions = bool(record_decisions)
        self.decision_timeout_seconds = decision_timeout_seconds
        self._actions_jsonl_path = actions_jsonl_path
        self._recorder: ActionRecorder | None = None
        # Shared by the decision client and the action recorder; the test seam
        # for both enforcement HTTP calls.
        self._http_opener = decision_opener
        self.blocked_actions = 0

        if remote_decisions is None:
            remote_decisions = bool(api_base)
        self.remote_decisions = bool(remote_decisions)
        self.decision_client: RemoteDecisionClient | None = None
        if self.remote_decisions and api_base:
            self.decision_client = RemoteDecisionClient(
                api_base, timeout_seconds=decision_timeout_seconds, opener=decision_opener
            )
        self.tracker = SessionTracker(default_session_id=self.session_id)
        self.builder = EventBuilder(
            system_id=system_id,
            deployment_id=deployment_id,
            environment=environment,
            agent_id=self.agent_id,
            source=source or {"type": "custom_function_adapter", "library": "ai_governance", "library_version": "0.1"},
            tracker=self.tracker,
        )

    def trace(self, *, name: str, session_id: str | None = None, user_id: str | None = None) -> "TraceContext":
        active = _ACTIVE_TRACE.get()
        return TraceContext(
            client=self,
            name=name,
            session_id=session_id or (active.session_id if active is not None else self.session_id),
            user_id_hash=fingerprint(user_id) if user_id is not None else (active.user_id_hash if active is not None else None),
        )

    def active_context(self) -> dict[str, str | None]:
        active_trace = _ACTIVE_TRACE.get()
        if active_trace is None:
            return {"parent_run_id": None, "session_id": None, "user_id_hash": None}
        return {
            "parent_run_id": active_trace.tool_parent_run_id,
            "session_id": active_trace.session_id,
            "user_id_hash": active_trace.user_id_hash,
        }

    def request_context(
        self,
        *,
        name: str,
        session_id: str | None = None,
        user_id_hash: str | None = None,
        attributes: dict[str, Any] | None = None,
    ) -> "RequestContext":
        return RequestContext(
            client=self,
            name=name,
            session_id=session_id or self.session_id,
            user_id_hash=user_id_hash,
            attributes=attributes or {},
        )

    def openai_client(self, *args: Any, client: Any | None = None, **kwargs: Any) -> Any:
        from ai_governance.adapters.openai import OpenAIAdapter

        if client is None:
            try:
                from openai import OpenAI
            except ModuleNotFoundError as exc:
                raise ImportError(
                    "OpenAI adapter requires the optional 'openai' package. "
                    "Install it with: pip install openai"
                ) from exc
            client = OpenAI(*args, **kwargs)
        return OpenAIAdapter(self).install(client)

    def anthropic_client(self, *args: Any, client: Any | None = None, **kwargs: Any) -> Any:
        from ai_governance.adapters.anthropic import AnthropicAdapter

        if client is None:
            try:
                from anthropic import Anthropic
            except ModuleNotFoundError as exc:
                raise ImportError(
                    "Anthropic adapter requires the optional 'anthropic' package. "
                    "Install it with: pip install anthropic"
                ) from exc
            client = Anthropic(*args, **kwargs)
        return AnthropicAdapter(self).install(client)

    def emit(
        self,
        *,
        event_type: str,
        run_id: Any,
        parent_run_id: Any | None = None,
        status: str,
        component_kind: str,
        component_name: str | None,
        duration_ms: float | None = None,
        session_id: str | None = None,
        user_id_hash: str | None = None,
        **details: Any,
    ) -> dict[str, Any] | None:
        """Build and write one event. Fail-open by design."""
        try:
            context = {"metadata": {"session_id": session_id or self.session_id}}
            if user_id_hash is not None:
                details.setdefault(
                    "actor",
                    {"agent_id": self.agent_id, "identity_type": "logical_agent", "user_id_hash": user_id_hash},
                )
            event = self.builder.build(
                event_type=event_type,
                run_id=run_id,
                parent_run_id=parent_run_id,
                status=status,
                component_kind=component_kind,
                component_name=component_name,
                duration_ms=duration_ms,
                _callback_context=context,
                **details,
            )
            return self.sink.emit(event)
        except Exception:
            self.dropped_events += 1
            logger.warning("governance client emit failed", exc_info=True)
            return None

    # ------------------------------------------------------------------
    # Pre-execution enforcement
    # ------------------------------------------------------------------

    def approval(self, approval: Any) -> "ApprovalContext":
        """Attach a trusted approval to every governed call in this block."""
        return ApprovalContext(approval)

    def _get_recorder(self) -> ActionRecorder:
        """Build the action recorder lazily, so observe mode creates no file."""
        if self._recorder is None:
            path = self._actions_jsonl_path
            if path is None:
                sink_path = getattr(self.sink, "path", None)
                path = Path(sink_path).with_name(DEFAULT_ACTIONS_FILENAME) if sink_path else None
            self._recorder = ActionRecorder(
                jsonl_path=path,
                api_base=self.api_base,
                timeout_seconds=self.decision_timeout_seconds,
                opener=self._http_opener,
            )
        return self._recorder

    def authorize(
        self,
        request: ActionRequest,
        *,
        raw_arguments: dict[str, Any] | None = None,
        approval: Any = None,
    ) -> Decision:
        """Authorize one action against local policy and, if configured, the backend.

        Local policy is always evaluated and acts as a floor: the result is the
        more restrictive of the two verdicts. That matters because some rules
        exist only locally -- ``denied_argument_patterns`` inspects live
        argument values, which never leave the process -- so a backend ALLOW
        must not be able to wave them through. An unreachable backend likewise
        never downgrades a local DENY.
        """
        local = authorize_action_local(
            request, self.policy, raw_arguments=raw_arguments, approval=approval
        )
        if self.decision_client is None:
            return local
        remote = self.decision_client.evaluate(request)
        if remote is None:
            return local
        remote = self._apply_local_approval(remote, request, approval)
        return self._most_restrictive(local, remote)

    @staticmethod
    def _most_restrictive(local: Decision, remote: Decision) -> Decision:
        """Return whichever verdict blocks more. Ties go to the backend."""
        rank = {VERDICT_ALLOW: 0, VERDICT_REQUIRE_APPROVAL: 1, VERDICT_DENY: 2}
        return local if rank.get(local.verdict, 0) > rank.get(remote.verdict, 0) else remote

    @staticmethod
    def _apply_local_approval(decision: Decision, request: ActionRequest, approval: Any) -> Decision:
        """Release a backend hold when a verified approval is present locally.

        The approval token never leaves the process, so the backend cannot see
        it and always holds an approval-gated action. Only REQUIRE_APPROVAL is
        released this way -- a DENY is never upgraded.
        """
        if decision.verdict != VERDICT_REQUIRE_APPROVAL:
            return decision
        if not verify_approval_token(request, approval):
            return decision
        return Decision.from_dict(
            {
                **decision.to_dict(),
                "verdict": VERDICT_ALLOW,
                "reason": f"{decision.reason} (released by a verified local approval)",
                "reason_code": REASON_ALLOWED_BY_POLICY,
                "approval_required": True,
            },
            action_id=request.action_id,
        )

    def _begin_action(
        self, spec: _ToolSpec, func: Callable[..., Any], args: tuple[Any, ...], kwargs: dict[str, Any]
    ) -> _ActionContext:
        """Build the request, decide, and resolve what the wrapper should do."""
        run_id = str(uuid.uuid4())
        context = self.active_context()
        parent_run_id = context["parent_run_id"]
        event_session_id = spec.session_id or context["session_id"]
        user_id_hash = context["user_id_hash"]
        self.tracker.start(run_id, spec.tool_name)

        raw_arguments = self._raw_call_arguments(func, args, kwargs)
        safe_args = self._privacy_safe_value(sanitize(dict(raw_arguments)))
        mode = normalize_mode(spec.enforcement_mode or self.enforcement_mode)

        request = build_action_request(
            system_id=self.system_id,
            deployment_id=self.deployment_id,
            environment=self.environment,
            agent_id=self.agent_id,
            capability_name=spec.tool_name,
            enforcement_mode=mode,
            raw_arguments=raw_arguments,
            arguments_hash=fingerprint(safe_args),
            capability_id=spec.capability_id,
            capability_status=spec.capability_status,
            module_path=spec.module_path,
            action_type=spec.action_type,
            data_classes=list(spec.data_classes),
            external_side_effect=spec.external_side_effect,
            approval_required=spec.approval_required,
            session_id=event_session_id,
            parent_span_id=parent_run_id,
        )

        approval = _ACTIVE_APPROVAL.get()
        try:
            decision = self.authorize(request, raw_arguments=raw_arguments, approval=approval)
        except Exception:
            logger.warning("governance authorization failed; falling back to local", exc_info=True)
            decision = authorize_action_local(
                request, self.policy, raw_arguments=raw_arguments, approval=approval
            )

        should_execute, execution_status, would_have_blocked = enforce_decision(decision, mode)
        return _ActionContext(
            spec=spec,
            run_id=run_id,
            parent_run_id=parent_run_id,
            session_id=event_session_id,
            user_id_hash=user_id_hash,
            safe_args=safe_args,
            request=request,
            decision=decision,
            mode=mode,
            should_execute=should_execute,
            execution_status=execution_status,
            would_have_blocked=would_have_blocked,
            # Default observe mode records nothing: no decision events, no
            # action-record file. Existing evidence output stays byte-identical.
            records=self.record_decisions or mode != MODE_OBSERVE,
        )

    def _decision_block(self, ctx: _ActionContext) -> dict[str, Any]:
        return {
            "action_id": ctx.request.action_id,
            "decision_id": ctx.decision.decision_id,
            "verdict": ctx.decision.verdict,
            "reason_code": ctx.decision.reason_code,
            "reason": sanitize(ctx.decision.reason),
            "decided_by": ctx.decision.decided_by,
            "enforcement_mode": ctx.mode,
            "execution_status": ctx.execution_status,
            "would_have_blocked": ctx.would_have_blocked,
            "kill_switch_id": ctx.decision.kill_switch_id,
            "matched_pattern_id": ctx.decision.matched_pattern_id,
        }

    def _emit_decision_event(self, ctx: _ActionContext) -> None:
        """Emit an action_decision event. Never called in default observe mode."""
        event = self.emit(
            event_type="action_decision",
            run_id=ctx.run_id,
            parent_run_id=ctx.parent_run_id,
            status="success",
            component_kind="action",
            component_name=ctx.spec.tool_name,
            duration_ms=self.tracker.duration(ctx.run_id) if not ctx.should_execute else None,
            session_id=ctx.session_id,
            user_id_hash=ctx.user_id_hash,
            tool={
                "name": ctx.spec.tool_name,
                "action_type": ctx.spec.action_type,
                "arguments_hash": ctx.request.arguments_hash,
                "target": ctx.spec.target,
                "external_side_effect": ctx.spec.external_side_effect,
                "reversible": ctx.spec.reversible,
            },
            data={"classifications": list(ctx.spec.data_classes), "sources": [], "destinations": []},
            approval={
                "required": ctx.decision.approval_required,
                "granted": None,
                "policy_id": ctx.decision.policy_version_id,
            },
            decision=self._decision_block(ctx),
            _final=not ctx.should_execute,
        )
        self._collect_event_id(ctx, event)

    def _emit_tool_start(self, ctx: _ActionContext) -> None:
        event = self.emit(
            event_type="tool_start",
            run_id=ctx.run_id,
            parent_run_id=ctx.parent_run_id,
            status="started",
            component_kind="tool",
            component_name=ctx.spec.tool_name,
            session_id=ctx.session_id,
            user_id_hash=ctx.user_id_hash,
            tool={
                "name": ctx.spec.tool_name,
                "action_type": ctx.spec.action_type,
                "arguments_hash": ctx.request.arguments_hash,
                "sanitized_arguments": ctx.safe_args,
                "target": ctx.spec.target,
                "external_side_effect": ctx.spec.external_side_effect,
                "reversible": ctx.spec.reversible,
            },
            data={"classifications": list(ctx.spec.data_classes), "sources": [], "destinations": []},
            approval={"required": ctx.spec.approval_required, "granted": None, "policy_id": None},
            decision=self._decision_block(ctx),
        )
        self._collect_event_id(ctx, event)

    @staticmethod
    def _collect_event_id(ctx: _ActionContext, event: dict[str, Any] | None) -> None:
        if isinstance(event, dict) and event.get("event_id"):
            ctx.event_ids.append(str(event["event_id"]))

    def _record_action(
        self,
        ctx: _ActionContext,
        *,
        executed: bool,
        execution_status: str,
        duration_ms: float | None = None,
        error_type: str | None = None,
    ) -> None:
        if not ctx.records:
            return
        try:
            record = build_action_record(
                ctx.request,
                ctx.decision,
                executed=executed,
                execution_status=execution_status,
                would_have_blocked=ctx.would_have_blocked,
                duration_ms=duration_ms,
                error_type=error_type,
                event_ids=ctx.event_ids,
            )
            self._get_recorder().record(record)
        except Exception:
            logger.warning("governance action record failed", exc_info=True)

    def _blocked(self, ctx: _ActionContext) -> Any:
        """Handle a blocked action. The wrapped function is never called."""
        self.blocked_actions += 1
        self._emit_decision_event(ctx)
        self._record_action(
            ctx,
            executed=False,
            execution_status=ctx.execution_status,
            duration_ms=self.tracker.duration(ctx.run_id),
        )
        on_deny = ctx.spec.on_deny or self.on_deny
        if on_deny == ON_DENY_RAISE:
            raise Agent7Blocked(ctx.decision)
        return blocked_result(ctx.decision)

    def _start_execution(self, ctx: _ActionContext) -> None:
        if ctx.records and ctx.decision.verdict != VERDICT_ALLOW:
            self._emit_decision_event(ctx)
        self._emit_tool_start(ctx)

    def _finish_success(self, ctx: _ActionContext, result: Any) -> None:
        duration_ms = self.tracker.duration(ctx.run_id)
        event = self.emit(
            event_type="tool_end",
            run_id=ctx.run_id,
            parent_run_id=ctx.parent_run_id,
            status="success",
            component_kind="tool",
            component_name=ctx.spec.tool_name,
            duration_ms=duration_ms,
            session_id=ctx.session_id,
            user_id_hash=ctx.user_id_hash,
            attributes={
                "result_hash": fingerprint(sanitize(result)),
                "result_summary": self._privacy_safe_value(sanitize(result)),
            },
        )
        self._collect_event_id(ctx, event)
        self._record_action(
            ctx, executed=True, execution_status=ctx.execution_status, duration_ms=duration_ms
        )

    def _finish_error(self, ctx: _ActionContext, exc: BaseException) -> None:
        duration_ms = self.tracker.duration(ctx.run_id)
        event = self.emit(
            event_type="tool_error",
            run_id=ctx.run_id,
            parent_run_id=ctx.parent_run_id,
            status="error",
            component_kind="tool",
            component_name=ctx.spec.tool_name,
            duration_ms=duration_ms,
            session_id=ctx.session_id,
            user_id_hash=ctx.user_id_hash,
            attributes={"error_message": sanitize(str(exc))},
            outcome={"error_type": type(exc).__name__},
        )
        self._collect_event_id(ctx, event)
        self._record_action(
            ctx,
            executed=True,
            execution_status=EXECUTION_ERROR,
            duration_ms=duration_ms,
            error_type=type(exc).__name__,
        )

    def tool(
        self,
        *,
        name: str | None = None,
        action_type: str = "unknown",
        approval_required: bool | None = None,
        data_classes: list[str] | tuple[str, ...] | None = None,
        external_side_effect: bool | None = None,
        reversible: bool | None = None,
        target: str | None = None,
        session_id: str | None = None,
        capability_id: str | None = None,
        capability_status: str | None = None,
        module_path: str | None = None,
        enforcement_mode: str | None = None,
        on_deny: str | None = None,
    ) -> Callable[[F], F]:
        """Decorate a function so Agent7 authorizes it before it executes.

        In ``observe`` mode (the default) the emitted evidence is unchanged from
        earlier releases: ``tool_start`` then ``tool_end``/``tool_error``, with the
        decision carried in-band on ``tool_start``. In ``shadow`` and ``enforce``
        modes a separate ``action_decision`` event is emitted and an ActionRecord
        is written. In ``enforce`` mode a DENY or unapproved REQUIRE_APPROVAL
        prevents the function body from running at all.
        """
        if on_deny is not None and on_deny not in _ON_DENY_CHOICES:
            raise ValueError(f"on_deny must be one of {sorted(_ON_DENY_CHOICES)}, got {on_deny!r}")

        def decorator(func: F) -> F:
            spec = _ToolSpec(
                tool_name=name or getattr(func, "__name__", func.__class__.__name__),
                action_type=action_type,
                approval_required=approval_required,
                data_classes=tuple(data_classes or ()),
                external_side_effect=external_side_effect,
                reversible=reversible,
                target=target,
                session_id=session_id,
                capability_id=capability_id,
                capability_status=capability_status,
                module_path=module_path,
                enforcement_mode=enforcement_mode,
                on_deny=on_deny,
            )

            if inspect.iscoroutinefunction(func):

                @functools.wraps(func)
                async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
                    approval = kwargs.pop(APPROVAL_KWARG, None)
                    token = _ACTIVE_APPROVAL.set(approval) if approval is not None else None
                    try:
                        ctx = self._begin_action(spec, func, args, kwargs)
                        if not ctx.should_execute:
                            return self._blocked(ctx)
                        self._start_execution(ctx)
                        try:
                            result = await func(*args, **kwargs)
                        except Exception as exc:
                            self._finish_error(ctx, exc)
                            raise
                        self._finish_success(ctx, result)
                        return result
                    finally:
                        if token is not None:
                            _ACTIVE_APPROVAL.reset(token)

                return async_wrapper  # type: ignore[return-value]

            @functools.wraps(func)
            def wrapper(*args: Any, **kwargs: Any) -> Any:
                approval = kwargs.pop(APPROVAL_KWARG, None)
                token = _ACTIVE_APPROVAL.set(approval) if approval is not None else None
                try:
                    ctx = self._begin_action(spec, func, args, kwargs)
                    if not ctx.should_execute:
                        return self._blocked(ctx)
                    self._start_execution(ctx)
                    try:
                        result = func(*args, **kwargs)
                    except Exception as exc:
                        self._finish_error(ctx, exc)
                        raise
                    self._finish_success(ctx, result)
                    return result
                finally:
                    if token is not None:
                        _ACTIVE_APPROVAL.reset(token)

            return wrapper  # type: ignore[return-value]

        return decorator

    @staticmethod
    def _raw_call_arguments(
        func: Callable[..., Any], args: tuple[Any, ...], kwargs: dict[str, Any]
    ) -> dict[str, Any]:
        """Bind a call to its signature, returning RAW values.

        The result is used only in-process: to derive the sanitized summary and
        to evaluate deny patterns. It is never persisted or transmitted.
        """
        try:
            signature = inspect.signature(func)
            bound = signature.bind_partial(*args, **kwargs)
            bound.apply_defaults()
            return dict(bound.arguments)
        except Exception:
            return {"args": args, "kwargs": kwargs}

    @staticmethod
    def _safe_call_arguments(func: Callable[..., Any], args: tuple[Any, ...], kwargs: dict[str, Any]) -> Any:
        try:
            signature = inspect.signature(func)
            bound = signature.bind_partial(*args, **kwargs)
            bound.apply_defaults()
            return sanitize(dict(bound.arguments))
        except Exception:
            return sanitize({"args": args, "kwargs": kwargs})

    @staticmethod
    def _privacy_safe_value(value: Any) -> Any:
        return "<redacted-raw-text-probe>" if raw_text_problems(value) else value

    # ------------------------------------------------------------------
    # Manifest-based instrumentation
    # ------------------------------------------------------------------

    @classmethod
    def from_config(
        cls,
        path: str | Path,
        *,
        api_endpoint: str | None = None,
        jsonl_path: str | None = None,
        sink: EventSink | None = None,
        enforcement_mode: str | None = None,
        on_deny: str | None = None,
        actions_jsonl_path: str | None = None,
        record_decisions: bool | None = None,
        remote_decisions: bool | None = None,
        decision_opener: Callable[..., Any] | None = None,
    ) -> "GovernanceClient":
        """Create a :class:`GovernanceClient` from a ``governance.yaml`` manifest.

        ``enforcement_mode`` resolves in this order: the explicit argument, then
        the manifest's ``enforcement_mode`` key, then ``observe``.
        """
        from ai_governance.enforcement import build_policy_from_manifest
        from ai_governance.manifest import load_manifest

        config = load_manifest(path)
        policy = build_policy_from_manifest(config, mode=enforcement_mode)
        client = cls(
            system_id=config["system_id"],
            deployment_id=config.get("deployment_id", "local-test"),
            environment=config.get("environment", "local"),
            agent_id=config.get("agent_id"),
            jsonl_path=jsonl_path or config.get("jsonl_path", "governance-events.jsonl"),
            api_endpoint=api_endpoint or config.get("api_endpoint"),
            sink=sink,
            source={
                "type": "manifest_instrumentation",
                "library": "ai_governance",
                "library_version": "0.1",
            },
            enforcement_mode=policy.mode,
            on_deny=on_deny or config.get("on_deny") or ON_DENY_RETURN,
            policy=policy,
            record_decisions=bool(
                record_decisions
                if record_decisions is not None
                else config.get("record_decisions", False)
            ),
            actions_jsonl_path=actions_jsonl_path or config.get("actions_jsonl_path"),
            remote_decisions=remote_decisions,
            decision_opener=decision_opener,
        )
        client._manifest = config  # type: ignore[attr-defined]
        return client

    def instrument_from_config(self) -> list[dict[str, Any]]:
        """Dynamically wrap functions declared in the stored manifest.

        Returns a list of status dicts, one per capability::

            [{"name": "refund_execute", "module_path": "...", "status": "wrapped"}, ...]

        Only capabilities with status ``approved``, ``approved_for_acap``,
        or ``edited`` are instrumented.  Others are skipped.  Import or
        attribute-resolution failures are reported but never raise.
        """
        from ai_governance.manifest import (
            WRAPPED_MARKER,
            STATUS_ALREADY_WRAPPED,
            STATUS_FAILED_IMPORT,
            STATUS_MISSING_ATTRIBUTE,
            STATUS_SKIPPED_NOT_APPROVED,
            STATUS_UNSUPPORTED_TARGET,
            STATUS_WRAPPED,
            STATUS_WRAPPED_FOR_ENFORCEMENT,
            _APPROVED_STATUSES,
            _DENIED_STATUSES,
            _NEVER_WRAP_STATUSES,
            replace_function,
            resolve_function,
        )

        config: dict[str, Any] | None = getattr(self, "_manifest", None)
        if config is None:
            raise RuntimeError(
                "instrument_from_config() requires a client created via from_config()"
            )

        enforcing = self.enforcement_mode != MODE_OBSERVE

        results: list[dict[str, Any]] = []
        for cap in config.get("capabilities", []):
            cap_name = cap["name"]
            mod_path = cap["module_path"]
            status_val = cap.get("status", "pending")
            entry: dict[str, Any] = {"name": cap_name, "module_path": mod_path}

            # A capability a human refused is wrapped only so Agent7 can block
            # it. In observe mode there is nothing to enforce, so it stays
            # skipped exactly as it always has been.
            wrap_for_enforcement = (
                enforcing
                and status_val in _DENIED_STATUSES
                and status_val not in _NEVER_WRAP_STATUSES
            )

            if status_val not in _APPROVED_STATUSES and not wrap_for_enforcement:
                entry["status"] = STATUS_SKIPPED_NOT_APPROVED
                results.append(entry)
                continue

            resolved = resolve_function(mod_path)
            if resolved is None:
                # Distinguish import failure from missing attribute
                dot = mod_path.rfind(".")
                if dot < 0:
                    entry["status"] = STATUS_FAILED_IMPORT
                else:
                    try:
                        import importlib
                        importlib.import_module(mod_path[:dot])
                        entry["status"] = STATUS_MISSING_ATTRIBUTE
                    except Exception:
                        entry["status"] = STATUS_FAILED_IMPORT
                results.append(entry)
                continue

            module_obj, attr_name, original_func, _ = resolved

            if not callable(original_func):
                entry["status"] = STATUS_UNSUPPORTED_TARGET
                results.append(entry)
                continue

            # Prevent double-wrapping
            if getattr(original_func, WRAPPED_MARKER, False):
                entry["status"] = STATUS_ALREADY_WRAPPED
                results.append(entry)
                continue

            decorator = self.tool(
                name=cap_name,
                action_type=cap.get("action_type", "unknown"),
                approval_required=cap.get("approval_required"),
                data_classes=cap.get("data_classes"),
                external_side_effect=cap.get("external_side_effect"),
                reversible=cap.get("reversible"),
                target=cap.get("target"),
                capability_id=cap.get("capability_id"),
                capability_status=status_val,
                module_path=mod_path,
            )
            wrapped = decorator(original_func)
            setattr(wrapped, WRAPPED_MARKER, True)
            replace_function(module_obj, attr_name, wrapped)
            entry["status"] = (
                STATUS_WRAPPED_FOR_ENFORCEMENT if wrap_for_enforcement else STATUS_WRAPPED
            )
            results.append(entry)

        return results


class ApprovalContext:
    """Attach a trusted approval to every governed call inside a block.

    Only a mapping carrying ``verified`` / ``trusted`` / ``token_verified`` set
    to True is treated as trusted. ``granted`` alone is not enough.
    """

    def __init__(self, approval: Any) -> None:
        self.approval = approval
        self._token: Token[Any] | None = None

    def __enter__(self) -> "ApprovalContext":
        self._token = _ACTIVE_APPROVAL.set(self.approval)
        return self

    def __exit__(self, exc_type: type[BaseException] | None, exc: BaseException | None, traceback: Any) -> bool:
        if self._token is not None:
            _ACTIVE_APPROVAL.reset(self._token)
            self._token = None
        return False


class TraceContext:
    def __init__(self, *, client: GovernanceClient, name: str, session_id: str, user_id_hash: str | None) -> None:
        self.client = client
        self.name = name
        self.session_id = session_id
        self.user_id_hash = user_id_hash
        self.run_id = str(uuid.uuid4())
        self._token: Token[_ActiveTrace | None] | None = None
        self.parent_run_id: str | None = None

    def __enter__(self) -> "TraceContext":
        active = _ACTIVE_TRACE.get()
        self.parent_run_id = active.run_id if active is not None else None
        self.client.tracker.start(self.run_id, self.name)
        self.client.emit(
            event_type="chain_start",
            run_id=self.run_id,
            parent_run_id=self.parent_run_id,
            status="started",
            component_kind="chain",
            component_name=self.name,
            session_id=self.session_id,
            user_id_hash=self.user_id_hash,
            attributes={"trace_name": sanitize(self.name)},
        )
        self._token = _ACTIVE_TRACE.set(
            _ActiveTrace(
                run_id=self.run_id,
                name=self.name,
                session_id=self.session_id,
                user_id_hash=self.user_id_hash,
                tool_parent_run_id=self._tool_parent_run_id(),
                pin_tool_parent=False,
            )
        )
        return self

    def __exit__(self, exc_type: type[BaseException] | None, exc: BaseException | None, traceback: Any) -> bool:
        try:
            duration_ms = self.client.tracker.duration(self.run_id)
            if exc is None:
                self.client.emit(
                    event_type="chain_end",
                    run_id=self.run_id,
                    parent_run_id=self.parent_run_id,
                    status="success",
                    component_kind="chain",
                    component_name=self.name,
                    duration_ms=duration_ms,
                    session_id=self.session_id,
                    user_id_hash=self.user_id_hash,
                    attributes={"trace_name": sanitize(self.name)},
                )
            else:
                self.client.emit(
                    event_type="chain_error",
                    run_id=self.run_id,
                    parent_run_id=self.parent_run_id,
                    status="error",
                    component_kind="chain",
                    component_name=self.name,
                    duration_ms=duration_ms,
                    session_id=self.session_id,
                    user_id_hash=self.user_id_hash,
                    attributes={"trace_name": sanitize(self.name), "error_message": sanitize(str(exc))},
                    outcome={"error_type": exc_type.__name__ if exc_type else type(exc).__name__},
                )
        finally:
            if self._token is not None:
                _ACTIVE_TRACE.reset(self._token)
                self._token = None
        return False

    def _tool_parent_run_id(self) -> str:
        active = _ACTIVE_TRACE.get()
        if active is not None and active.pin_tool_parent:
            return active.tool_parent_run_id
        return self.run_id


class RequestContext:
    def __init__(
        self,
        *,
        client: GovernanceClient,
        name: str,
        session_id: str,
        user_id_hash: str | None,
        attributes: dict[str, Any],
    ) -> None:
        self.client = client
        self.name = name
        self.session_id = session_id
        self.user_id_hash = user_id_hash
        self.attributes = attributes
        self.run_id = str(uuid.uuid4())
        self._token: Token[_ActiveTrace | None] | None = None
        self.status_code: int | None = None

    def __enter__(self) -> "RequestContext":
        self.client.tracker.start(self.run_id, self.name)
        self.client.emit(
            event_type="chain_start",
            run_id=self.run_id,
            parent_run_id=None,
            status="started",
            component_kind="chain",
            component_name=self.name,
            session_id=self.session_id,
            user_id_hash=self.user_id_hash,
            attributes=dict(self.attributes),
        )
        self._token = _ACTIVE_TRACE.set(
            _ActiveTrace(
                run_id=self.run_id,
                name=self.name,
                session_id=self.session_id,
                user_id_hash=self.user_id_hash,
                tool_parent_run_id=self.run_id,
                pin_tool_parent=True,
            )
        )
        return self

    def __exit__(self, exc_type: type[BaseException] | None, exc: BaseException | None, traceback: Any) -> bool:
        try:
            duration_ms = self.client.tracker.duration(self.run_id)
            attrs = dict(self.attributes)
            if self.status_code is not None:
                attrs["status_code"] = self.status_code
            if exc is None:
                self.client.emit(
                    event_type="chain_end",
                    run_id=self.run_id,
                    parent_run_id=None,
                    status="success",
                    component_kind="chain",
                    component_name=self.name,
                    duration_ms=duration_ms,
                    session_id=self.session_id,
                    user_id_hash=self.user_id_hash,
                    attributes=attrs,
                )
            else:
                attrs["error_message"] = self.client._privacy_safe_value(sanitize(str(exc)))
                self.client.emit(
                    event_type="chain_error",
                    run_id=self.run_id,
                    parent_run_id=None,
                    status="error",
                    component_kind="chain",
                    component_name=self.name,
                    duration_ms=duration_ms,
                    session_id=self.session_id,
                    user_id_hash=self.user_id_hash,
                    attributes=attrs,
                    outcome={"error_type": exc_type.__name__ if exc_type else type(exc).__name__},
                )
        finally:
            if self._token is not None:
                _ACTIVE_TRACE.reset(self._token)
                self._token = None
        return False
