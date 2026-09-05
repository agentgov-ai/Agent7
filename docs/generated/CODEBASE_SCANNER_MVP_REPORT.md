# Codebase Scanner MVP Report

**Date:** 2026-08-29
**Scanner version:** 0.1.0
**Schema version:** 0.1

## Purpose

The codebase scanner is a deterministic, local-only static analysis tool that inspects Python source files using the `ast` module and produces a `governance-discovery.json` containing **candidate capabilities** with evidence, confidence scores, and `review_status: pending`.

**Product principle:** Scanner suggests. Human approves. Runtime proves.

The scanner does NOT:
- Call AI/LLM
- Upload source code
- Generate approved ACAP
- Replace human review

## Architecture

```
CLI (cli.py)
  -> walk .py files (exclude .git, .venv, node_modules, etc.)
  -> ast.parse each file
  -> build import alias map + local variable bindings
  -> visit each function/method:
      -> check decorators (@gov.tool, @app.post, etc.)
      -> walk body for Call nodes -> resolve via alias map -> match against sink catalog
      -> apply name heuristics
  -> classify each candidate (action_type, risk, data_classes, approval)
  -> output governance-discovery.json
```

### Key modules

| Module | Purpose |
|--------|---------|
| `scanner/sinks.py` | Sink catalog (~60 entries) across 7 categories + model-usage patterns |
| `scanner/ast_scanner.py` | Core AST walker with import alias and local binding resolution |
| `scanner/rules.py` | Classification engine (action_type, risk, confidence scoring) |
| `scanner/models.py` | Plain-dict builders for candidates, evidence, summaries |
| `scanner/output.py` | JSON/YAML output generation |
| `cli.py` | `agent-governance scan <path>` CLI entry point |

## Sink categories

| Category | Risk | Action type | Examples |
|----------|------|-------------|----------|
| Payment/refund | high | write | `stripe.refunds.create`, `paypal.*` |
| Email/communication | high | communicate | `smtplib.SMTP.send_message`, `sendgrid.*` |
| Database write/delete | medium | write/delete | `session.delete`, `collection.insert_one` |
| HTTP outbound | medium | write/delete | `requests.post`, `httpx.delete` |
| Filesystem | medium | write/delete | `os.remove`, `shutil.rmtree`, `Path.write_text` |
| Subprocess | high | execute | `subprocess.run`, `os.system` |
| Cloud SDK | high | write/delete/execute | `s3.put_object`, `sns.publish` |

## Confidence scoring

| Source | Score | Description |
|--------|-------|-------------|
| `sink_reachability` | 0.90 | Known consequential sink call found in function body |
| `existing_decorator` | 0.85 | `@gov.tool(...)` decorator with governance metadata |
| `route_and_name` | 0.70 | FastAPI write/delete route handler |
| `name_heuristic` | 0.50 | Function/parameter name matches risky patterns |
| `model_usage` | — | Recorded separately as model surface, not a capability |

Multiple signals: highest source wins, +0.05 per additional signal (cap 0.95).

## Model usage separation

OpenAI/Anthropic/LLM SDK calls are recorded as `model_surface` entries, NOT as governed business capabilities. A bare `openai.chat.completions.create()` is model infrastructure. It only becomes a capability when wrapped in a business-meaningful tool or action.

## Output format

```json
{
  "schema_version": "0.1",
  "scanner_version": "0.1.0",
  "generated_at": "...",
  "source": "deterministic_scanner",
  "project_hash": "sha256:...",
  "scan_summary": { ... },
  "candidates": [ { "review_status": "pending", ... } ],
  "model_surface": [ ... ]
}
```

Every candidate has `review_status: "pending"`. No approved ACAP is generated.

## Known limitations

1. **Single-function scope.** The scanner only analyzes the immediate function body. Transitive call chains (`foo() -> bar() -> stripe.refunds.create()`) will flag `bar` but not `foo`. Cross-function dataflow analysis is planned for a future milestone.

2. **Dynamic dispatch.** Calls like `getattr(client, method_name)(...)` cannot be resolved statically and are not detected.

3. **Non-literal SQL.** `cursor.execute(query_variable)` is flagged as medium-risk but the SQL content cannot be inspected. Only string-literal SQL arguments are analyzed for write keywords.

4. **Complex re-exports.** Import chains across multiple modules (re-exports) may not fully resolve.

5. **Local variable tracking.** The scanner tracks `with X() as name` and `name = X()` bindings within a function, but does not follow complex assignment chains or conditional bindings.

## Test coverage

51 tests across 5 test classes:
- `TestSinkCatalog` — catalog matching, SQL detection, model usage patterns
- `TestClassificationRules` — action_type, risk, confidence scoring
- `TestASTScanner` — sink detection, decorators, routes, aliases, local bindings, exclusions
- `TestOutputFormat` — schema, fields, deterministic IDs, no ACAP
- `TestEndToEndDemoApp` — full scan of `examples/scanner-demo-app/`

## Usage

```bash
# Install
pip install -e sdk-python/

# Scan
agent-governance scan /path/to/project

# Or without install
cd sdk-python && python -m ai_governance scan /path/to/project

# Options
agent-governance scan . --output discovery.json --format json --verbose
```

## Next steps

- Dashboard review UI for human approval of pending candidates
- Transitive call-chain analysis
- Manifest instrumentation from approved candidates
- `governance.yaml.candidate` output for review workflow
