---
name: inspect-restaurant-agent
description: Inspect the existing restaurant-agent repository and design the smallest safe evidence-extraction plan. Use before any instrumentation work.
disable-model-invocation: true
---
Inspect the repository without changing code.

Read CLAUDE.md and docs/FIRST_OBJECTIVE.md first.

Produce `docs/generated/REPO_INVENTORY.md` and `docs/generated/INSTRUMENTATION_PLAN.md` containing:

1. Language, package manager, dependency files and exact installed/declared LangChain/LangGraph versions.
2. Application entry points and commands for local run and tests.
3. Agent construction style: create_agent, AgentExecutor, Runnable, LangGraph graph or custom chain.
4. The real invocation path from user input to final response.
5. Model providers and model wrapper classes.
6. Prompt sources: templates, hub references, inline messages, files and dynamic prompt construction.
7. Tools: names, definitions, schemas, modules, side effects and external services.
8. Retrievers, memory, databases and APIs used.
9. Existing callbacks, LangSmith tracing, OpenTelemetry, OpenInference or logging.
10. Current tests and safe fixture/sandbox options.
11. Minimum code insertion points for root callbacks, tool enrichment and approval events.
12. A field-by-field matrix: automatically captured, needs annotation, unavailable, or unsafe to capture.
13. Risks: behavior changes, duplicate events, raw content, secrets, real-world side effects and performance.
14. A small ordered implementation plan with acceptance criteria.

Do not assume raw prompts are required. Do not upgrade dependencies. Do not scaffold the wider governance product.
