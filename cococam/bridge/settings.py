import json
import os
from pathlib import Path


def options():
    path = Path(os.getenv("COCOCAM_OPTIONS", "/data/options.json"))
    if not path.is_file():
        return {}
    with path.open() as stream:
        value = json.load(stream)
    return value if isinstance(value, dict) else {}


def live_duration(config):
    value = config.get("live_seconds", 60)
    if type(value) is not int or not 15 <= value <= 300:
        raise ValueError("live_seconds")
    return value
