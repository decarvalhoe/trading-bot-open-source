import importlib.util
import os
import sys
from collections.abc import Generator
from pathlib import Path
from types import ModuleType

import pytest
from fastapi.testclient import TestClient

CURRENT_DIR = Path(__file__).resolve().parent

HELPERS_NAME = "config_service_test_helpers"
HELPERS_PATH = CURRENT_DIR / "_helpers.py"


def _load_helpers(name: str, path: Path) -> ModuleType:
    if name in sys.modules:
        return sys.modules[name]

    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)  # type: ignore[arg-type]
    return module


helpers = _load_helpers(HELPERS_NAME, HELPERS_PATH)

CONFIG_FILES = helpers.CONFIG_FILES
app = helpers.app


@pytest.fixture()
def client() -> Generator[TestClient, None, None]:
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture()
def config_env(tmp_path) -> Generator[str, None, None]:
    original_env = os.environ.get("ENVIRONMENT")
    original_dir = os.environ.get("CONFIG_DATA_DIR")
    original_mapping = dict(CONFIG_FILES)

    os.environ["ENVIRONMENT"] = "test"
    os.environ["CONFIG_DATA_DIR"] = str(tmp_path)

    CONFIG_FILES.clear()
    for env in ("dev", "test", "prod"):
        CONFIG_FILES[env] = os.path.join(str(tmp_path), f"config.{env}.json")

    try:
        yield str(tmp_path)
    finally:
        CONFIG_FILES.clear()
        CONFIG_FILES.update(original_mapping)

        if original_env is None:
            os.environ.pop("ENVIRONMENT", None)
        else:
            os.environ["ENVIRONMENT"] = original_env
        if original_dir is None:
            os.environ.pop("CONFIG_DATA_DIR", None)
        else:
            os.environ["CONFIG_DATA_DIR"] = original_dir
