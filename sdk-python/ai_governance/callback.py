from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from langchain_core import __version__ as _LANGCHAIN_CORE_VERSION
from langchain_core.callbacks import BaseCallbackHandler

from .core import EventBuilder, SessionTracker
from .writer import GovernanceEventWriter, fingerprint, sanitize

logger = logging.getLogger(__name__)


def _serialized_name(serialized: dict[str, Any] | None, fallback: str) -> str:
    if not serialized:
        return fallback
    name = serialized.get("name")
    if name:
        return str(name)
    identifier = serialized.get("id")
    if isinstance(identifier, list) and identifier:
        return str(identifier[-1])
    return fallback


def _usage_from_response(response: Any) -> dict[str, Any]:
    llm_output = getattr(response, "llm_output", None) or {}
    usage = llm_output.get("token_usage") or llm_output.get("usage") or {}
    if usage:
        return usage
    try:
        for batch in getattr(response, "generations", None) or []:
            for generation in batch:
                message = getattr(generation, "message", None)
                usage_metadata = getattr(message, "usage_metadata", None)
                if usage_metadata:
                    return {
                        "prompt_tokens": usage_metadata.get("input_tokens"),
                        "completion_tokens": usage_metadata.get("output_tokens"),
                        "total_tokens": usage_metadata.get("total_tokens"),
                    }
    except Exception:
        pass
    return {}


class GovernanceCallback(BaseCallbackHandler):
    """Passive evidence callback for langchain-core 1.x.

    Fail-open by design: any failure while writing evidence is swallowed
    (logged and counted in ``dropped_events``) so the agent request is never
    affected. Raw prompt/response content is never persisted — only hashes,
    message-shape metadata and sanitized tool arguments/results.
    """

    raise_error = False  # langchain-core also suppresses handler exceptions

    def __init__(
        self,
        *,
        writer: GovernanceEventWriter,
        system_id: str,
        deployment_id: str,
        environment: str,
        agent_id: str,
        tool_catalog: dict[str, dict[str, Any]] | None = None,
        model_provider: str | None = None,
    ) -> None:
        self.writer = writer
        self.system_id = system_id
        self.deployment_id = deployment_id
        self.environment = environment
        self.agent_id = agent_id
        self.tool_catalog = tool_catalog or {}
        self.model_provider = model_provider
        self.default_session_id = f"{deployment_id}:default"
        self.dropped_events = 0
        self._tracker = SessionTracker(default_session_id=self.default_session_id)
        self._builder = EventBuilder(
            system_id=system_id,
            deployment_id=deployment_id,
            environment=environment,
            agent_id=agent_id,
            source={
                "type": "langchain_callback",
                "library": "langchain-core",
                "library_version": _LANGCHAIN_CORE_VERSION,
            },
            tracker=self._tracker,
        )
        self._trace_for_run = self._tracker.trace_for_run
        self._session_for_run = self._tracker.session_for_run

    # -- bookkeeping ---------------------------------------------------------

    def _ids(self, run_id: UUID, parent_run_id: UUID | None, *, final: bool = False) -> tuple[str, str, str | None]:
        return self._tracker.ids(run_id, parent_run_id, final=final)

    @staticmethod
    def _session_candidate(kwargs: dict[str, Any]) -> str | None:
        return SessionTracker.session_candidate(kwargs)

    def _session_id(self, run_id: UUID, parent_run_id: UUID | None, kwargs: dict[str, Any], *, final: bool) -> str:
        return self._tracker.session_id(run_id, parent_run_id, kwargs, final=final)

    def _start(self, run_id: UUID, component_name: str | None = None) -> None:
        self._tracker.start(run_id, component_name)

    def _duration(self, run_id: UUID) -> float | None:
        return self._tracker.duration(run_id)

    def _name_for(self, run_id: UUID, fallback: str | None) -> str | None:
        return self._tracker.name_for(run_id, fallback)

    def _emit(
        self,
        *,
        event_type: str,
        run_id: UUID,
        parent_run_id: UUID | None,
        status: str,
        component_kind: str,
        component_name: str | None,
        duration_ms: float | None = None,
        **details: Any,
    ) -> None:
        try:
            event = self._builder.build(
                event_type=event_type,
                run_id=run_id,
                parent_run_id=parent_run_id,
                status=status,
                component_kind=component_kind,
                component_name=component_name,
                duration_ms=duration_ms,
                **details,
            )
            self.writer.emit(event)
        except Exception:  # evidence failure must never break the request
            self.dropped_events += 1
            logger.warning("governance evidence emit failed", exc_info=True)

    # -- chain / agent -------------------------------------------------------

    def on_chain_start(self, serialized: dict[str, Any], inputs: dict[str, Any], *, run_id: UUID, parent_run_id: UUID | None = None, **kwargs: Any) -> None:
        name = _serialized_name(serialized, kwargs.get("name") or "chain")
        self._start(run_id, name)
        input_shape: Any
        if isinstance(inputs, dict):
            input_shape = {k: type(v).__name__ for k, v in inputs.items()}
        else:
            input_shape = type(inputs).__name__
        self._emit(
            event_type="chain_start", run_id=run_id, parent_run_id=parent_run_id,
            status="started", component_kind="chain", component_name=name,
            attributes={"input_shape": sanitize(input_shape)},
            _callback_context=kwargs,
        )

    def on_chain_end(self, outputs: dict[str, Any], *, run_id: UUID, parent_run_id: UUID | None = None, **kwargs: Any) -> None:
        self._emit(
            event_type="chain_end", run_id=run_id, parent_run_id=parent_run_id,
            status="success", component_kind="chain",
            component_name=self._name_for(run_id, kwargs.get("name")),
            duration_ms=self._duration(run_id),
            attributes={"output_hash": fingerprint(sanitize(outputs))},
            _callback_context=kwargs,
        )

    def on_chain_error(self, error: BaseException, *, run_id: UUID, parent_run_id: UUID | None = None, **kwargs: Any) -> None:
        duration_ms = self._duration(run_id)
        self._emit(
            event_type="chain_error", run_id=run_id, parent_run_id=parent_run_id,
            status="error", component_kind="chain",
            component_name=self._name_for(run_id, kwargs.get("name")),
            duration_ms=duration_ms, attributes={"error_message": sanitize(str(error))},
            outcome={"error_type": type(error).__name__},
            _callback_context=kwargs,
        )

    # -- model ---------------------------------------------------------------

    def on_llm_start(self, serialized: dict[str, Any], prompts: list[str], *, run_id: UUID, parent_run_id: UUID | None = None, **kwargs: Any) -> None:
        name = _serialized_name(serialized, "llm")
        self._start(run_id, name)
        params = kwargs.get("invocation_params") or {}
        model_name = params.get("model") or params.get("model_name")
        self._emit(
            event_type="llm_start", run_id=run_id, parent_run_id=parent_run_id,
            status="started", component_kind="llm", component_name=name,
            model={"provider": self.model_provider, "name": model_name},
            prompt={
                "template_id": None, "template_hash": fingerprint(prompts),
                "content_capture": "hash", "message_count": len(prompts), "roles": [],
            },
            _callback_context=kwargs,
        )

    def on_chat_model_start(self, serialized: dict[str, Any], messages: list[list[Any]], *, run_id: UUID, parent_run_id: UUID | None = None, **kwargs: Any) -> None:
        name = _serialized_name(serialized, "chat_model")
        self._start(run_id, name)
        shape = [
            [getattr(message, "type", message.__class__.__name__) for message in batch]
            for batch in messages
        ]
        params = kwargs.get("invocation_params") or {}
        model_name = params.get("model") or params.get("model_name")
        self._emit(
            event_type="llm_start", run_id=run_id, parent_run_id=parent_run_id,
            status="started", component_kind="chat_model", component_name=name,
            model={"provider": self.model_provider, "name": model_name},
            prompt={
                "template_id": None, "template_hash": fingerprint(shape),
                "content_capture": "hash",
                "message_count": sum(len(batch) for batch in messages),
                "roles": sorted({role for batch in shape for role in batch}),
            },
            _callback_context=kwargs,
        )

    def on_llm_end(self, response: Any, *, run_id: UUID, parent_run_id: UUID | None = None, **kwargs: Any) -> None:
        llm_output = getattr(response, "llm_output", None) or {}
        usage = _usage_from_response(response)
        duration_ms = self._duration(run_id)
        self._emit(
            event_type="llm_end", run_id=run_id, parent_run_id=parent_run_id,
            status="success", component_kind="chat_model",
            component_name=self._name_for(run_id, kwargs.get("name")),
            duration_ms=duration_ms,
            model={"provider": self.model_provider, "name": llm_output.get("model_name")},
            attributes={"response_hash": fingerprint(str(response))},
            outcome={
                "status": "success", "duration_ms": duration_ms,
                "input_tokens": usage.get("prompt_tokens") or usage.get("input_tokens"),
                "output_tokens": usage.get("completion_tokens") or usage.get("output_tokens"),
                "total_tokens": usage.get("total_tokens"),
            },
            _callback_context=kwargs,
        )

    def on_llm_error(self, error: BaseException, *, run_id: UUID, parent_run_id: UUID | None = None, **kwargs: Any) -> None:
        duration_ms = self._duration(run_id)
        self._emit(
            event_type="llm_error", run_id=run_id, parent_run_id=parent_run_id,
            status="error", component_kind="chat_model",
            component_name=self._name_for(run_id, kwargs.get("name")),
            duration_ms=duration_ms, attributes={"error_message": sanitize(str(error))},
            outcome={"error_type": type(error).__name__},
            _callback_context=kwargs,
        )

    # -- tools ---------------------------------------------------------------

    def on_tool_start(self, serialized: dict[str, Any], input_str: str, *, run_id: UUID, parent_run_id: UUID | None = None, inputs: dict[str, Any] | None = None, **kwargs: Any) -> None:
        name = _serialized_name(serialized, "tool")
        self._start(run_id, name)
        metadata = self.tool_catalog.get(name, {})
        approval_meta = metadata.get("approval") or {}
        safe_args = sanitize(inputs if inputs is not None else input_str)
        self._emit(
            event_type="tool_start", run_id=run_id, parent_run_id=parent_run_id,
            status="started", component_kind="tool", component_name=name,
            tool={
                "name": name,
                "action_type": metadata.get("action_type", "unknown"),
                "arguments_hash": fingerprint(safe_args),
                "sanitized_arguments": safe_args,
                "target": metadata.get("target"),
                "external_side_effect": metadata.get("external_side_effect"),
                "reversible": metadata.get("reversible"),
            },
            data={"classifications": metadata.get("data_classes", []), "sources": [], "destinations": []},
            approval={
                "required": approval_meta.get("required", metadata.get("approval_required")),
                "granted": None,
                "policy_id": approval_meta.get("condition"),
                "trust_basis": "session_structure" if approval_meta.get("required") else None,
                "note": (
                    "model-supplied tool arguments are not trusted approval evidence"
                    if approval_meta.get("required") else None
                ),
            },
            _callback_context=kwargs,
        )

    # Tool results whose catalog entry declares one of these data classes are
    # persisted as hash-only: sanitize() has no reliable pattern for free-text
    # personal data such as customer names (e.g. get_user_name greetings).
    SENSITIVE_DATA_CLASSES = frozenset({"contact"})

    def on_tool_end(self, output: Any, *, run_id: UUID, parent_run_id: UUID | None = None, **kwargs: Any) -> None:
        name = self._name_for(run_id, kwargs.get("name"))
        data_classes = set(self.tool_catalog.get(name, {}).get("data_classes") or [])
        if data_classes & self.SENSITIVE_DATA_CLASSES:
            summary = "<redacted-data-class:" + ",".join(sorted(data_classes & self.SENSITIVE_DATA_CLASSES)) + ">"
        else:
            summary = sanitize(output)
        self._emit(
            event_type="tool_end", run_id=run_id, parent_run_id=parent_run_id,
            status="success", component_kind="tool",
            component_name=name,
            duration_ms=self._duration(run_id),
            attributes={"result_hash": fingerprint(sanitize(output)), "result_summary": summary},
            _callback_context=kwargs,
        )

    def on_tool_error(self, error: BaseException, *, run_id: UUID, parent_run_id: UUID | None = None, **kwargs: Any) -> None:
        duration_ms = self._duration(run_id)
        self._emit(
            event_type="tool_error", run_id=run_id, parent_run_id=parent_run_id,
            status="error", component_kind="tool",
            component_name=self._name_for(run_id, kwargs.get("name")),
            duration_ms=duration_ms, attributes={"error_message": sanitize(str(error))},
            outcome={"error_type": type(error).__name__},
            _callback_context=kwargs,
        )

    # -- retriever (no retriever runs exist in this app today; kept for coverage) --

    def on_retriever_start(self, serialized: dict[str, Any], query: str, *, run_id: UUID, parent_run_id: UUID | None = None, **kwargs: Any) -> None:
        name = _serialized_name(serialized, "retriever")
        self._start(run_id, name)
        self._emit(
            event_type="retriever_start", run_id=run_id, parent_run_id=parent_run_id,
            status="started", component_kind="retriever", component_name=name,
            attributes={"query_hash": fingerprint(query)},
            _callback_context=kwargs,
        )

    def on_retriever_end(self, documents: list[Any], *, run_id: UUID, parent_run_id: UUID | None = None, **kwargs: Any) -> None:
        sources = []
        for document in documents or []:
            metadata = getattr(document, "metadata", {}) or {}
            source = metadata.get("source") or metadata.get("id")
            if source is not None:
                sources.append(str(source))
        self._emit(
            event_type="retriever_end", run_id=run_id, parent_run_id=parent_run_id,
            status="success", component_kind="retriever",
            component_name=self._name_for(run_id, kwargs.get("name")),
            duration_ms=self._duration(run_id),
            data={"classifications": [], "sources": sources[:100], "destinations": []},
            attributes={"document_count": len(documents or [])},
            _callback_context=kwargs,
        )

    def on_retriever_error(self, error: BaseException, *, run_id: UUID, parent_run_id: UUID | None = None, **kwargs: Any) -> None:
        duration_ms = self._duration(run_id)
        self._emit(
            event_type="retriever_error", run_id=run_id, parent_run_id=parent_run_id,
            status="error", component_kind="retriever",
            component_name=self._name_for(run_id, kwargs.get("name")),
            duration_ms=duration_ms, attributes={"error_message": sanitize(str(error))},
            outcome={"error_type": type(error).__name__},
            _callback_context=kwargs,
        )

    # -- agent action / finish ----------------------------------------------

    def on_agent_action(self, action: Any, *, run_id: UUID, parent_run_id: UUID | None = None, **kwargs: Any) -> None:
        self._emit(
            event_type="agent_action", run_id=run_id, parent_run_id=parent_run_id,
            status="started", component_kind="agent", component_name=self.agent_id,
            attributes={
                "tool": getattr(action, "tool", None),
                "tool_input_hash": fingerprint(sanitize(getattr(action, "tool_input", None))),
            },
            _callback_context=kwargs,
        )

    def on_agent_finish(self, finish: Any, *, run_id: UUID, parent_run_id: UUID | None = None, **kwargs: Any) -> None:
        self._emit(
            event_type="agent_finish", run_id=run_id, parent_run_id=parent_run_id,
            status="success", component_kind="agent", component_name=self.agent_id,
            attributes={"return_values_hash": fingerprint(sanitize(getattr(finish, "return_values", None)))},
            _callback_context=kwargs,
        )
