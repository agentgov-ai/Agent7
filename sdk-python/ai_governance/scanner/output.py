from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ai_governance.core.fingerprint import fingerprint
from ai_governance.core.sanitize import utc_now
from ai_governance.scanner.models import SCANNER_VERSION, build_scan_summary


def format_discovery(
    *,
    candidates: list[dict[str, Any]],
    model_surface: list[dict[str, Any]],
    files_scanned: int,
    functions_seen: int,
    ignored_helpers_count: int,
    root_path: str | Path | None = None,
) -> dict[str, Any]:
    """Build the top-level governance-discovery dict."""
    summary = build_scan_summary(
        files_scanned=files_scanned,
        functions_seen=functions_seen,
        candidates=candidates,
        model_surface=model_surface,
        ignored_helpers_count=ignored_helpers_count,
    )

    result: dict[str, Any] = {
        "schema_version": "0.1",
        "scanner_version": SCANNER_VERSION,
        "generated_at": utc_now(),
        "source": "deterministic_scanner",
        "scan_summary": summary,
        "candidates": candidates,
        "model_surface": model_surface,
    }

    if root_path is not None:
        result["project_hash"] = fingerprint(str(Path(root_path).resolve()))

    return result


def write_governance_discovery(
    discovery: dict[str, Any],
    path: str | Path,
    *,
    fmt: str = "json",
) -> None:
    """Write *discovery* to *path* as JSON or YAML."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    if fmt == "yaml":
        try:
            import yaml  # type: ignore[import-untyped]
        except ImportError as exc:
            raise SystemExit(
                "PyYAML is required for YAML output.  Install with: "
                "pip install agent-governance-sdk[acap]"
            ) from exc
        text = yaml.dump(discovery, default_flow_style=False, sort_keys=True, allow_unicode=True)
    else:
        text = json.dumps(discovery, indent=2, sort_keys=True, ensure_ascii=False)

    path.write_text(text, encoding="utf-8")
