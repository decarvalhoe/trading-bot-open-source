from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(slots=True)
class AlertEngineSettings:
    """Application settings for the alert engine service."""

    database_url: str = "sqlite:///./alert_engine.db"
    events_database_url: str = "sqlite:///./alert_events.db"
    market_data_url: str = "http://market-data"
    market_data_stream_url: str = "http://market-data"
    reports_url: str = "http://reports"
    notification_url: str = "http://notification-service"
    evaluation_interval_seconds: float = 15.0
    market_snapshot_ttl_seconds: float = 30.0
    market_event_ttl_seconds: float = 2.0
    reports_ttl_seconds: float = 60.0
    stream_symbols: tuple[str, ...] = ()

    @classmethod
    def from_env(cls) -> "AlertEngineSettings":
        defaults = cls()
        symbols_env = os.getenv("ALERT_ENGINE_STREAM_SYMBOLS")
        if symbols_env is None:
            stream_symbols = defaults.stream_symbols
        else:
            stream_symbols = tuple(
                symbol.strip()
                for symbol in symbols_env.split(",")
                if symbol.strip()
            )
        market_data_url = os.getenv("ALERT_ENGINE_MARKET_DATA_URL", defaults.market_data_url)
        reports_url = os.getenv("ALERT_ENGINE_REPORTS_URL", defaults.reports_url)
        return cls(
            database_url=os.getenv("ALERT_ENGINE_DATABASE_URL", defaults.database_url),
            events_database_url=os.getenv(
                "ALERT_ENGINE_EVENTS_DATABASE_URL",
                os.getenv("ALERT_EVENTS_DATABASE_URL", defaults.events_database_url),
            ),
            market_data_url=market_data_url,
            market_data_stream_url=os.getenv(
                "ALERT_ENGINE_MARKET_DATA_STREAM_URL",
                market_data_url,
            ),
            reports_url=reports_url,
            notification_url=os.getenv("ALERT_ENGINE_NOTIFICATION_URL", defaults.notification_url),
            evaluation_interval_seconds=float(
                os.getenv(
                    "ALERT_ENGINE_EVALUATION_INTERVAL_SECONDS",
                    defaults.evaluation_interval_seconds,
                )
            ),
            market_snapshot_ttl_seconds=float(
                os.getenv(
                    "ALERT_ENGINE_MARKET_SNAPSHOT_TTL_SECONDS",
                    defaults.market_snapshot_ttl_seconds,
                )
            ),
            market_event_ttl_seconds=float(
                os.getenv(
                    "ALERT_ENGINE_MARKET_EVENT_TTL_SECONDS",
                    defaults.market_event_ttl_seconds,
                )
            ),
            reports_ttl_seconds=float(
                os.getenv(
                    "ALERT_ENGINE_REPORTS_TTL_SECONDS",
                    defaults.reports_ttl_seconds,
                )
            ),
            stream_symbols=stream_symbols,
        )
