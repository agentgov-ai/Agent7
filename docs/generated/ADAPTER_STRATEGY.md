# Adapter Strategy

How to support LangChain, OpenAI, Anthropic, LiteLLM, LlamaIndex, FastAPI, raw logs, and generic Python instrumentation through a unified adapter architecture.

---

## Adapter Protocol

Every adapter implements this interface:

```python
from typing import Protocol, Any
from ai_governance import GovernanceClient

class FrameworkAdapter(Protocol):
    """Translates framework lifecycle events into governance events."""

    def install(self, target: Any = None) -> Any:
        """
        Attach to the target framework object.
        Returns a framework-specific handler/wrapper/middleware.
        """
        ...
```

The adapter's job is simple: **listen for framework events, call `GovernanceClient` methods to emit governance events.** All sanitization, validation, and sink routing happens inside the client.

---

## Adapter 1: LangChain (Priority 1 -- exists today)

### Current State

`sdk-python/ai_governance/callback.py` inherits `BaseCallbackHandler` and implements 14 callback methods. All the LangChain-specific translation logic lives here.

### Target Design

```python
# ai_governance/adapters/langchain.py

from langchain_core.callbacks import BaseCallbackHandler
from ai_governance import GovernanceClient
from ai_governance.core import SessionTracker

class LangChainAdapter(BaseCallbackHandler):
    """LangChain callback handler that emits governance events."""

    raise_error = False  # fail-open

    def __init__(self, client: GovernanceClient):
        self.client = client
        self._tracker = SessionTracker()

    def on_tool_start(self, serialized, input_str, *, run_id, parent_run_id=None, **kwargs):
        trace_id, span_id = self._tracker.start_span(run_id, parent_run_id)
        self.client.emit_tool_start(
            tool_name=serialized.get("name", "unknown"),
            arguments=input_str,
            trace_id=trace_id,
            span_id=span_id,
            parent_span_id=self._tracker.span_for(parent_run_id),
        )

    def on_tool_end(self, output, *, run_id, **kwargs):
        trace_id, span_id = self._tracker.resolve(run_id)
        duration = self._tracker.end_span(span_id)
        self.client.emit_tool_end(
            tool_name=...,
            result=output,
            trace_id=trace_id,
            span_id=span_id,
            duration_ms=duration,
        )

    # Similarly: on_llm_start/end, on_chain_start/end, on_retriever_start/end
```

### Migration from Current Code

| Current (callback.py) | Target (adapters/langchain.py) |
|----------------------|-------------------------------|
| `GovernanceCallback.__init__` (writer, metadata) | `LangChainAdapter.__init__` (client) |
| `_emit()` (event construction + writing) | Split: event construction -> `EventBuilder`, writing -> `GovernanceClient` |
| `_ids()` (run_id -> trace/span mapping) | Moved to `SessionTracker` |
| `_session_id()` (metadata extraction) | Moved to `SessionTracker` |
| `_duration()` (timing) | Moved to `SessionTracker` |
| All `on_*` methods | Same methods, but delegate to `client.emit_*` |

### What the Developer Writes

```python
from ai_governance import GovernanceClient

gov = GovernanceClient(system_id="my-agent")

agent.invoke(
    {"input": user_input},
    config={"callbacks": [gov.langchain_callback()]}
)
```

---

## Adapter 2: OpenAI Direct Client (Priority 2 -- new)

### Design

Wrap the `openai.OpenAI` client so that every `chat.completions.create()` call emits governance events.

```python
# ai_governance/adapters/openai.py

import openai
from ai_governance import GovernanceClient

class OpenAIAdapter:
    def __init__(self, client: GovernanceClient):
        self.client = client

    def install(self, openai_client: openai.OpenAI) -> openai.OpenAI:
        original_create = openai_client.chat.completions.create

        def wrapped_create(*args, **kwargs):
            trace_id = self.client.start_trace()
            span_id = self.client.start_span(trace_id)

            # Emit llm_start
            self.client.emit_llm_start(
                model_name=kwargs.get("model", "unknown"),
                model_provider="openai",
                message_count=len(kwargs.get("messages", [])),
                trace_id=trace_id,
                span_id=span_id,
            )

            try:
                response = original_create(*args, **kwargs)

                # Emit llm_end
                usage = getattr(response, "usage", None)
                self.client.emit_llm_end(
                    trace_id=trace_id,
                    span_id=span_id,
                    token_usage={
                        "prompt_tokens": usage.prompt_tokens if usage else None,
                        "completion_tokens": usage.completion_tokens if usage else None,
                    },
                )
                return response

            except Exception as e:
                self.client.emit_llm_error(
                    trace_id=trace_id,
                    span_id=span_id,
                    error_type=type(e).__name__,
                )
                raise

        openai_client.chat.completions.create = wrapped_create
        return openai_client
```

### What the Developer Writes

```python
from ai_governance import GovernanceClient
import openai

gov = GovernanceClient(system_id="my-chatbot")
client = gov.wrap_openai(openai.OpenAI())

response = client.chat.completions.create(
    model="gpt-4",
    messages=[{"role": "user", "content": "Hello"}]
)
# Governance events emitted automatically
```

### Tool Call Handling

When the OpenAI response includes `tool_calls`, the adapter emits `tool_start` events. The developer must emit `tool_end` manually (since the SDK doesn't control tool execution):

```python
for tool_call in response.choices[0].message.tool_calls:
    # Adapter auto-emits tool_start from the response
    result = execute_tool(tool_call.function.name, tool_call.function.arguments)
    gov.emit_tool_end(tool_name=tool_call.function.name, result=result)
```

Or use the `@gov.tool()` decorator for automatic capture.

---

## Adapter 3: Anthropic Client (Priority 2 -- new)

### Design

Same pattern as OpenAI. Wrap `anthropic.Anthropic` client.

```python
# ai_governance/adapters/anthropic.py

class AnthropicAdapter:
    def install(self, client: anthropic.Anthropic) -> anthropic.Anthropic:
        original_create = client.messages.create

        def wrapped_create(*args, **kwargs):
            # Emit llm_start with model=kwargs["model"], provider="anthropic"
            response = original_create(*args, **kwargs)
            # Emit llm_end with usage from response.usage
            # If tool_use blocks in response, emit tool_start events
            return response

        client.messages.create = wrapped_create
        return client
```

### What the Developer Writes

```python
gov = GovernanceClient(system_id="my-agent")
client = gov.wrap_anthropic(anthropic.Anthropic())

response = client.messages.create(
    model="claude-sonnet-4-20250514",
    messages=[...],
    tools=[...]
)
```

---

## Adapter 4: LiteLLM (Priority 3 -- new)

### Design

LiteLLM has a `success_callback` / `failure_callback` system.

```python
# ai_governance/adapters/litellm.py

import litellm

class LiteLLMAdapter:
    def install(self, client: GovernanceClient):
        def on_success(kwargs, response, start_time, end_time):
            client.emit_llm_start(...)
            client.emit_llm_end(...)

        def on_failure(kwargs, exception, start_time, end_time):
            client.emit_llm_start(...)
            client.emit_llm_error(...)

        litellm.success_callback.append(on_success)
        litellm.failure_callback.append(on_failure)
```

### What the Developer Writes

```python
gov = GovernanceClient(system_id="my-multi-model-app")
gov.litellm_adapter()  # registers callbacks globally

response = litellm.completion(model="gpt-4", messages=[...])
# Governance events emitted via LiteLLM callbacks
```

---

## Adapter 5: LlamaIndex (Priority 3 -- new)

### Design

LlamaIndex uses a `CallbackManager` with event handlers.

```python
# ai_governance/adapters/llamaindex.py

from llama_index.core.callbacks import CallbackManager, CBEventType, EventPayload

class LlamaIndexAdapter:
    def install(self, client: GovernanceClient) -> CallbackManager:
        handler = GovernanceLlamaHandler(client)
        return CallbackManager([handler])

class GovernanceLlamaHandler:
    def on_event_start(self, event_type: CBEventType, payload: EventPayload, **kwargs):
        if event_type == CBEventType.LLM:
            client.emit_llm_start(...)
        elif event_type == CBEventType.FUNCTION_CALL:
            client.emit_tool_start(...)

    def on_event_end(self, event_type: CBEventType, payload: EventPayload, **kwargs):
        ...
```

---

## Adapter 6: Generic Python Decorator (Priority 1 -- new)

### Design

For any framework or custom code. Manual but explicit.

```python
# ai_governance/adapters/generic.py

class GenericAdapter:
    """Provides @gov.tool() decorator and gov.trace() context manager."""

    def tool(self, name: str, action_type: str = "unknown", **annotations):
        """Decorator that wraps a function with governance event emission."""
        def decorator(func):
            def wrapper(*args, **kwargs):
                span_id = self.client.start_span(...)
                self.client.emit_tool_start(
                    tool_name=name,
                    action_type=action_type,
                    arguments=kwargs,
                    **annotations,
                )
                try:
                    result = func(*args, **kwargs)
                    self.client.emit_tool_end(tool_name=name, result=result)
                    return result
                except Exception as e:
                    self.client.emit_tool_error(tool_name=name, error=e)
                    raise
            return wrapper
        return decorator

    def trace(self, name: str):
        """Context manager for manual trace boundaries."""
        return TraceContext(self.client, name)
```

### What the Developer Writes

```python
gov = GovernanceClient(system_id="my-pipeline")

@gov.tool(name="send_email", action_type="communicate", approval_required=True)
def send_email(to: str, subject: str, body: str):
    smtp.send(to, subject, body)

# Or manual tracing:
with gov.trace("process_request") as trace:
    data = fetch_data(request_id)
    trace.log_tool_call("fetch_data", action_type="read")
    result = process(data)
    trace.log_tool_call("process", action_type="execute")
```

---

## Adapter 7: FastAPI Middleware (Priority 3 -- new)

### Design

For AI systems that expose tools as HTTP endpoints (MCP servers, tool-serving APIs).

```python
# ai_governance/adapters/fastapi.py

from starlette.middleware.base import BaseHTTPMiddleware

class GovernanceMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, client: GovernanceClient, tool_routes: dict[str, dict] = None):
        super().__init__(app)
        self.client = client
        self.tool_routes = tool_routes or {}

    async def dispatch(self, request, call_next):
        route = request.url.path
        tool_config = self.tool_routes.get(route)
        if tool_config:
            self.client.emit_tool_start(
                tool_name=tool_config["name"],
                action_type=tool_config.get("action_type", "execute"),
            )
        response = await call_next(request)
        if tool_config:
            self.client.emit_tool_end(
                tool_name=tool_config["name"],
                status="success" if response.status_code < 400 else "error",
            )
        return response
```

### What the Developer Writes

```python
from fastapi import FastAPI
from ai_governance import GovernanceClient
from ai_governance.adapters.fastapi import GovernanceMiddleware

app = FastAPI()
gov = GovernanceClient(system_id="tool-server")

app.add_middleware(
    GovernanceMiddleware,
    client=gov,
    tool_routes={
        "/api/search": {"name": "search", "action_type": "read"},
        "/api/execute": {"name": "execute", "action_type": "write"},
    }
)
```

---

## Adapter 8: Raw JSON Log Adapter (Priority 4 -- new)

### Design

For systems that already produce structured logs. Parse existing logs into governance events.

```python
# ai_governance/adapters/raw_log.py

class RawLogAdapter:
    def __init__(self, client: GovernanceClient, mapping: dict):
        self.client = client
        self.mapping = mapping  # maps log fields to governance event fields

    def ingest_log_line(self, log: dict):
        event = self._map(log)
        self.client.emit_raw(event)

    def ingest_file(self, path: str):
        with open(path) as f:
            for line in f:
                self.ingest_log_line(json.loads(line))
```

---

## Adapter Priority and Effort

| Priority | Adapter | Effort | Value | Dependency |
|----------|---------|--------|-------|------------|
| **1** | LangChain | Low (refactor existing) | High (current users) | `langchain-core` |
| **1** | Generic Decorator | Medium (new) | High (any framework) | None |
| **2** | OpenAI Wrapper | Medium (new) | High (most common) | `openai` |
| **2** | Anthropic Wrapper | Medium (new) | High (growing fast) | `anthropic` |
| **3** | LiteLLM | Low (callback hooks) | Medium (multi-model) | `litellm` |
| **3** | LlamaIndex | Medium (new) | Medium (RAG focused) | `llama-index-core` |
| **3** | FastAPI Middleware | Medium (new) | Medium (tool servers) | `starlette` |
| **4** | Raw Log Adapter | Low (simple mapping) | Low (niche) | None |
| **Future** | Semantic Kernel | Medium | Low (early adopters) | TBD |
| **Future** | CrewAI/AutoGen | Medium | Low (wait for demand) | TBD |

---

## Event Mapping: What Each Adapter Captures

| Event Type | LangChain | OpenAI | Anthropic | Generic | FastAPI |
|-----------|-----------|--------|-----------|---------|---------|
| `llm_start` | on_llm_start | completions.create (pre) | messages.create (pre) | manual | N/A |
| `llm_end` | on_llm_end | completions.create (post) | messages.create (post) | manual | N/A |
| `llm_error` | on_llm_error | exception handler | exception handler | manual | N/A |
| `tool_start` | on_tool_start | tool_calls in response | tool_use blocks | @gov.tool() | middleware pre |
| `tool_end` | on_tool_end | manual or @gov.tool() | manual or @gov.tool() | @gov.tool() | middleware post |
| `tool_error` | on_tool_error | @gov.tool() exception | @gov.tool() exception | @gov.tool() | middleware error |
| `chain_start` | on_chain_start | N/A | N/A | gov.trace() | N/A |
| `chain_end` | on_chain_end | N/A | N/A | gov.trace() | N/A |
| `retriever_*` | on_retriever_* | N/A | N/A | manual | N/A |

### Coverage Gap: Tool Execution

LangChain is unique in that it controls tool execution (the framework calls the tool). OpenAI and Anthropic only *request* tool calls; the developer's code executes them. This means:

- **LangChain adapter:** Full automatic tool start/end capture
- **OpenAI/Anthropic adapter:** Automatic `tool_start` from response, but `tool_end` requires either `@gov.tool()` decorator or manual `gov.emit_tool_end()`

The `@gov.tool()` generic decorator bridges this gap for all non-LangChain frameworks.

---

## Testing Strategy for Adapters

Each adapter needs:

1. **Unit test:** Mock the framework client, verify events emitted correctly
2. **Integration test:** Real framework call (mocked LLM endpoint), verify end-to-end JSONL output
3. **Privacy test:** Verify no raw prompts/responses leak through the adapter
4. **Fail-open test:** Verify framework still works when sink is broken
5. **Determinism test:** Same input produces same event structure (excluding timestamps/UUIDs)
