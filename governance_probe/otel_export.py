from __future__ import annotations

from ._compat import ensure_sdk_path

ensure_sdk_path()

from ai_governance.otel_export import *  # noqa: F401,F403,E402
from ai_governance.otel_export import main  # noqa: E402


if __name__ == "__main__":
    raise SystemExit(main())
