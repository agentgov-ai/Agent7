# Generic Rule Engine Plan

How to replace hardcoded restaurant/refund rules with reusable, ACAP-driven generic rules that work for any AI system.

---

## The Problem

### Current Rules Are Hardcoded

```python
# rules.py (services/evidence_api/)
SYSTEM_RULES = {
    "restaurant-agent": ["R1_confirm_without_proposal"],     # hardcoded
    "customer-refund-agent": ["R_write_no_approval"],         # hardcoded
}

# R1 checks literal tool names:
if tool_name == "place_order":    # ← hardcoded
    prior_place_order = True
if tool_name == "confirm_order":  # ← hardcoded
    if not prior_place_order:
        FLAG VIOLATION

# findings.py (sdk-python/ai_governance/)
# Same R1/R2/R3 rules with hardcoded "confirm_order", "place_order"
```

This only works for the restaurant agent. A new system would need new rules written in Python.

### Target: Rules Driven by ACAP + Action Types

Rules should operate on **action classifications** (read, write, communicate) and **ACAP policies** (authorization, approval requirements, prerequisites), not tool names.

---

## Generic Rule Catalog

### Rules That Already Work Generically

| Rule ID | Current File | What It Checks | Generic? |
|---------|-------------|----------------|----------|
| `R_write_no_approval` | `rules.py:81-140` | Any `write` tool with `approval.required=true` but `approval.granted!=true` | **YES** |

### Rules That Need Generalization

| Current Rule | Hardcoded | Generic Version |
|-------------|-----------|-----------------|
| `R1_confirm_without_proposal` | Checks for `confirm_order` without `place_order` | `R_write_without_prior_communicate`: Any `write` action without prior `communicate` action in session |
| `R2_confirmation_without_customer_turn` | Checks `confirm_order` in same turn as `place_order` | `R_write_same_turn_as_proposal`: Any `write` action in same invoke turn as the `communicate` that proposed it |
| `R3_duplicate_confirmation` | Checks duplicate `confirm_order` | `R_duplicate_write`: Duplicate successful `write` actions with matching arguments in same session |

### New Generic Rules (Not Currently Implemented)

| Rule ID | What It Checks | Severity |
|---------|---------------|----------|
| `R_unregistered_tool` | Tool appears in runtime evidence but not in reviewed ACAP | high |
| `R_exceeds_acap` | Tool authorized as `read` but runtime evidence shows `write` behavior | high |
| `R_missing_agent_identity` | Event lacks `actor.agent_id` | medium |
| `R_missing_session_id` | Event lacks `session_id` | medium |
| `R_unapproved_model` | Model name in evidence doesn't match reviewed ACAP models | high |
| `R_sensitive_data_unapproved` | Tool sends data classified as `financial`/`health` to unapproved destination | high |
| `R_coverage_degraded` | Evidence coverage dropped below threshold since last assessment | medium |
| `R_prohibited_tool` | Tool marked `prohibited` in ACAP was invoked | critical |

---

## Architecture

### Before (Current)

```python
# Hardcoded rule dispatch
def run_rules_for_system(events, system_id, acap_id):
    rule_ids = SYSTEM_RULES.get(system_id, DEFAULT_RULE_IDS)  # hardcoded map
    for rule_id in rule_ids:
        if rule_id == "R1_confirm_without_proposal":
            findings.extend(run_r1_confirm_without_proposal(events))  # hardcoded function
        elif rule_id == "R_write_no_approval":
            findings.extend(run_write_no_approval(events))
```

### After (Generic)

```python
# ai_governance/rules/engine.py

class RuleEngine:
    """Generic rule execution engine. Rules are registered, not hardcoded."""

    def __init__(self):
        self._rules: dict[str, Rule] = {}

    def register(self, rule: "Rule"):
        self._rules[rule.rule_id] = rule

    def run(self, events: list[dict], acap: dict, system_id: str) -> list[dict]:
        """Run all applicable rules against events."""
        findings = []
        for rule in self._rules.values():
            if rule.applies_to(acap, system_id):
                rule_findings = rule.evaluate(events, acap)
                for f in rule_findings:
                    enrich_finding(f)  # add control + framework mappings
                findings.extend(rule_findings)
        return findings

class Rule(Protocol):
    """Interface for deterministic governance rules."""
    rule_id: str
    description: str
    severity: str
    maps_to_control: str | None

    def applies_to(self, acap: dict, system_id: str) -> bool:
        """Whether this rule should run for this system."""
        ...

    def evaluate(self, events: list[dict], acap: dict) -> list[dict]:
        """Evaluate events and return findings. Must be deterministic."""
        ...
```

### Built-in Generic Rules

```python
# ai_governance/rules/builtin.py

class WriteWithoutApproval(Rule):
    """R_write_no_approval: Write action without required approval."""
    rule_id = "R_write_no_approval"
    severity = "high"
    maps_to_control = "AGT-AUTH-001"

    def applies_to(self, acap, system_id):
        # Applies if any tool has action_type=write and approval.required=true
        return any(
            _value(t.get("proposed_action_type")) in ("write", "execute")
            and _value((t.get("approval") or {}).get("required")) is True
            for t in (acap.get("tools") or [])
        )

    def evaluate(self, events, acap):
        # EXISTING LOGIC from rules.py:81-140 -- already generic
        ...


class WriteWithoutPriorCommunicate(Rule):
    """R_write_without_prior_communicate: Write action without preceding communicate action."""
    rule_id = "R_write_without_prior_communicate"
    severity = "high"
    maps_to_control = "AGT-AUTH-001"

    def applies_to(self, acap, system_id):
        # Applies if system has both write and communicate tools
        action_types = {_value(t.get("proposed_action_type")) for t in (acap.get("tools") or [])}
        return "write" in action_types and "communicate" in action_types

    def evaluate(self, events, acap):
        findings = []
        by_session = group_by_session(events)

        for session_ref, session_events in by_session.items():
            ordered = sort_events(session_events)
            prior_communicate = False

            for event in ordered:
                if event.get("event_type") != "tool_start":
                    continue
                tool = event.get("tool") or {}
                action = tool.get("action_type")

                if action == "communicate":
                    prior_communicate = True

                if action == "write" and not prior_communicate:
                    findings.append(self._build_finding(event, session_ref))

        return findings


class ProhibitedToolUsed(Rule):
    """R_prohibited_tool: Tool marked prohibited in ACAP was invoked."""
    rule_id = "R_prohibited_tool"
    severity = "critical"
    maps_to_control = "AGT-AUTH-001"

    def applies_to(self, acap, system_id):
        # Applies if any tool is explicitly prohibited
        return any(
            t.get("authorization") == "prohibited"
            for t in (acap.get("tools") or [])
        )

    def evaluate(self, events, acap):
        prohibited_tools = {
            t["name"] for t in (acap.get("tools") or [])
            if t.get("authorization") == "prohibited"
        }
        findings = []
        for event in events:
            if event.get("event_type") != "tool_start":
                continue
            tool_name = (event.get("tool") or {}).get("name")
            if tool_name in prohibited_tools:
                findings.append(self._build_finding(event, ...))
        return findings


class UnregisteredTool(Rule):
    """R_unregistered_tool: Tool appears in evidence but not in ACAP."""
    rule_id = "R_unregistered_tool"
    severity = "high"
    maps_to_control = None

    def applies_to(self, acap, system_id):
        return True  # always check

    def evaluate(self, events, acap):
        known_tools = {t["name"] for t in (acap.get("tools") or [])}
        findings = []
        seen_unknown = set()

        for event in events:
            if event.get("event_type") != "tool_start":
                continue
            tool_name = (event.get("tool") or {}).get("name")
            if tool_name and tool_name not in known_tools and tool_name not in seen_unknown:
                seen_unknown.add(tool_name)
                findings.append(self._build_finding(event, ...))
        return findings


class UnapprovedModel(Rule):
    """R_unapproved_model: Model used but not listed in ACAP."""
    rule_id = "R_unapproved_model"
    severity = "high"

    def evaluate(self, events, acap):
        approved_models = {
            m.get("name") for m in (acap.get("models") or [])
            if m.get("authorization") == "allowed"
        }
        findings = []
        seen = set()
        for event in events:
            if event.get("event_type") != "llm_start":
                continue
            model_name = (event.get("model") or {}).get("name")
            if model_name and model_name not in approved_models and model_name not in seen:
                seen.add(model_name)
                findings.append(self._build_finding(event, ...))
        return findings


class DuplicateWrite(Rule):
    """R_duplicate_write: Multiple successful write actions with similar args in one session."""
    rule_id = "R_duplicate_write"
    severity = "medium"
    maps_to_control = "AGT-INTEG-001"

    def evaluate(self, events, acap):
        # Group write tool_end events by session
        # Hash their arguments
        # If same tool + same args hash appears twice -> finding
        ...
```

---

## Rule Registration

### Default Rules (shipped with SDK)

```python
# ai_governance/rules/__init__.py

from .engine import RuleEngine
from .builtin import (
    WriteWithoutApproval,
    WriteWithoutPriorCommunicate,
    ProhibitedToolUsed,
    UnregisteredTool,
    UnapprovedModel,
    DuplicateWrite,
    MissingAgentIdentity,
    MissingSessionId,
    CoverageDegraded,
)

def default_engine() -> RuleEngine:
    engine = RuleEngine()
    engine.register(WriteWithoutApproval())
    engine.register(WriteWithoutPriorCommunicate())
    engine.register(ProhibitedToolUsed())
    engine.register(UnregisteredTool())
    engine.register(UnapprovedModel())
    engine.register(DuplicateWrite())
    engine.register(MissingAgentIdentity())
    engine.register(MissingSessionId())
    engine.register(CoverageDegraded())
    return engine
```

### Custom Rules (user-defined)

```python
from ai_governance.rules import RuleEngine, Rule

class MyCustomRule(Rule):
    rule_id = "CUSTOM_001"
    severity = "medium"

    def applies_to(self, acap, system_id):
        return True

    def evaluate(self, events, acap):
        # Custom logic
        ...

engine = default_engine()
engine.register(MyCustomRule())
```

---

## Finding ID Determinism (Preserved)

The current deterministic finding ID scheme is excellent and must be preserved:

```python
def finding_id(rule_id: str, event_ids: list[str]) -> str:
    digest = hashlib.sha256(
        (rule_id + "|" + "|".join(sorted(event_ids))).encode()
    ).hexdigest()[:12]
    return f"F-{digest}"
```

Same rule + same events = same finding ID, always. This is critical for:
- Deduplication across assessment runs
- Tracking finding lifecycle (new, existing, resolved)
- Audit reproducibility

---

## Migration: Current Rules to Generic Rules

### R1 Migration

```
BEFORE:
  R1_confirm_without_proposal
  Checks: confirm_order tool_start without prior place_order tool_start
  Hardcoded: tool names "confirm_order", "place_order"

AFTER:
  R_write_without_prior_communicate
  Checks: any tool_start with action_type=write without prior action_type=communicate
  Driven by: ACAP tool classifications (action_type field)

COMPATIBILITY:
  R1 produces finding F-06236c96da2c for event bef3e128-...
  The new generic rule MUST produce the same finding for the same events
  (if action_type classifications match)
```

### Backward Compatibility

To avoid breaking existing finding IDs:

1. Keep `R1_confirm_without_proposal` as an **alias** that maps to `R_write_without_prior_communicate`
2. Use a legacy finding_id prefix for backward compat
3. New systems get new rule IDs; existing restaurant demo keeps working

```python
RULE_ALIASES = {
    "R1_confirm_without_proposal": "R_write_without_prior_communicate",
    "R2_confirmation_without_customer_turn": "R_write_same_turn_as_proposal",
    "R3_duplicate_confirmation": "R_duplicate_write",
}
```

---

## Evidence API Changes

### Current (`POST /rules/run`)

```python
# Accepts rule_ids list, dispatches to hardcoded functions
class RulesRunRequest(BaseModel):
    rule_ids: list[str]
```

### Target

```python
# Uses RuleEngine with registered rules
@app.post("/rules/run")
def run_rules(body: RulesRunRequest | None = None):
    engine = default_engine()  # or load custom rules from config
    acap = _load_reviewed_acap(system_id)
    events = db.all_events_for_system(conn, system_id)
    findings = engine.run(events, acap, system_id)
    db.insert_findings(conn, findings, system_id)
    return {"findings": findings}
```

### New Endpoint: List Available Rules

```
GET /rules
Response:
{
    "rules": [
        {
            "rule_id": "R_write_no_approval",
            "description": "Write action without required approval",
            "severity": "high",
            "maps_to_control": "AGT-AUTH-001",
            "builtin": true
        },
        {
            "rule_id": "R_prohibited_tool",
            "description": "Tool marked prohibited in ACAP was invoked",
            "severity": "critical",
            "builtin": true
        },
        ...
    ]
}
```

---

## Control Library Updates

### Current (`canonical-controls.yaml`)

```yaml
rule_mappings:
  R1_confirm_without_proposal: AGT-AUTH-001
  R2_confirmation_without_customer_turn: AGT-AUTH-002
  R3_duplicate_confirmation: AGT-INTEG-001
  R_write_no_approval: AGT-AUTH-001
```

### Target

```yaml
rule_mappings:
  # Generic rules
  R_write_no_approval: AGT-AUTH-001
  R_write_without_prior_communicate: AGT-AUTH-001
  R_write_same_turn_as_proposal: AGT-AUTH-002
  R_duplicate_write: AGT-INTEG-001
  R_prohibited_tool: AGT-AUTH-001
  R_unregistered_tool: AGT-AUTH-001
  R_unapproved_model: AGT-AUTH-001

  # Legacy aliases (backward compat)
  R1_confirm_without_proposal: AGT-AUTH-001
  R2_confirmation_without_customer_turn: AGT-AUTH-002
  R3_duplicate_confirmation: AGT-INTEG-001
```

---

## What Stays Deterministic (No LLM)

| Aspect | Deterministic? | Why |
|--------|---------------|-----|
| Rule evaluation | Yes | Pure code over sorted event lists |
| Finding ID | Yes | SHA256(rule_id + sorted event_ids) |
| Control mapping | Yes | YAML lookup |
| Framework mapping | Yes | YAML lookup |
| Overall status | Yes | If high-severity -> requires_remediation |
| Risk profile | Yes | If/else on ACAP fields |

**LLM is never involved in rule evaluation, finding generation, or assessment scoring.** The only place LLM touches is the optional enrichment stage during ACAP draft generation, and even those suggestions require human confirmation.
