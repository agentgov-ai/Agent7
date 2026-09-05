"""Smoke test for the end-to-end governance loop demo.

Run with:  python -m unittest tests.test_full_loop_demo -v
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "sdk-python"))
sys.path.insert(0, str(REPO_ROOT))


class TestFullLoopDemo(unittest.TestCase):

    def test_demo_runs_successfully_and_produces_findings(self) -> None:
        """Run the full governance loop demo in-process and verify results."""
        # Import and run
        sys.path.insert(0, str(REPO_ROOT / "scripts"))
        from run_full_governance_loop_demo import main

        exit_code = main()
        self.assertEqual(exit_code, 0, "Demo should exit successfully with findings")


if __name__ == "__main__":
    unittest.main()
