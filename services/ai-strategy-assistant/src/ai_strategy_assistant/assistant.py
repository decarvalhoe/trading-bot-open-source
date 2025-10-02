"""Core orchestration logic used by the AI strategy assistant."""

from __future__ import annotations

import logging
from typing import Iterable

from functools import partial

from langchain.output_parsers import PydanticOutputParser
from langchain.prompts import ChatPromptTemplate
from langchain_core.messages import BaseMessage
from langchain_openai import ChatOpenAI

from .schemas import (
    StrategyDraft,
    StrategyFormat,
    StrategyGenerationRequest,
    StrategyGenerationResponse,
)

logger = logging.getLogger(__name__)


class StrategyGenerationError(RuntimeError):
    """Raised when the assistant cannot transform the LLM output into a draft."""


class AIStrategyAssistant:
    """Helper orchestrating a LangChain pipeline for strategy ideation."""

    def __init__(
        self,
        llm: ChatOpenAI | None = None,
        *,
        model: str = "gpt-4o-mini",
        temperature: float = 0.2,
    ) -> None:
        self._llm: ChatOpenAI | None = None
        self._llm_factory = None
        if llm is not None:
            self._llm = llm
        else:
            try:
                self._llm = ChatOpenAI(model=model, temperature=temperature)
            except Exception as exc:  # pragma: no cover - environment fallback
                logger.warning("ChatOpenAI initialisation failed: %s", exc)
                self._llm = None
                self._llm_factory = partial(ChatOpenAI, model=model, temperature=temperature)
        self._parser = PydanticOutputParser(pydantic_object=StrategyDraft)
        self._prompt = self._build_prompt()

    def _build_prompt(self) -> ChatPromptTemplate:
        template = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    "Tu es un assistant quant expérimenté. Transforme les idées en stratégies"
                    " de trading exploitables pour notre moteur. Analyse les contraintes et"
                    " retourne un plan prudent qui mentionne les risques clés.",
                ),
                (
                    "human",
                    """
Analyse l'idée de trading suivante et propose une stratégie exploitable.
Contexte:
- Objectif: {prompt}
- Profil de risque: {risk_profile}
- Timeframe: {timeframe}
- Capital disponible: {capital}
- Indicateurs souhaités: {indicators}
- Instructions additionnelles: {notes}

Retourne un objet structuré suivant les instructions:
{format_instructions}

Respecte les règles:
- Pour `yaml_strategy`, fournis un bloc YAML complet pour une stratégie déclarative.
- Pour `python_strategy`, écris une classe ou fonction autonome (pas de dépendances externes).
- Fournis systématiquement un résumé, même si un format n'est pas demandé.
- Si un format n'est pas pertinent, laisse le champ à null.
- Ajoute des avertissements si les hypothèses sont fortes ou les données manquent.
""",
                ),
            ]
        )
        return template.partial(format_instructions=self._parser.get_format_instructions())

    def _invoke_llm(self, messages: Iterable[BaseMessage]) -> StrategyDraft:
        if self._llm is None:
            if self._llm_factory is None:
                raise StrategyGenerationError("Client OpenAI non configuré")
            try:
                self._llm = self._llm_factory()
            except Exception as exc:  # pragma: no cover - configuration invalid
                logger.error("Impossible d'initialiser ChatOpenAI", exc_info=exc)
                raise StrategyGenerationError("Client OpenAI non configuré") from exc
        response = self._llm.invoke(messages)  # type: ignore[no-untyped-call]
        content = getattr(response, "content", None)
        if not content or not isinstance(content, str):
            logger.error("Unexpected LLM response: %s", response)
            raise StrategyGenerationError("Réponse du modèle vide ou invalide")
        try:
            draft = self._parser.parse(content)
        except Exception as exc:  # pragma: no cover - defensive logging
            logger.exception("Impossible de parser la réponse LLM", exc_info=exc)
            raise StrategyGenerationError("Impossible d'interpréter la réponse du modèle") from exc
        return draft

    def generate(self, request: StrategyGenerationRequest) -> StrategyGenerationResponse:
        messages = self._prompt.format_messages(
            prompt=request.prompt,
            risk_profile=request.risk_profile or "non spécifié",
            timeframe=request.timeframe or "non spécifié",
            capital=request.capital or "non spécifié",
            indicators=", ".join(request.indicators) if request.indicators else "non spécifié",
            notes=request.notes or "aucune",
        )
        draft = self._invoke_llm(messages)

        if request.preferred_format == StrategyFormat.YAML:
            draft.python_strategy = None
        elif request.preferred_format == StrategyFormat.PYTHON:
            draft.yaml_strategy = None

        if not draft.indicators and request.indicators:
            draft.indicators = request.indicators

        draft.metadata.setdefault("prompt", request.prompt)
        draft.metadata.setdefault("risk_profile", request.risk_profile)
        draft.metadata.setdefault("timeframe", request.timeframe)

        return StrategyGenerationResponse(draft=draft, request=request)


__all__ = ["AIStrategyAssistant", "StrategyGenerationError"]
