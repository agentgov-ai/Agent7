from __future__ import annotations

import sys
from pathlib import Path


def ensure_sdk_path() -> None:
    sdk_root = Path(__file__).resolve().parents[1] / "sdk-python"
    sdk_root_text = str(sdk_root)
    if sdk_root_text not in sys.path:
        sys.path.insert(0, sdk_root_text)
