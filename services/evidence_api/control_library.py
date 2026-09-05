"""Loads canonical controls and enriches findings with control + framework mappings."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONTROLS_PATH = REPO_ROOT / "control-library" / "canonical-controls.yaml"

_cache: dict[str, dict[str, Any]] = {}


def load_control_library(path: Path | None = None) -> dict[str, Any]:
    resolved = str(path or DEFAULT_CONTROLS_PATH)
    if resolved in _cache:
        return _cache[resolved]
    try:
        data = yaml.safe_load(Path(resolved).read_text(encoding="utf-8"))
    except Exception:
        logger.warning("control library not loaded from %s", resolved, exc_info=True)
        data = {}
    _cache[resolved] = data
    return data


def enrich_finding(finding: dict[str, Any], path: Path | None = None) -> dict[str, Any]:
    lib = load_control_library(path)
    rule_mappings = lib.get("rule_mappings") or {}
    control_id = rule_mappings.get(finding.get("rule_id", ""))
    if not control_id:
        return finding
    controls = {c["control_id"]: c for c in (lib.get("controls") or [])}
    control = controls.get(control_id)
    if not control:
        return finding
    finding["failed_control"] = control_id
    finding["failed_control_title"] = control["title"]
    finding["framework_mappings"] = control.get("framework_mappings", {})
    return finding
