"""Configuration loading utilities."""

from pathlib import Path
from typing import Any

import yaml


def load_yaml_config(filename: str) -> dict[str, Any]:
    """Load a YAML config file from the config/ directory."""
    config_dir = Path(__file__).parent
    config_path = config_dir / filename
    with open(config_path) as f:
        return yaml.safe_load(f)
