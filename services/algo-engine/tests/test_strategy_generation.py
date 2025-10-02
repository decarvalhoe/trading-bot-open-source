from typing import Any, Dict

from fastapi.testclient import TestClient

from algo_engine.app.main import app
from algo_engine.app import main as main_module


class DummyAssistant:
    def __init__(self, response: Any) -> None:
        self.response = response
        self.calls: list[Any] = []

    def generate(self, request: Any) -> Any:
        self.calls.append(request)
        return self.response


def test_generate_strategy_returns_draft(monkeypatch):
    from ai_strategy_assistant import StrategyDraft, StrategyGenerationResponse
    from ai_strategy_assistant.schemas import StrategyGenerationRequest, StrategyFormat

    draft = StrategyDraft(
        summary="Breakout momentum",
        yaml_strategy="""
name: breakout-ai
rules:
  - when:
      indicator: price
      operator: gt
      value: 100
    signal:
      action: buy
      size: 1
  - when:
      indicator: price
      operator: lt
      value: 95
    signal:
      action: sell
      size: 1
parameters:
  timeframe: 1h
""",
        python_strategy="class Strategy: ...",
        indicators=["EMA", "RSI"],
        warnings=["Vérifier la liquidité"],
        metadata={"suggested_name": "Breakout AI"},
    )
    request = StrategyGenerationRequest(
        prompt="Breakout sur BTC",
        preferred_format=StrategyFormat.BOTH,
        indicators=["EMA"],
    )
    response = StrategyGenerationResponse(draft=draft, request=request)

    assistant = DummyAssistant(response)
    monkeypatch.setattr(main_module, "ai_assistant", assistant)

    client = TestClient(app)
    payload: Dict[str, Any] = {
        "prompt": "Breakout sur BTC",
        "preferred_format": "both",
        "indicators": ["EMA"],
        "risk_profile": "modéré",
        "timeframe": "1h",
    }
    result = client.post("/strategies/generate", json=payload)

    assert result.status_code == 200
    body = result.json()
    assert body["draft"]["summary"] == "Breakout momentum"
    assert "rules" in body["draft"]["yaml"]
    assert body["draft"]["python"].startswith("class")
    assert body["draft"]["indicators"] == ["EMA", "RSI"]
    assert assistant.calls, "L'assistant doit être invoqué"

    edited_yaml = body["draft"]["yaml"] + "\nmetadata:\n  source: ai"
    import_payload = {
        "format": "yaml",
        "content": edited_yaml,
        "enabled": False,
        "tags": ["ai"],
    }
    import_response = client.post("/strategies/import", json=import_payload)
    assert import_response.status_code == 201
    created = import_response.json()
    assert created["source_format"] == "yaml"
    assert created["tags"] == ["ai"]
