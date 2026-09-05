from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SDK_ROOT = REPO_ROOT / "sdk-python"
sdk_root_text = str(SDK_ROOT)
if sdk_root_text not in sys.path:
    sys.path.insert(0, sdk_root_text)

from ai_governance.core.validation import (  # noqa: E402
    ACTION_TYPES,
    EVENT_TYPES,
    OUTCOME_STATUSES,
    PROMPT_CAPTURE,
    RAW_TEXT_PROBES,
    REQUIRED_FIELDS,
    public_event,
    raw_text_problems,
    validate_event,
)

SCHEMA_PATH = REPO_ROOT / "schemas" / "governance-event.schema.json"

__all__ = [
    "ACTION_TYPES",
    "EVENT_TYPES",
    "OUTCOME_STATUSES",
    "PROMPT_CAPTURE",
    "RAW_TEXT_PROBES",
    "REQUIRED_FIELDS",
    "SCHEMA_PATH",
    "public_event",
    "raw_text_problems",
    "validate_event",
]
