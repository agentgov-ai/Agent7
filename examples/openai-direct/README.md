# OpenAI Direct Example

This example shows direct OpenAI SDK-style instrumentation without LangChain.

By default it uses a local fake OpenAI-compatible client so the example can run
without credentials:

```powershell
conda run python examples\openai-direct\run_example.py
```

For a real OpenAI call, install the optional `openai` package, configure
credentials, and construct the client with `gov.openai_client()`.
