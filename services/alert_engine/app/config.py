from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(slots=True)
class AlertEngineSettings:
    """Application settings for the alert engine service."""

    database_url: str = "sqlite:///./alert_engine.db"
    market_data_url: str = "http://market-data"
    reports_url: str = "http://reports"
    notification_url: str = "http://notification-service"
    evaluation_interval_seconds: float = 15.0

    @classmethod
    def from_env(cls) -> "AlertEngineSettings":
        defaults = cls()
        return cls(
            database_url=os.getenv("ALERT_ENGINE_DATABASE_URL", defaults.database_url),
            market_data_url=os.getenv("ALERT_ENGINE_MARKET_DATA_URL", defaults.market_data_url),
            reports_url=os.getenv("ALERT_ENGINE_REPORTS_URL", defaults.reports_url),
            notification_url=os.getenv("ALERT_ENGINE_NOTIFICATION_URL", defaults.notification_url),
            evaluation_interval_seconds=float(
                os.getenv(
                    "ALERT_ENGINE_EVALUATION_INTERVAL_SECONDS",
                    defaults.evaluation_interval_seconds,
                )
            ),
        )
