# Anthropic Direct Example

This example shows direct Anthropic SDK-style instrumentation without LangChain.

By default it uses a local fake Anthropic-compatible client so the example can
run without credentials:

```powershell
conda run python examples\anthropic-direct\run_example.py
```

For a real Anthropic call, install the optional `anthropic` package, configure
credentials, and construct the client with `gov.anthropic_client()`.
