from __future__ import annotations

import uuid
from typing import Any

from ai_governance.core import fingerprint
from ai_governance.adapters.llm_common import finish_reasons, get_value, message_count, message_roles, token_usage


class OpenAIAdapter:
    """Adapter for a direct OpenAI SDK client instance."""

    def __init__(self, client: Any) -> None:
        self.governance_client = client

    def install(self, target: Any = None) -> Any:
        if target is None:
            raise ValueError("OpenAIAdapter.install requires an OpenAI client instance")
        return _GovernedOpenAIClient(target, self.governance_client)


class _GovernedOpenAIClient:
    def __init__(self, wrapped: Any, governance_client: Any) -> None:
        self._wrapped = wrapped
        self._governance_client = governance_client

    @property
    def chat(self) -> "_GovernedChat":
        return _GovernedChat(self._wrapped.chat, self._governance_client)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._wrapped, name)


class _GovernedChat:
    def __init__(self, wrapped: Any, governance_client: Any) -> None:
        self._wrapped = wrapped
        self._governance_client = governance_client

    @property
    def completions(self) -> "_GovernedChatCompletions":
        return _GovernedChatCompletions(self._wrapped.completions, self._governance_client)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._wrapped, name)


class _GovernedChatCompletions:
    def __init__(self, wrapped: Any, governance_client: Any) -> None:
        self._wrapped = wrapped
        self._governance_client = governance_client

    def create(self, *args: Any, **kwargs: Any) -> Any:
        gov = self._governance_client
        run_id = str(uuid.uuid4())
        operation = "chat.completions.create"
        context = gov.active_context()
        parent_run_id = context["parent_run_id"]
        session_id = context["session_id"]
        user_id_hash = context["user_id_hash"]
        model_name = kwargs.get("model")
        messages = kwargs.get("messages")
        prompt_hash = fingerprint({"messages": messages}) if messages is not None else fingerprint({"args_count": len(args)})
        roles = message_roles(messages)
        gov.tracker.start(run_id, operation)
        gov.emit(
            event_type="llm_start",
            run_id=run_id,
            parent_run_id=parent_run_id,
            status="started",
            component_kind="chat_model",
            component_name=operation,
            session_id=session_id,
            user_id_hash=user_id_hash,
            model={"provider": "openai", "name": model_name},
            prompt={
                "template_id": None,
                "template_hash": prompt_hash,
                "content_capture": "hash",
                "message_count": message_count(messages),
                "roles": roles,
            },
            attributes={"operation": operation},
        )
        try:
            response = self._wrapped.create(*args, **kwargs)
        except Exception as exc:
            duration_ms = gov.tracker.duration(run_id)
            gov.emit(
                event_type="llm_error",
                run_id=run_id,
                parent_run_id=parent_run_id,
                status="error",
                component_kind="chat_model",
                component_name=operation,
                duration_ms=duration_ms,
                session_id=session_id,
                user_id_hash=user_id_hash,
                model={"provider": "openai", "name": model_name},
                attributes={"operation": operation, "error_hash": fingerprint(str(exc))},
                outcome={"error_type": type(exc).__name__},
            )
            raise
        duration_ms = gov.tracker.duration(run_id)
        usage = token_usage(response)
        reasons = finish_reasons(response)
        response_shape = {
            "model": get_value(response, "model", model_name),
            "usage": usage,
            "finish_reasons": reasons,
            "choice_count": len(get_value(response, "choices", []) or []),
            "type": response.__class__.__name__,
        }
        gov.emit(
            event_type="llm_end",
            run_id=run_id,
            parent_run_id=parent_run_id,
            status="success",
            component_kind="chat_model",
            component_name=operation,
            duration_ms=duration_ms,
            session_id=session_id,
            user_id_hash=user_id_hash,
            model={"provider": "openai", "name": get_value(response, "model", model_name)},
            attributes={
                "operation": operation,
                "response_hash": fingerprint(response_shape),
                "finish_reasons": reasons,
            },
            outcome={
                "input_tokens": usage.get("prompt_tokens"),
                "output_tokens": usage.get("completion_tokens"),
                "total_tokens": usage.get("total_tokens"),
            },
        )
        return response

    def __getattr__(self, name: str) -> Any:
        return getattr(self._wrapped, name)
