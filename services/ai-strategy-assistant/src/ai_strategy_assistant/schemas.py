"""Pydantic models shared between the assistant service and consumers."""

from __future__ import annotations

from enum import Enum
from typing import Dict, List, Optional

from pydantic import BaseModel, Field


class StrategyFormat(str, Enum):
    """Output formats supported by the assistant."""

    YAML = "yaml"
    PYTHON = "python"
    BOTH = "both"


class StrategyGenerationRequest(BaseModel):
    """Inputs describing the trading idea the assistant should materialise."""

    prompt: str = Field(..., description="Intent or trading idea expressed in natural language")
    preferred_format: StrategyFormat = Field(
        default=StrategyFormat.YAML,
        description="Requested output format for the strategy definition",
    )
    risk_profile: Optional[str] = Field(
        default=None, description="Risk appetite description (e.g. conservative, aggressive)"
    )
    timeframe: Optional[str] = Field(
        default=None, description="Primary timeframe the strategy should operate on"
    )
    capital: Optional[str] = Field(
        default=None,
        description="Capital or sizing constraints the strategy should take into account",
    )
    indicators: List[str] = Field(
        default_factory=list,
        description="List of indicators or data sources the user wants to leverage",
    )
    notes: Optional[str] = Field(
        default=None,
        description="Additional instructions or constraints to pass to the assistant",
    )


class StrategyDraft(BaseModel):
    """Draft produced by the AI assistant."""

    summary: str = Field(..., description="Short explanation of the proposed strategy")
    yaml_strategy: Optional[str] = Field(
        default=None, description="Declarative YAML version of the strategy"
    )
    python_strategy: Optional[str] = Field(
        default=None, description="Python implementation for more advanced scenarios"
    )
    indicators: List[str] = Field(
        default_factory=list,
        description="Indicators referenced or recommended by the assistant",
    )
    warnings: List[str] = Field(
        default_factory=list, description="Caveats or risk considerations returned by the model"
    )
    metadata: Dict[str, object] = Field(
        default_factory=dict,
        description="Additional metadata (suggested name, parameters, etc.)",
    )


class StrategyGenerationResponse(BaseModel):
    """Response returned by the HTTP microservice."""

    draft: StrategyDraft
    request: StrategyGenerationRequest
