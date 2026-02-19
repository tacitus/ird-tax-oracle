"""Fixtures for the evaluation suite."""

from pathlib import Path
from typing import Any

import pytest
import yaml

EVAL_DIR = Path(__file__).parent


@pytest.fixture(scope="session")
def eval_scenarios() -> list[dict[str, Any]]:
    """Load evaluation scenarios from YAML."""
    path = EVAL_DIR / "test_scenarios.yaml"
    data = yaml.safe_load(path.read_text())
    return data["scenarios"]
