from __future__ import annotations

import sys
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SDK_ROOT = REPO_ROOT / "sdk-python"


class SdkLayoutTest(unittest.TestCase):
    def test_ai_governance_import_path_exposes_reusable_probe_api(self):
        sys.path.insert(0, str(SDK_ROOT))
        try:
            from ai_governance import GovernanceCallback, GovernanceEventWriter, discover_tools, fingerprint, sanitize
        finally:
            sys.path.remove(str(SDK_ROOT))

        self.assertIsNotNone(GovernanceCallback)
        self.assertIsNotNone(GovernanceEventWriter)
        self.assertEqual(discover_tools([]), [])
        self.assertTrue(fingerprint({"ok": True}).startswith("sha256:"))
        self.assertEqual(sanitize({"api_key": "secret"})["api_key"], "<redacted>")


if __name__ == "__main__":
    unittest.main()
