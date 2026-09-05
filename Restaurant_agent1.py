"""Compatibility launcher for the restaurant-agent example.

The runnable demo lives in examples/restaurant-agent/Restaurant_agent1.py.
Keeping this wrapper preserves the old `python Restaurant_agent1.py` command.
"""
from __future__ import annotations

import runpy
from pathlib import Path


EXAMPLE_SCRIPT = Path(__file__).resolve().parent / "examples" / "restaurant-agent" / "Restaurant_agent1.py"


if __name__ == "__main__":
    runpy.run_path(str(EXAMPLE_SCRIPT), run_name="__main__")
