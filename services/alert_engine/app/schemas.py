from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


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


class ThresholdDirection(str, Enum):
    ABOVE = "above"
    BELOW = "below"


class NotificationChannelType(str, Enum):
    EMAIL = "email"
    PUSH = "push"
    WEBHOOK = "webhook"


def _slugify(value: str) -> str:
    cleaned = [char.lower() if char.isalnum() else "_" for char in value.strip()]
    slug = "".join(cleaned)
    while "__" in slug:
        slug = slug.replace("__", "_")
    return slug.strip("_")


class NotificationChannel(BaseModel):
    type: NotificationChannelType
    target: str | None = Field(default=None, max_length=255)
    enabled: bool = Field(default=True)


class PerformanceCondition(BaseModel):
    enabled: bool = Field(default=False)
    operator: ThresholdDirection = Field(default=ThresholdDirection.BELOW)
    value: float | None = Field(default=None)

    def expression(self, variable: str) -> str | None:
        if not self.enabled or self.value is None:
            return None
        comparator = ">=" if self.operator is ThresholdDirection.ABOVE else "<="
        return f"{variable} {comparator} {self.value}"


class IndicatorCondition(BaseModel):
    id: str = Field(..., min_length=1)
    name: str = Field(..., min_length=1)
    operator: ThresholdDirection = Field(default=ThresholdDirection.ABOVE)
    value: float = Field(...)
    lookback: int | None = Field(default=None, ge=1, description="Lookback period in minutes")
    enabled: bool = Field(default=True)

    @field_validator("value")
    @classmethod
    def _ensure_numeric(cls, value: float) -> float:
        return float(value)

    def variable_name(self) -> str:
        base = _slugify(self.name)
        if self.lookback:
            base = f"{base}_{self.lookback}"
        if not base:
            base = _slugify(self.id) or "indicator"
        return f"indicator_{base}"

    def expression(self) -> str | None:
        if not self.enabled:
            return None
        comparator = ">=" if self.operator is ThresholdDirection.ABOVE else "<="
        return f"{self.variable_name()} {comparator} {self.value}"


class RuleConditions(BaseModel):
    pnl: PerformanceCondition = Field(default_factory=PerformanceCondition)
    drawdown: PerformanceCondition = Field(default_factory=PerformanceCondition)
    indicators: list[IndicatorCondition] = Field(default_factory=list)

    def expressions(self) -> list[str]:
        expressions: list[str] = []
        pnl_expression = self.pnl.expression("pnl")
        if pnl_expression:
            expressions.append(pnl_expression)
        drawdown_expression = self.drawdown.expression("drawdown")
        if drawdown_expression:
            expressions.append(drawdown_expression)
        for indicator in self.indicators:
            indicator_expression = indicator.expression()
            if indicator_expression:
                expressions.append(indicator_expression)
        return expressions


class AlertRuleDefinition(BaseModel):
    symbol: str = Field(..., min_length=1, max_length=32)
    timeframe: str | None = Field(default=None, description="Optional timeframe hint")
    conditions: RuleConditions = Field(default_factory=RuleConditions)

    def build_expression(self) -> str:
        expressions = self.conditions.expressions()
        return " and ".join(expressions)


class AlertRuleBase(BaseModel):
    title: str = Field(..., min_length=1)
    detail: str = Field(..., min_length=1)
    risk: str = Field(default="info")
    acknowledged: bool = Field(default=False)
    rule: AlertRuleDefinition
    channels: list[NotificationChannel] = Field(default_factory=list)
    throttle_seconds: int = Field(default=0, ge=0)

    def expression(self) -> str:
        expression = self.rule.build_expression()
        if not expression:
            raise ValueError("Au moins une condition doit être définie pour la règle d'alerte.")
        return expression

    def dump_channels(self) -> list[dict[str, Any]]:
        return [channel.model_dump(mode="json") for channel in self.channels]

    def dump_rule(self) -> dict[str, Any]:
        return self.rule.model_dump(mode="json")


class AlertRuleCreate(AlertRuleBase):
    """Payload accepted when creating a new alert rule."""


class AlertRuleUpdate(BaseModel):
    model_config = ConfigDict(extra="ignore")

    title: str | None = None
    detail: str | None = None
    risk: str | None = None
    acknowledged: bool | None = None
    rule: AlertRuleDefinition | None = None
    channels: list[NotificationChannel] | None = None
    throttle_seconds: int | None = Field(default=None, ge=0)

    def to_update_mapping(self) -> dict[str, Any]:
        payload: dict[str, Any] = {}
        if self.title is not None:
            payload["name"] = self.title
        if self.detail is not None:
            payload["detail"] = self.detail
        if self.risk is not None:
            payload["severity"] = self.risk
        if self.acknowledged is not None:
            payload["acknowledged"] = self.acknowledged
        if self.rule is not None:
            expression = self.rule.build_expression()
            if not expression:
                raise ValueError("Au moins une condition doit être définie pour la règle d'alerte.")
            payload["symbol"] = self.rule.symbol
            payload["expression"] = expression
            payload["conditions"] = self.rule.model_dump(mode="json")
        if self.channels is not None:
            payload["channels"] = [
                channel.model_dump(mode="json") for channel in self.channels
            ]
        if self.throttle_seconds is not None:
            payload["throttle_seconds"] = self.throttle_seconds
        return payload


class AlertRuleRead(BaseModel):
    """Representation of an alert rule returned by the API."""

    id: int
    title: str
    detail: str
    risk: str
    acknowledged: bool
    created_at: datetime
    updated_at: datetime
    rule: AlertRuleDefinition
    channels: list[NotificationChannel]
    throttle_seconds: int

    @classmethod
    def from_orm_rule(cls, rule: "AlertRule") -> "AlertRuleRead":  # type: ignore[name-defined]
        from .models import AlertRule as ORMRule  # Local import to avoid circular dependency

        if not isinstance(rule, ORMRule):
            raise TypeError("Expected an AlertRule ORM instance")

        stored_definition = rule.conditions or {}
        if not isinstance(stored_definition, dict):
            stored_definition = {}
        stored_definition.setdefault("symbol", rule.symbol)
        definition = AlertRuleDefinition.model_validate(stored_definition)

        channels_data = rule.channels or []
        channels = [NotificationChannel.model_validate(channel) for channel in channels_data]

        return cls(
            id=rule.id,
            title=rule.name,
            detail=rule.detail,
            risk=rule.severity,
            acknowledged=rule.acknowledged,
            created_at=rule.created_at,
            updated_at=rule.updated_at,
            rule=definition,
            channels=channels,
            throttle_seconds=rule.throttle_seconds or 0,
        )


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
