# Custom Python Tool Example

This example shows non-LangChain instrumentation with `GovernanceClient.tool`.

```powershell
conda run python examples\custom-python-tool\run_example.py
```

The script writes `examples/custom-python-tool/events.jsonl`. If
`GOVERNANCE_API_ENDPOINT` is set, the same events are also sent to the Evidence
API on a best-effort fail-open path.
