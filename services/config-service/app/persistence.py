import json, os
from typing import Any, Dict

DATA_DIR = os.environ.get("CONFIG_DATA_DIR", "/data")
FILES = {
    "dev": os.path.join(DATA_DIR, "config.dev.json"),
    "test": os.path.join(DATA_DIR, "config.test.json"),
    "prod": os.path.join(DATA_DIR, "config.prod.json"),
}

def read_config_for_env(env: str) -> Dict[str, Any] | None:
    path = FILES.get(env)
    if not path or not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def persist_config(settings) -> None:
    env = settings.ENVIRONMENT
    path = FILES.get(env)
    if not path:
        raise ValueError(f"Unknown ENVIRONMENT {env}")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(settings.model_dump(), f, ensure_ascii=False, indent=2)
