"""Load form configuration values for the ERP app."""
from __future__ import annotations

import json
from pathlib import Path
from typing import List


def load_state_names() -> List[str]:
    """Load the list of state names from the bundled JSON config file."""
    config_path = Path(__file__).with_name("state_names.json")
    if not config_path.exists():
        return []

    try:
        with config_path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
    except Exception:
        return []

    if isinstance(data, list):
        return [str(item) for item in data if item is not None]
    return []
