from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, ConfigDict


class MarketEvent(BaseModel):
    symbol: str = Field(..., description="Symbol identifier for the market event")
    price: float = Field(..., description="Last traded price")
    volume: float | None = Field(None, description="Traded volume for the event")
    bid: float | None = Field(None, description="Best bid price")
    ask: float | None = Field(None, description="Best ask price")
    metadata: dict[str, Any] | None = Field(None, description="Additional event metadata")


class AlertTriggerRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    rule_id: int
    triggered_at: datetime
    context: dict[str, Any] | None


class AlertRuleSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    trigger_id: int = Field(..., description="Identifier of the trigger event")
    rule_id: int = Field(..., description="Identifier of the originating rule")
    name: str = Field(..., description="Rule display name")
    symbol: str = Field(..., description="Instrument evaluated by the rule")
    severity: str = Field(..., description="Severity declared on the rule")
    expression: str = Field(..., description="Expression evaluated to generate the trigger")
    triggered_at: datetime
    context: dict[str, Any] | None = None


class AlertEvaluationResponse(BaseModel):
    triggered: bool
    triggers: list[AlertTriggerRead] = Field(default_factory=list)
