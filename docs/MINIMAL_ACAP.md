# Minimal auto-generated ACAP

ACAP is not a long developer questionnaire. It is a reviewed authorization profile generated from discovered capabilities.

## Automatic draft inputs

- discovered agents and tools;
- tool argument schemas;
- model and prompt fingerprints;
- observed read/write/external behavior;
- technical annotations from a small tool override file;
- available approval and identity evidence.

## Human confirmations

Ask only the policy questions that code cannot answer:

1. What is this restaurant agent intended to do?
2. Who is accountable for it?
3. Which discovered actions should be allowed?
4. Which actions should be prohibited?
5. Which actions require user confirmation or staff approval?
6. Which customer data may be processed?
7. What changes require reassessment?

## Important separation

```text
Discovered: the tool exists.
Observed: the tool was called.
Authorized: a responsible person approved its use under defined conditions.
```

Do not collapse these into one field.

## Example

A discovered `cancel_reservation` tool may lead to this draft:

```yaml
cancel_reservation:
  discovered: true
  observed: false
  proposed_action_type: write
  proposed_external_side_effect: true
  authorization: unresolved
  proposed_approval: customer_confirmation
  provenance:
    - source: code_discovery
    - source: tool_override
```

The reviewer chooses whether it is allowed and under what conditions.
