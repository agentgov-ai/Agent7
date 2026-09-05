from __future__ import annotations

import threading
import time
from typing import Any
from uuid import UUID

from langchain_core.callbacks import BaseCallbackHandler

from .writer import GovernanceEventWriter, fingerprint, sanitize


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


class GovernanceCallback(BaseCallbackHandler):
    """Reference callback. Adapt signatures and metadata to the installed LangChain version."""

    def __init__(
        self,
        *,
        writer: GovernanceEventWriter,
        system_id: str,
        deployment_id: str,
        environment: str,
        agent_id: str,
        tool_catalog: dict[str, dict[str, Any]] | None = None,
    ) -> None:
        self.writer = writer
        self.system_id = system_id
        self.deployment_id = deployment_id
        self.environment = environment
        self.agent_id = agent_id
        self.tool_catalog = tool_catalog or {}
        self._lock = threading.Lock()
        self._trace_for_run: dict[str, str] = {}
        self._started: dict[str, float] = {}

    def _ids(self, run_id: UUID, parent_run_id: UUID | None) -> tuple[str, str, str | None]:
        run = str(run_id)
        parent = str(parent_run_id) if parent_run_id else None
        with self._lock:
            trace = self._trace_for_run.get(parent) if parent else None
            trace = trace or run
            self._trace_for_run[run] = trace
        return trace, run, parent

    def _start(self, run_id: UUID) -> None:
        with self._lock:
            self._started[str(run_id)] = time.perf_counter()

    def _duration(self, run_id: UUID) -> float | None:
        with self._lock:
            start = self._started.pop(str(run_id), None)
        return None if start is None else round((time.perf_counter() - start) * 1000, 3)

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
        trace_id, span_id, parent_span_id = self._ids(run_id, parent_run_id)
        self.writer.emit(
            {
                "system_id": self.system_id,
                "deployment_id": self.deployment_id,
                "environment": self.environment,
                "event_type": event_type,
                "trace_id": trace_id,
                "span_id": span_id,
                "parent_span_id": parent_span_id,
                "source": {"type": "langchain_callback", "library": "langchain-core", "library_version": None},
                "actor": {"agent_id": self.agent_id, "identity_type": "logical_agent"},
                "component": {"kind": component_kind, "name": component_name, "version": None},
                "outcome": {"status": status, "duration_ms": duration_ms},
                **details,
            }
        )

    def on_chain_start(self, serialized: dict[str, Any], inputs: dict[str, Any], *, run_id: UUID, parent_run_id: UUID | None = None, **kwargs: Any) -> None:
        self._start(run_id)
        self._emit(
            event_type="chain_start", run_id=run_id, parent_run_id=parent_run_id,
            status="started", component_kind="chain", component_name=_serialized_name(serialized, "chain"),
            attributes={"input_shape": sanitize({k: type(v).__name__ for k, v in (inputs or {}).items()})},
        )

    def on_chain_end(self, outputs: dict[str, Any], *, run_id: UUID, parent_run_id: UUID | None = None, **kwargs: Any) -> None:
        self._emit(
            event_type="chain_end", run_id=run_id, parent_run_id=parent_run_id,
            status="success", component_kind="chain", component_name=kwargs.get("name"),
            duration_ms=self._duration(run_id), attributes={"output_hash": fingerprint(sanitize(outputs))},
        )

    def on_chain_error(self, error: BaseException, *, run_id: UUID, parent_run_id: UUID | None = None, **kwargs: Any) -> None:
        duration_ms = self._duration(run_id)
        self._emit(
            event_type="chain_error", run_id=run_id, parent_run_id=parent_run_id,
            status="error", component_kind="chain", component_name=kwargs.get("name"),
            duration_ms=duration_ms, attributes={"error_message": sanitize(str(error))},
            outcome={"status": "error", "duration_ms": duration_ms, "error_type": type(error).__name__},
        )

    def on_llm_start(self, serialized: dict[str, Any], prompts: list[str], *, run_id: UUID, parent_run_id: UUID | None = None, **kwargs: Any) -> None:
        self._start(run_id)
        model_name = kwargs.get("invocation_params", {}).get("model") or kwargs.get("invocation_params", {}).get("model_name")
        self._emit(
            event_type="llm_start", run_id=run_id, parent_run_id=parent_run_id,
            status="started", component_kind="llm", component_name=_serialized_name(serialized, "llm"),
            model={"provider": None, "name": model_name},
            prompt={"template_id": None, "template_hash": fingerprint(prompts), "content_capture": "hash", "message_count": len(prompts), "roles": []},
        )

    def on_chat_model_start(self, serialized: dict[str, Any], messages: list[list[Any]], *, run_id: UUID, parent_run_id: UUID | None = None, **kwargs: Any) -> None:
        self._start(run_id)
        shape = [[getattr(message, "type", message.__class__.__name__) for message in batch] for batch in messages]
        model_name = kwargs.get("invocation_params", {}).get("model") or kwargs.get("invocation_params", {}).get("model_name")
        self._emit(
            event_type="llm_start", run_id=run_id, parent_run_id=parent_run_id,
            status="started", component_kind="chat_model", component_name=_serialized_name(serialized, "chat_model"),
            model={"provider": None, "name": model_name},
            prompt={"template_id": None, "template_hash": fingerprint(shape), "content_capture": "hash", "message_count": sum(len(batch) for batch in messages), "roles": sorted({role for batch in shape for role in batch})},
        )

    def on_llm_end(self, response: Any, *, run_id: UUID, parent_run_id: UUID | None = None, **kwargs: Any) -> None:
        llm_output = getattr(response, "llm_output", None) or {}
        usage = llm_output.get("token_usage") or llm_output.get("usage") or {}
        duration_ms = self._duration(run_id)
        self._emit(
            event_type="llm_end", run_id=run_id, parent_run_id=parent_run_id,
            status="success", component_kind="llm", component_name=kwargs.get("name"),
            duration_ms=duration_ms,
            model={"provider": llm_output.get("model_provider"), "name": llm_output.get("model_name")},
            attributes={"response_hash": fingerprint(str(response))},
            outcome={
                "status": "success", "duration_ms": duration_ms,
                "input_tokens": usage.get("prompt_tokens") or usage.get("input_tokens"),
                "output_tokens": usage.get("completion_tokens") or usage.get("output_tokens"),
                "total_tokens": usage.get("total_tokens"),
            },
        )

    def on_llm_error(self, error: BaseException, *, run_id: UUID, parent_run_id: UUID | None = None, **kwargs: Any) -> None:
        duration_ms = self._duration(run_id)
        self._emit(
            event_type="llm_error", run_id=run_id, parent_run_id=parent_run_id,
            status="error", component_kind="llm", component_name=kwargs.get("name"),
            duration_ms=duration_ms, attributes={"error_message": sanitize(str(error))},
            outcome={"status": "error", "duration_ms": duration_ms, "error_type": type(error).__name__},
        )

    def on_tool_start(self, serialized: dict[str, Any], input_str: str, *, run_id: UUID, parent_run_id: UUID | None = None, inputs: dict[str, Any] | None = None, **kwargs: Any) -> None:
        self._start(run_id)
        name = _serialized_name(serialized, "tool")
        metadata = self.tool_catalog.get(name, {})
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
            approval={"required": metadata.get("approval_required"), "granted": None},
        )

    def on_tool_end(self, output: Any, *, run_id: UUID, parent_run_id: UUID | None = None, **kwargs: Any) -> None:
        self._emit(
            event_type="tool_end", run_id=run_id, parent_run_id=parent_run_id,
            status="success", component_kind="tool", component_name=kwargs.get("name"),
            duration_ms=self._duration(run_id), attributes={"result_hash": fingerprint(sanitize(output)), "result_summary": sanitize(output)},
        )

    def on_tool_error(self, error: BaseException, *, run_id: UUID, parent_run_id: UUID | None = None, **kwargs: Any) -> None:
        duration_ms = self._duration(run_id)
        self._emit(
            event_type="tool_error", run_id=run_id, parent_run_id=parent_run_id,
            status="error", component_kind="tool", component_name=kwargs.get("name"),
            duration_ms=duration_ms, attributes={"error_message": sanitize(str(error))},
            outcome={"status": "error", "duration_ms": duration_ms, "error_type": type(error).__name__},
        )

    def on_retriever_start(self, serialized: dict[str, Any], query: str, *, run_id: UUID, parent_run_id: UUID | None = None, **kwargs: Any) -> None:
        self._start(run_id)
        self._emit(
            event_type="retriever_start", run_id=run_id, parent_run_id=parent_run_id,
            status="started", component_kind="retriever", component_name=_serialized_name(serialized, "retriever"),
            attributes={"query_hash": fingerprint(query)},
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
            status="success", component_kind="retriever", component_name=kwargs.get("name"),
            duration_ms=self._duration(run_id), data={"classifications": [], "sources": sources[:100], "destinations": []},
            attributes={"document_count": len(documents or [])},
        )

    def on_retriever_error(self, error: BaseException, *, run_id: UUID, parent_run_id: UUID | None = None, **kwargs: Any) -> None:
        duration_ms = self._duration(run_id)
        self._emit(
            event_type="retriever_error", run_id=run_id, parent_run_id=parent_run_id,
            status="error", component_kind="retriever", component_name=kwargs.get("name"),
            duration_ms=duration_ms, attributes={"error_message": sanitize(str(error))},
            outcome={"status": "error", "duration_ms": duration_ms, "error_type": type(error).__name__},
        )

    def on_agent_action(self, action: Any, *, run_id: UUID, parent_run_id: UUID | None = None, **kwargs: Any) -> None:
        self._emit(
            event_type="agent_action", run_id=run_id, parent_run_id=parent_run_id,
            status="started", component_kind="agent", component_name=self.agent_id,
            attributes={"tool": getattr(action, "tool", None), "tool_input_hash": fingerprint(sanitize(getattr(action, "tool_input", None)))},
        )

    def on_agent_finish(self, finish: Any, *, run_id: UUID, parent_run_id: UUID | None = None, **kwargs: Any) -> None:
        self._emit(
            event_type="agent_finish", run_id=run_id, parent_run_id=parent_run_id,
            status="success", component_kind="agent", component_name=self.agent_id,
            attributes={"return_values_hash": fingerprint(sanitize(getattr(finish, "return_values", None)))},
        )
