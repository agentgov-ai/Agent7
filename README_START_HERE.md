# Restaurant Agent Governance Extraction — Claude Code Starter

This pack is designed for an **existing LangChain restaurant agent**. Its first objective is not to build the full AI Governance Command Center. It is to prove, with the current codebase, that we can extract enough trustworthy runtime evidence to support governance.

## What changes from the earlier starter pack

- Use the restaurant agent as the golden-path application.
- Do not scaffold Next.js, FastAPI, PostgreSQL, Redis, LangGraph audits, or a dashboard yet.
- First inspect the existing code and preserve its behavior.
- Capture local, redacted LangChain runtime events.
- Discover tools and prompt fingerprints automatically.
- Measure which governance fields are available and which need lightweight annotation.
- Generate a draft ACAP for review instead of asking the developer to type every tool.
- Produce one deterministic finding from a controlled local scenario.
- Add OpenTelemetry only after local event extraction is proven.

## Install into the existing repository

1. Create a branch:

   ```bash
   git checkout -b governance-instrumentation-poc
   ```

2. Extract this pack into the **root of the restaurant-agent repository**. Merge the `.claude/` directory if one already exists; do not overwrite useful existing project instructions blindly.

3. Add the contents of `.gitignore.additions` to the repository `.gitignore`.

4. Start Claude Code from the repository root:

   ```bash
   claude
   ```

5. Confirm the project instructions are loaded, then run:

   ```text
   /inspect-restaurant-agent
   ```

6. Review the generated inventory and plan. Then run:

   ```text
   /instrument-langchain-evidence local-jsonl
   /run-evidence-scenarios
   /generate-acap-draft
   /verify-first-objective
   ```

Do not run real payments, place real orders, or create real customer reservations during the experiment. Use local fixtures, mocks, a sandbox, or the application's test mode.

## Recommended Claude Code extensions

Use only what matches the repository:

- Install one official LSP/code-intelligence plugin for the repository language: Python/Pyright or TypeScript.
- Install a security-guidance/review plugin if available in the official marketplace.
- GitHub integration is optional after the repository is connected.
- **No MCP server is required for this objective.** Claude Code already has repository and shell tools. Do not add database, cloud, observability, or production MCP access yet.

Open `/plugin` in Claude Code and use the Discover tab. Official plugins use the `@claude-plugins-official` marketplace.

## Expected outputs

The implementation should create local artifacts similar to:

```text
artifacts/governance/
├── discovery.json
├── events.jsonl
├── coverage.json
├── acap-draft.yaml
├── findings.json
└── run-summary.md
```

These files may contain operational metadata and must remain local unless reviewed and redacted.

## First prompt to Claude

```text
Read CLAUDE.md and docs/FIRST_OBJECTIVE.md. Do not edit code yet.
Run the inspect-restaurant-agent workflow. Identify the installed LangChain version,
agent construction style, entry points, model clients, prompt sources, tools,
existing callbacks/LangSmith/OpenTelemetry setup, test commands, and the smallest
safe instrumentation insertion point. Produce a field-by-field evidence extraction
plan and do not scaffold the wider governance platform.
```
