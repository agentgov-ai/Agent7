# Migration Plan: PoC to Library

Exactly which current files are generic, demo-specific, should move, should be renamed, or should be deprecated.

---

## File-by-File Migration Table

### SDK Python (`sdk-python/ai_governance/`)

| Current File | Status | Action | Target Location | Notes |
|-------------|--------|--------|-----------------|-------|
| `__init__.py` | GENERIC | **Update** | `ai_governance/__init__.py` | Add `GovernanceClient` as primary export |
| `callback.py` | LANGCHAIN-COUPLED | **Split** | `ai_governance/adapters/langchain.py` + `ai_governance/core/session_tracker.py` | Extract `SessionTracker` and event building to core; keep LangChain adapter separate |
| `writer.py` | GENERIC | **Split** | `ai_governance/core/sanitizer.py` + `ai_governance/sinks/jsonl.py` + `ai_governance/sinks/http.py` | `sanitize()`/`fingerprint()` -> core; `GovernanceEventWriter` -> jsonl sink; `EvidenceApiSink` -> http sink |
| `discovery.py` | GENERIC | **Move** | `ai_governance/discovery/tools.py` | Already handles both BaseTool and plain functions |
| `bootstrap.py` | MOSTLY GENERIC | **Refactor** | `ai_governance/__init__.py` (GovernanceClient) | Remove hardcoded defaults (`restaurant-agent`, `local-test`). `Governance` class becomes `GovernanceClient` |
| `findings.py` | DEMO-SPECIFIC | **Split** | Generic engine: `ai_governance/rules/engine.py` + `ai_governance/rules/builtin.py`; Demo rules: `examples/restaurant-agent/rules.py` | R1/R2/R3 become examples of `WriteWithoutPriorCommunicate` etc. |
| `acap_draft.py` | DEMO-SPECIFIC | **Split** | Generic draft: `ai_governance/acap/draft.py`; Demo questions: `examples/restaurant-agent/acap_config.yaml` | Remove `TOOL_FIELD_NOTES` for confirm_order; genericize review questions |
| `acap_review.py` | GENERIC | **Move** | `ai_governance/acap/review.py` | Already framework-agnostic |
| `coverage_report.py` | MOSTLY GENERIC | **Refactor** | `ai_governance/core/coverage.py` | Extract text probes to configurable list |
| `scenario_runner.py` | DEMO-SPECIFIC | **Move** | `examples/restaurant-agent/scenario_runner.py` | Hardcoded scenarios, test users, restaurant paths |
| `otel_export.py` | MOSTLY GENERIC | **Refactor** | `ai_governance/sinks/otel.py` | Extract text probes; keep OTLP conversion logic |
| `control_library.py` | GENERIC | **Move** | `ai_governance/rules/control_library.py` | Already framework-agnostic |
| `verify_objective.py` | DEMO-SPECIFIC | **Move** | `examples/restaurant-agent/verify_objective.py` | Checks PoC-specific success criteria |
| `pyproject.toml` | N/A | **Update** | `sdk-python/pyproject.toml` | Make `langchain-core` optional dependency |

### Governance Probe (compatibility shim)

| Current File | Action | Notes |
|-------------|--------|-------|
| `governance_probe/` (entire directory) | **Deprecate** | Keep for backward compat in v1.0; add deprecation warning. Remove in v2.0. All imports should move to `ai_governance` |
| `governance_probe/_compat.py` | **Deprecate** | sys.path hack; unnecessary with proper package install |

### Services (`services/evidence_api/`)

| Current File | Status | Action | Notes |
|-------------|--------|--------|-------|
| `app.py` | MOSTLY GENERIC | **Refactor** | Extract `SYSTEM_REGISTRY` to config file or env var; make `DEFAULT_RULE_IDS` configurable; use `RuleEngine` instead of hardcoded dispatch |
| `db.py` | GENERIC | **Keep** | Already framework-agnostic |
| `validation.py` | MOSTLY GENERIC | **Refactor** | Extract text probes to configurable list loaded from YAML |
| `rules.py` | DEMO-SPECIFIC | **Replace** | Replace with `RuleEngine` + built-in generic rules; keep R1 as legacy alias |
| `coverage.py` | GENERIC | **Keep** | Already framework-agnostic |
| `draft.py` | MOSTLY GENERIC | **Refactor** | Remove `TOOL_FIELD_NOTES` for restaurant tools; genericize review questions |
| `risk.py` | GENERIC | **Keep** | Already framework-agnostic |
| `report.py` | GENERIC | **Keep** | Already framework-agnostic |
| `control_library.py` | GENERIC | **Keep** | Delegates to canonical-controls.yaml |
| `evidence.db` | N/A | **Gitignore** | Should not be tracked in git |

### Frontend (`services/evidence_api/static/`)

| Current File | Status | Action | Notes |
|-------------|--------|--------|-------|
| `app.js` | MOSTLY GENERIC | **Refactor** | Extract text probes; move `RULE_RECOMMENDATIONS` to server-side API response; replace hardcoded rule descriptions with data from `GET /rules` |
| `index.html` | GENERIC | **Keep** | No domain-specific content |
| `styles.css` | GENERIC | **Keep** | No domain-specific content |

### Control Library

| Current File | Action | Notes |
|-------------|--------|-------|
| `canonical-controls.yaml` | **Update** | Add rule_mappings for new generic rules; keep legacy aliases |

### Schemas

| Current File | Action | Notes |
|-------------|--------|-------|
| `governance-event.schema.json` | **Keep** | Already vendor-neutral. May version to 0.2 if new required fields added |

### Examples

| Current File | Action | Notes |
|-------------|--------|-------|
| `examples/restaurant-agent/Restaurant_agent1.py` | **Keep** | Demo agent stays as example |
| `examples/restaurant-agent/governance-tool-overrides.yaml` | **Keep** | Demo config |
| `examples/refund-agent/generate_evidence.py` | **Keep** | Synthetic event generator for multi-system demo |
| `examples/refund-agent/acap-reviewed.yaml` | **Keep** | Demo ACAP |

### Root Level

| Current File | Action | Notes |
|-------------|--------|-------|
| `Restaurant_agent1.py` | **Keep** | Compatibility wrapper for demo |
| `governance-tool-overrides.yaml` | **Move** | Move to `examples/restaurant-agent/` (it's demo-specific) |
| `CLAUDE.md` | **Update** | Add library architecture notes |
| `README.md` | **Rewrite** | Focus on library install + quickstart, not demo |

### Tests

| Current File | Status | Action | Notes |
|-------------|--------|--------|-------|
| `test_evidence_api.py` | DEMO-SPECIFIC | **Split** | Generic API tests + restaurant-specific fixture tests |
| `test_evidence_ui.py` | MOSTLY GENERIC | **Keep** | Minor text probe update |
| `test_findings.py` | DEMO-SPECIFIC | **Split** | Generic rule engine tests + restaurant rule examples |
| `test_governance_probe.py` | MOSTLY GENERIC | **Refactor** | Update imports from `governance_probe` to `ai_governance` |
| `test_otel_export.py` | MOSTLY GENERIC | **Keep** | Extract text probes |
| `test_sdk_layout.py` | GENERIC | **Update** | Add new package structure assertions |

### New Files to Create

| File | Purpose |
|------|---------|
| `ai_governance/core/__init__.py` | Core exports |
| `ai_governance/core/event_builder.py` | EventBuilder class (extracted from callback.py) |
| `ai_governance/core/session_tracker.py` | SessionTracker class (extracted from callback.py) |
| `ai_governance/core/sanitizer.py` | sanitize(), fingerprint(), SanitizerConfig |
| `ai_governance/core/validator.py` | validate_event() (extracted from evidence_api/validation.py) |
| `ai_governance/core/schema.py` | Event type enums, field constants |
| `ai_governance/adapters/__init__.py` | Adapter exports |
| `ai_governance/adapters/base.py` | FrameworkAdapter protocol |
| `ai_governance/adapters/langchain.py` | LangChain adapter (refactored from callback.py) |
| `ai_governance/adapters/openai.py` | OpenAI client wrapper |
| `ai_governance/adapters/anthropic.py` | Anthropic client wrapper |
| `ai_governance/adapters/generic.py` | @gov.tool() decorator, trace context manager |
| `ai_governance/sinks/__init__.py` | Sink exports |
| `ai_governance/sinks/base.py` | EventSink protocol |
| `ai_governance/sinks/jsonl.py` | JsonlSink (from GovernanceEventWriter) |
| `ai_governance/sinks/http.py` | HttpSink (from EvidenceApiSink) |
| `ai_governance/sinks/otel.py` | OtlpSink (live streaming version) |
| `ai_governance/sinks/multi.py` | MultiSink (fan-out) |
| `ai_governance/discovery/__init__.py` | Discovery exports |
| `ai_governance/discovery/tools.py` | discover_tools() (moved) |
| `ai_governance/enrichment/__init__.py` | Enrichment exports |
| `ai_governance/enrichment/heuristic.py` | Deterministic inference |
| `ai_governance/enrichment/llm.py` | Optional LLM enrichment |
| `ai_governance/enrichment/provenance.py` | Provenance tracking |
| `ai_governance/acap/__init__.py` | ACAP exports |
| `ai_governance/acap/draft.py` | Generic draft generation |
| `ai_governance/acap/review.py` | Review workflow (moved) |
| `ai_governance/acap/versioning.py` | ACAP versioning |
| `ai_governance/rules/__init__.py` | Rule exports + default_engine() |
| `ai_governance/rules/engine.py` | RuleEngine class |
| `ai_governance/rules/builtin.py` | Built-in generic rules |
| `ai_governance/rules/registry.py` | Rule registration |
| `ai_governance/rules/control_library.py` | Control loading (moved) |
| `ai_governance/privacy/__init__.py` | Privacy exports |
| `ai_governance/privacy/modes.py` | PrivacyMode configs |
| `ai_governance/privacy/probes.py` | Configurable text probes |
| `services/evidence_api/system_config.yaml` | Replaces SYSTEM_REGISTRY dict |
| `services/evidence_api/text_probes.yaml` | Configurable text probes |

---

## Hardcoded Values to Extract

### Text Probes (duplicated in 3 places)

**Currently hardcoded in:**
1. `services/evidence_api/validation.py:50-54`
2. `sdk-python/ai_governance/otel_export.py:36-40`
3. `services/evidence_api/static/app.js:35-40`

**Target:** Single config file `services/evidence_api/text_probes.yaml`:

```yaml
# Text patterns that indicate raw content leakage
probes:
  system_prompt_text:
    pattern: "restaurant waiter bot"
    category: system_prompt
  stdin_order_text:
    pattern: "I want to order"
    category: user_input
  adversarial_input_text:
    pattern: "ignore (all|previous) instructions"
    category: adversarial
  known_fake_prompt:
    pattern: "SECRET-PROMPT-TEXT"
    category: test_marker
  known_fake_response:
    pattern: "SECRET-RESPONSE-TEXT"
    category: test_marker
```

JavaScript loads from API: `GET /config/text-probes`. Python loads from YAML.

### System Registry

**Currently:** `app.py:28-37` hardcoded dict

**Target:** `services/evidence_api/system_config.yaml`:

```yaml
systems:
  restaurant-agent:
    acap: artifacts/governance/acap-reviewed.yaml
    events: artifacts/governance/events.jsonl
  customer-refund-agent:
    acap: examples/refund-agent/acap-reviewed.yaml
    events: examples/refund-agent/events.jsonl
```

Or dynamically from DB: any system that has events ingested with a `system_id` auto-registers.

### Rule-System Mapping

**Currently:** `rules.py:9-12` hardcoded dict

**Target:** Rules auto-apply based on ACAP content via `rule.applies_to(acap)`. No mapping needed.

### Bootstrap Defaults

**Currently:** `bootstrap.py` defaults to `system_id="restaurant-agent"`, `agent_id="restaurant-agent-main"`, etc.

**Target:** No defaults. Require `system_id` as mandatory parameter.

### Review Questions

**Currently:** `acap_draft.py` and `draft.py` have restaurant-specific questions (Q5 mentions "confirm_order").

**Target:** Generic questions defined in `ai_governance/acap/draft.py`. Demo-specific questions in `examples/restaurant-agent/acap_config.yaml`.

---

## Dependency Changes

### Before

```toml
# sdk-python/pyproject.toml
dependencies = [
    "langchain-core",
    "PyYAML",
]
```

### After

```toml
[project]
dependencies = ["PyYAML"]

[project.optional-dependencies]
langchain = ["langchain-core>=0.2"]
openai = ["openai>=1.0"]
anthropic = ["anthropic>=0.30"]
litellm = ["litellm"]
llamaindex = ["llama-index-core"]
otel = ["opentelemetry-api", "opentelemetry-sdk"]
all = ["ai-governance[langchain,openai,anthropic,otel]"]
dev = ["pytest", "httpx", "jsonschema"]
```

### Breaking Change

`langchain-core` moves from required to optional. Any code that does `from ai_governance import GovernanceCallback` and relies on `BaseCallbackHandler` will need:

```bash
pip install ai-governance[langchain]
```

Or switch to:

```python
from ai_governance import GovernanceClient
callback = gov.langchain_callback()  # auto-imports adapter
```

---

## What Must NOT Break

1. **Restaurant demo still works** with `GOVERNANCE_EVIDENCE=1 python Restaurant_agent1.py`
2. **Refund demo still works** with `python examples/refund-agent/generate_evidence.py`
3. **All existing tests pass** (may need import path updates)
4. **Finding F-06236c96da2c** is still produced for the same events (deterministic IDs preserved)
5. **Evidence API endpoints** maintain same request/response contract
6. **Dashboard** looks and functions the same
7. **JSONL format** is unchanged (schema v0.1 preserved)
8. **acap-reviewed.yaml** files are still valid
