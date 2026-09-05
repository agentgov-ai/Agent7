# Evidence requirements and likely sources

## What LangChain can often expose automatically

| Field | Likely source | Notes |
|---|---|---|
| Run/span IDs and parent relationships | Callback arguments or OTel spans | Essential for reconstructing the path |
| Chain/agent/component name | Serialized runnable, run name or span name | Exact availability varies by version |
| Model invocation | LLM/chat-model callbacks | Provider/model may require metadata or response details |
| Prompt/message structure | LLM/chat-model start callbacks | Store hashes and counts by default, not raw text |
| Model outcome | LLM end/error callbacks | Token usage depends on provider integration |
| Tool name | Tool start callback | Usually reliable |
| Tool arguments | Tool start callback | Must be sanitized; schema is safer than raw values |
| Tool result/error | Tool end/error callback | Store status and summary/hash by default |
| Retrieval activity | Retriever callbacks | Source-document content should not be stored by default |
| Timing | Start/end timestamps | Compute duration locally |
| Agent action/finish | Agent callbacks or graph events | Useful for intermediate decisions |

## What normally needs lightweight annotation

| Field | Why it is not reliably inferable |
|---|---|
| System and deployment ID | Business deployment boundary is outside LangChain |
| Logical agent identity | A class name is not necessarily an accountable agent identity |
| Tool action type | Function name alone may not prove read/write/execute semantics |
| External side effect | Some tools only draft; others actually send or mutate |
| Reversibility | Requires domain knowledge |
| Data classification | Tool arguments may contain PII without explicit labels |
| Approval required | A policy decision, not a runtime fact |
| Approval granted | Requires an explicit application/workflow event |
| On-behalf-of user | Must be passed securely and pseudonymized |

## What requires human confirmation

- Intended purpose
- Accountable owner
- Allowed and prohibited actions
- Approval thresholds
- Sensitive data allowed/prohibited
- Acceptable autonomy
- Reassessment triggers

## Content capture modes

1. **Metadata only:** default for this experiment.
2. **Hash/fingerprint:** prompts, outputs and large tool values.
3. **Sanitized summary:** selected tool arguments/results after redaction.
4. **Full content:** not enabled in this starter; would require explicit design and consent.

## Evidence coverage calculation

For each required field report:

```text
captured | partially captured | annotation required | unavailable | intentionally disabled
```

Do not reduce `intentionally disabled` privacy fields into a generic failure. The report should distinguish a privacy choice from an instrumentation gap.
