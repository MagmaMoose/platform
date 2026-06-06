"""Shared pytest fixtures."""

from __future__ import annotations

import sys
from pathlib import Path

# Allow `import mikrotik_minder_agent` without installing the package in test runs.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
