from __future__ import annotations

import logging
import os
from importlib import metadata as importlib_metadata
from pathlib import Path
from typing import Any, Iterable

import yaml

from ..callback import GovernanceCallback
from ..discovery import write_tool_discovery
from ..writer import GovernanceEventWriter

logger = logging.getLogger(__name__)

_TRACKED_PACKAGES = (
    "langchain",
    "langchain-core",
    "langchain-openai",
    "langgraph",
    "faiss-cpu",
    "sentence-transformers",
)


def _package_versions() -> dict[str, str | None]:
    versions: dict[str, str | None] = {}
    for package in _TRACKED_PACKAGES:
        try:
            versions[package] = importlib_metadata.version(package)
        except importlib_metadata.PackageNotFoundError:
            versions[package] = None
    return versions


def load_overrides(path: str | Path) -> dict[str, dict[str, Any]]:
    """Load the human-maintained tool annotation overrides (may be absent)."""
    override_file = Path(path)
    if not override_file.exists():
        logger.warning("governance overrides file not found: %s", override_file)
        return {}
    data = yaml.safe_load(override_file.read_text(encoding="utf-8")) or {}
    tools = data.get("tools") or {}
    return {str(name): dict(meta or {}) for name, meta in tools.items()}


class Governance:
    """Holds the callback plus the config fragment to merge at invoke time."""

    def __init__(self, *, callback: GovernanceCallback, tags: list[str], metadata: dict[str, Any]) -> None:
        self.callback = callback
        self.tags = tags
        self.metadata = metadata

    def merge_invoke_config(self, config: dict[str, Any]) -> dict[str, Any]:
        merged = dict(config)
        merged["callbacks"] = list(merged.get("callbacks") or []) + [self.callback]
        merged["tags"] = list(merged.get("tags") or []) + list(self.tags)
        existing_metadata = dict(merged.get("metadata") or {})
        metadata = {**existing_metadata, **self.metadata}
        configurable = merged.get("configurable") or {}
        if "session_id" not in metadata and isinstance(configurable, dict):
            thread_id = configurable.get("thread_id")
            if thread_id is not None:
                metadata["session_id"] = str(thread_id)
        merged["metadata"] = metadata
        return merged


def init_governance(
    *,
    tools: Iterable[Any],
    system_prompt: str | None = None,
    model_name: str | None = None,
    model_provider: str | None = None,
    system_id: str = "restaurant-agent",
    deployment_id: str = "local-test",
    environment: str = "local",
    agent_id: str = "restaurant-agent-main",
    overrides_path: str | Path = "governance-tool-overrides.yaml",
    artifacts_dir: str | Path = "artifacts/governance",
) -> Governance | None:
    """Build the evidence layer. Returns None if construction fails (fail-open)."""
    try:
        tools = list(tools)
        artifacts = Path(artifacts_dir)
        writer = GovernanceEventWriter(
            artifacts / "events.jsonl",
            api_endpoint=os.environ.get("GOVERNANCE_API_ENDPOINT"),
        )
        catalog = load_overrides(overrides_path)
        write_tool_discovery(
            tools,
            artifacts / "discovery.json",
            system_prompt=system_prompt,
            model={"provider": model_provider, "name": model_name},
            extra={"package_versions": _package_versions(), "agent_id": agent_id},
        )
        callback = GovernanceCallback(
            writer=writer,
            system_id=system_id,
            deployment_id=deployment_id,
            environment=environment,
            agent_id=agent_id,
            tool_catalog=catalog,
            model_provider=model_provider,
        )
        metadata = {
            "system_id": system_id,
            "deployment_id": deployment_id,
            "environment": environment,
            "agent_id": agent_id,
        }
        return Governance(callback=callback, tags=["governance-poc"], metadata=metadata)
    except Exception:
        logger.warning("governance initialization failed; continuing without evidence", exc_info=True)
        return None
