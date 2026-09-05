# Python reference adapter

This directory is a **reference**, not a drop-in dependency. Claude should adapt it to the installed LangChain version and repository structure.

It demonstrates:

- a local thread-safe JSONL writer;
- recursive sanitization and hashing;
- a `BaseCallbackHandler` implementation for common LangChain events;
- tool discovery from LangChain tool objects;
- root invocation metadata.

The reference stores no raw prompt or model-output content. It is intentionally small so the first experiment can run without infrastructure.

Possible integration shape:

```python
writer = GovernanceEventWriter("artifacts/governance/events.jsonl")
callback = GovernanceCallback(
    writer=writer,
    system_id="restaurant-agent",
    deployment_id="local-test",
    environment="local",
    agent_id="restaurant-agent-main",
)

result = agent.invoke(
    user_input,
    config={
        "callbacks": [callback],
        "tags": ["governance-poc"],
        "metadata": {"deployment_id": "local-test"},
    },
)
```

Use the actual invocation signature in the repository. If callbacks are already configured, append/merge rather than replacing them.
