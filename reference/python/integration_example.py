"""Illustrative only: adapt to the repository's real agent and invocation signature."""

from governance_probe import GovernanceCallback, GovernanceEventWriter, write_tool_discovery


def build_governance_callback(tools):
    write_tool_discovery(tools, "artifacts/governance/discovery.json")
    writer = GovernanceEventWriter("artifacts/governance/events.jsonl")
    return GovernanceCallback(
        writer=writer,
        system_id="restaurant-agent",
        deployment_id="local-test",
        environment="local",
        agent_id="restaurant-agent-main",
        tool_catalog={},  # Load generated overrides after review.
    )


def invoke_with_governance(agent, user_input, tools):
    callback = build_governance_callback(tools)
    return agent.invoke(
        user_input,
        config={
            "callbacks": [callback],
            "tags": ["governance-poc"],
            "metadata": {
                "system_id": "restaurant-agent",
                "deployment_id": "local-test",
            },
        },
    )
