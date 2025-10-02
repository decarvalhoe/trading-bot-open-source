import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
SERVICE = ROOT / "ai_strategy_assistant_service"

for path in (SRC, SERVICE, ROOT):
    if path.exists():
        sys.path.insert(0, str(path))
