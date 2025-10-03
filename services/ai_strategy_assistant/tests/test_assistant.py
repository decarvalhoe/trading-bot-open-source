import json
from dataclasses import dataclass

from fastapi.testclient import TestClient

import json
from dataclasses import dataclass

from fastapi.testclient import TestClient

from ai_strategy_assistant import (
    AIStrategyAssistant,
    StrategyDraft,
    StrategyGenerationRequest,
    StrategyGenerationResponse,
)
from ai_strategy_assistant.assistant import StrategyGenerationError
from ai_strategy_assistant.schemas import StrategyFormat
from ai_strategy_assistant_service.app import main as service_main


@dataclass
class FakeMessage:
    content: str


class FakeLLM:
    def __init__(self, payload: StrategyDraft):
        self._payload = payload
        self.invocations = []

    def invoke(self, messages):  # noqa: D401 - interface compatible avec LangChain
        self.invocations.append(messages)
        return FakeMessage(content=json.dumps(self._payload.model_dump()))


def test_assistant_builds_draft():
    draft = StrategyDraft(
        summary="Trend following on BTC",
        yaml_strategy="name: trend",
        python_strategy="class Strategy: ...",
        indicators=["EMA", "RSI"],
        warnings=["Backtest sur données limitées"],
        metadata={"suggested_name": "BTC Trend"},
    )
    fake_llm = FakeLLM(draft)
    assistant = AIStrategyAssistant(llm=fake_llm)

    request = StrategyGenerationRequest(
        prompt="Capturer les tendances 4h sur BTC",
        preferred_format=StrategyFormat.BOTH,
        indicators=["EMA", "RSI"],
        risk_profile="modéré",
    )

    response = assistant.generate(request)

    assert isinstance(response, StrategyGenerationResponse)
    assert response.draft.summary == draft.summary
    assert response.draft.yaml_strategy == draft.yaml_strategy
    assert response.draft.python_strategy == draft.python_strategy
    assert response.draft.indicators == ["EMA", "RSI"]
    assert response.draft.metadata["prompt"] == request.prompt
    assert fake_llm.invocations, "Le LLM doit être appelé"


def test_assistant_filters_formats():
    draft = StrategyDraft(
        summary="Counter trend",
        yaml_strategy="name: counter",
        python_strategy="class Strategy: ...",
    )
    assistant = AIStrategyAssistant(llm=FakeLLM(draft))

    request = StrategyGenerationRequest(
        prompt="Contre tendance sur ETH",
        preferred_format=StrategyFormat.YAML,
    )

    response = assistant.generate(request)

    assert response.draft.yaml_strategy is not None
    assert response.draft.python_strategy is None


def test_assistant_raises_on_invalid_output(monkeypatch):
    class EmptyLLM(FakeLLM):
        def __init__(self):
            super().__init__(payload=StrategyDraft(summary=""))

        def invoke(self, messages):
            return FakeMessage(content="")

    assistant = AIStrategyAssistant(llm=EmptyLLM())
    request = StrategyGenerationRequest(prompt="", preferred_format=StrategyFormat.YAML)

    try:
        assistant.generate(request)
    except StrategyGenerationError as exc:
        assert "Réponse du modèle" in str(exc)
    else:  # pragma: no cover - safety belt
        raise AssertionError("StrategyGenerationError attendu")


def test_microservice_endpoint_uses_injected_assistant(monkeypatch):
    draft = StrategyDraft(
        summary="Breakout",
        yaml_strategy="name: breakout",
        python_strategy=None,
        indicators=["Bollinger"],
    )
    fake_assistant = AIStrategyAssistant(llm=FakeLLM(draft))
    monkeypatch.setattr(service_main, "assistant", fake_assistant)

    client = TestClient(service_main.app)
    payload = {
        "prompt": "Breakout sur BTC",
        "preferred_format": "yaml",
        "indicators": ["Bollinger"],
    }
    response = client.post("/generate", json=payload)

    assert response.status_code == 200
    body = response.json()
    assert body["draft"]["summary"] == "Breakout"
    assert body["draft"]["yaml_strategy"] == "name: breakout"
    assert body["draft"]["python_strategy"] is None
