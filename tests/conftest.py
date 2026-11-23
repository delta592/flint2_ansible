"""Shared pytest fixtures for flint2_ansible."""

from __future__ import annotations

import importlib.util
import sys
from collections.abc import Iterator
from pathlib import Path
from types import ModuleType

import pytest

ROOT = Path(__file__).resolve().parents[1]
GLINET_SCRIPT = ROOT / "scripts" / "glinet_enable_dropbear.py"


@pytest.fixture
def glinet_mod() -> Iterator[ModuleType]:
    """Load scripts/glinet_enable_dropbear.py as a fresh module each test."""
    name = "glinet_enable_dropbear"
    spec = importlib.util.spec_from_file_location(name, GLINET_SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    try:
        yield module
    finally:
        sys.modules.pop(name, None)
