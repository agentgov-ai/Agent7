from __future__ import annotations

import functools
import inspect
import logging
import os
import uuid
from contextvars import ContextVar, Token
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, TypeVar

from ai_governance.core import EventBuilder, SessionTracker, fingerprint, raw_text_problems, sanitize
from ai_governance.sinks import JsonlSink
from ai_governance.sinks.base import EventSink

logger = logging.getLogger(__name__)

F = TypeVar("F", bound=Callable[..., Any])


@dataclass(frozen=True)
class _ActiveTrace:
    run_id: str
    name: str
    session_id: str
    user_id_hash: str | None
    tool_parent_run_id: str
    pin_tool_parent: bool = False


_ACTIVE_TRACE: ContextVar[_ActiveTrace | None] = ContextVar("ai_governance_active_trace", default=None)


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
    ) -> None:
        if not system_id:
            raise ValueError("system_id must not be empty")
        self.system_id = system_id
        self.deployment_id = deployment_id
        self.environment = environment
        self.agent_id = agent_id or system_id
        self.session_id = session_id or f"{deployment_id}:default"
        self.dropped_events = 0
        endpoint = api_endpoint if api_endpoint is not None else os.environ.get("GOVERNANCE_API_ENDPOINT")
        self.sink = sink or JsonlSink(jsonl_path, api_endpoint=endpoint, api_timeout_seconds=api_timeout_seconds)
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
    ) -> Callable[[F], F]:
        """Decorate a plain Python function to emit governance tool events."""

        def decorator(func: F) -> F:
            tool_name = name or getattr(func, "__name__", func.__class__.__name__)

            @functools.wraps(func)
            def wrapper(*args: Any, **kwargs: Any) -> Any:
                run_id = str(uuid.uuid4())
                context = self.active_context()
                parent_run_id = context["parent_run_id"]
                event_session_id = session_id or context["session_id"]
                user_id_hash = context["user_id_hash"]
                self.tracker.start(run_id, tool_name)
                safe_args = self._privacy_safe_value(self._safe_call_arguments(func, args, kwargs))
                classes = list(data_classes or [])
                self.emit(
                    event_type="tool_start",
                    run_id=run_id,
                    parent_run_id=parent_run_id,
                    status="started",
                    component_kind="tool",
                    component_name=tool_name,
                    session_id=event_session_id,
                    user_id_hash=user_id_hash,
                    tool={
                        "name": tool_name,
                        "action_type": action_type,
                        "arguments_hash": fingerprint(safe_args),
                        "sanitized_arguments": safe_args,
                        "target": target,
                        "external_side_effect": external_side_effect,
                        "reversible": reversible,
                    },
                    data={"classifications": classes, "sources": [], "destinations": []},
                    approval={"required": approval_required, "granted": None, "policy_id": None},
                )
                try:
                    result = func(*args, **kwargs)
                except Exception as exc:
                    duration_ms = self.tracker.duration(run_id)
                    self.emit(
                        event_type="tool_error",
                        run_id=run_id,
                        parent_run_id=parent_run_id,
                        status="error",
                        component_kind="tool",
                        component_name=tool_name,
                        duration_ms=duration_ms,
                        session_id=event_session_id,
                        user_id_hash=user_id_hash,
                        attributes={"error_message": sanitize(str(exc))},
                        outcome={"error_type": type(exc).__name__},
                    )
                    raise
                duration_ms = self.tracker.duration(run_id)
                self.emit(
                    event_type="tool_end",
                    run_id=run_id,
                    parent_run_id=parent_run_id,
                    status="success",
                    component_kind="tool",
                    component_name=tool_name,
                    duration_ms=duration_ms,
                    session_id=event_session_id,
                    user_id_hash=user_id_hash,
                    attributes={
                        "result_hash": fingerprint(sanitize(result)),
                        "result_summary": self._privacy_safe_value(sanitize(result)),
                    },
                )
                return result

            return wrapper  # type: ignore[return-value]

        return decorator

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
    ) -> "GovernanceClient":
        """Create a :class:`GovernanceClient` from a ``governance.yaml`` manifest."""
        from ai_governance.manifest import load_manifest

        config = load_manifest(path)
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
            _APPROVED_STATUSES,
            replace_function,
            resolve_function,
        )

        config: dict[str, Any] | None = getattr(self, "_manifest", None)
        if config is None:
            raise RuntimeError(
                "instrument_from_config() requires a client created via from_config()"
            )

        results: list[dict[str, Any]] = []
        for cap in config.get("capabilities", []):
            cap_name = cap["name"]
            mod_path = cap["module_path"]
            status_val = cap.get("status", "pending")
            entry: dict[str, Any] = {"name": cap_name, "module_path": mod_path}

            if status_val not in _APPROVED_STATUSES:
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
            )
            wrapped = decorator(original_func)
            setattr(wrapped, WRAPPED_MARKER, True)
            replace_function(module_obj, attr_name, wrapped)
            entry["status"] = STATUS_WRAPPED
            results.append(entry)

        return results


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
