# ADR 0001: Instrument the existing restaurant agent before building the platform

## Status

Accepted for the first prototype objective.

## Decision

Use the existing LangChain restaurant agent as the first governed deployment. Prove local evidence extraction, privacy controls, tool discovery, draft ACAP generation and deterministic findings before building the Command Center backend or dashboard.

## Reasons

- Tests the hardest technical assumption against real agent code.
- Reveals what LangChain exposes automatically versus what needs annotations.
- Prevents building a platform around an unvalidated telemetry model.
- Produces a credible demonstration using an already functioning application.
- Keeps the first change small and reversible.

## Initial sink

Use privacy-safe local JSONL. Add OpenTelemetry/OTLP only after the event schema and coverage are validated.

## Consequences

- The first deliverable is a measurement report and evidence artifacts, not a polished product UI.
- Framework mapping remains illustrative until evidence extraction is proven.
- Any missing approval, identity or data-classification fields become explicit follow-up requirements.
