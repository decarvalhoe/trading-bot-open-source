import json
import os
from typing import Any, Dict

DATA_DIR = os.environ.get("CONFIG_DATA_DIR", "/data")
CONFIG_FILES: Dict[str, str] = {
    "dev": os.path.join(DATA_DIR, "config.dev.json"),
    "test": os.path.join(DATA_DIR, "config.test.json"),
    "prod": os.path.join(DATA_DIR, "config.prod.json"),
}


def read_config_for_env(env: str) -> Dict[str, Any] | None:
    path = CONFIG_FILES.get(env)
    if not path or not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def persist_config(settings) -> None:
    env = settings.ENVIRONMENT
    path = CONFIG_FILES.get(env)
    if not path:
        raise ValueError(f"Environnement inconnu : {env}")

    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(settings.model_dump_json(indent=2))
