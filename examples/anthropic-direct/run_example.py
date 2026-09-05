from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace

REPO_ROOT = Path(__file__).resolve().parents[2]
SDK_ROOT = REPO_ROOT / "sdk-python"
if str(SDK_ROOT) not in sys.path:
    sys.path.insert(0, str(SDK_ROOT))

from ai_governance import GovernanceClient  # noqa: E402

OUT = Path(__file__).resolve().parent / "events.jsonl"


class FakeAnthropicClient:
    def __init__(self) -> None:
        self.messages = SimpleNamespace(create=self._create)

    def _create(self, **kwargs):
        return SimpleNamespace(
            model=kwargs.get("model"),
            usage=SimpleNamespace(input_tokens=9, output_tokens=5),
            stop_reason="end_turn",
            content=[SimpleNamespace(type="text", text="Hello from fake Anthropic")],
        )


def main() -> int:
    if OUT.exists():
        OUT.unlink()
    gov = GovernanceClient(
        system_id="anthropic-direct-agent",
        deployment_id="local-test",
        environment="local",
        session_id="demo-session-001",
        jsonl_path=OUT,
    )

    if os.environ.get("ANTHROPIC_DIRECT_LIVE") == "1":
        client = gov.anthropic_client()
    else:
        client = gov.anthropic_client(client=FakeAnthropicClient())

    with gov.trace(name="chat_workflow", session_id="demo-session-001"):
        response = client.messages.create(
            model="claude-3-5-sonnet-latest",
            max_tokens=256,
            messages=[{"role": "user", "content": "Hello"}],
        )

    print(json.dumps({"model": response.model, "events": str(OUT)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
