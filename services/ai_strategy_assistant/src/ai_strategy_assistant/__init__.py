"""AI strategy assistant module using LangChain/OpenAI to craft trading drafts."""

from .assistant import AIStrategyAssistant, StrategyGenerationError
from .schemas import StrategyDraft, StrategyGenerationRequest, StrategyGenerationResponse

__all__ = [
    "AIStrategyAssistant",
    "StrategyDraft",
    "StrategyGenerationRequest",
    "StrategyGenerationResponse",
    "StrategyGenerationError",
]
