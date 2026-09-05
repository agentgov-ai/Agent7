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


class FakeOpenAIClient:
    def __init__(self) -> None:
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, **kwargs):
        return SimpleNamespace(
            model=kwargs.get("model"),
            usage=SimpleNamespace(prompt_tokens=8, completion_tokens=4, total_tokens=12),
            choices=[SimpleNamespace(finish_reason="stop", message=SimpleNamespace(content="Hello from fake OpenAI"))],
        )


def main() -> int:
    if OUT.exists():
        OUT.unlink()
    gov = GovernanceClient(
        system_id="openai-direct-agent",
        deployment_id="local-test",
        environment="local",
        session_id="demo-session-001",
        jsonl_path=OUT,
    )

    if os.environ.get("OPENAI_DIRECT_LIVE") == "1":
        client = gov.openai_client()
    else:
        client = gov.openai_client(client=FakeOpenAIClient())

    with gov.trace(name="chat_workflow", session_id="demo-session-001"):
        response = client.chat.completions.create(
            model="gpt-4.1-mini",
            messages=[{"role": "user", "content": "Hello"}],
        )

    print(json.dumps({"model": response.model, "events": str(OUT)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
