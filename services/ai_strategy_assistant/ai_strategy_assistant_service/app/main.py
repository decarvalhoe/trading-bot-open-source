"""HTTP microservice delegating to the LangChain powered assistant."""

from __future__ import annotations

import logging
from fastapi import FastAPI, HTTPException

from ai_strategy_assistant import (
    AIStrategyAssistant,
    StrategyGenerationError,
    StrategyGenerationRequest,
    StrategyGenerationResponse,
)

logger = logging.getLogger(__name__)

app = FastAPI(title="AI Strategy Assistant", version="0.1.0")
assistant = AIStrategyAssistant()


@app.post("/generate", response_model=StrategyGenerationResponse)
async def generate_strategy(payload: StrategyGenerationRequest) -> StrategyGenerationResponse:
    """Generate a draft strategy from a natural language description."""

    try:
        return assistant.generate(payload)
    except StrategyGenerationError as exc:
        logger.exception("Strategy generation failed")
        raise HTTPException(status_code=502, detail=str(exc)) from exc
