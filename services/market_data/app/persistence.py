from __future__ import annotations

from typing import Iterable, Mapping

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from .tables import MarketDataOHLCV, MarketDataTick


def persist_ohlcv(session: Session, rows: Iterable[Mapping[str, object]]) -> None:
    payload = list(rows)
    if not payload:
        return

    insert_stmt = insert(MarketDataOHLCV)
    stmt = (
        insert_stmt
        .values(
            [
                {
                    "exchange": row["exchange"],
                    "symbol": row["symbol"],
                    "interval": row["interval"],
                    "timestamp": row["timestamp"],
                    "open": row["open"],
                    "high": row["high"],
                    "low": row["low"],
                    "close": row["close"],
                    "volume": row.get("volume"),
                    "quote_volume": row.get("quote_volume"),
                    "trades": row.get("trades"),
                    "extra": row.get("extra"),
                }
                for row in payload
            ]
        )
        .on_conflict_do_update(
            constraint="uq_ohlcv_bar",
            set_={
                "open": insert_stmt.excluded.open,
                "high": insert_stmt.excluded.high,
                "low": insert_stmt.excluded.low,
                "close": insert_stmt.excluded.close,
                "volume": insert_stmt.excluded.volume,
                "quote_volume": insert_stmt.excluded.quote_volume,
                "trades": insert_stmt.excluded.trades,
                "extra": insert_stmt.excluded.extra,
            },
        )
    )
    session.execute(stmt)


def persist_ticks(session: Session, rows: Iterable[Mapping[str, object]]) -> None:
    payload = list(rows)
    if not payload:
        return

    stmt = (
        insert(MarketDataTick)
        .values(payload)
        .on_conflict_do_nothing(constraint="uq_tick")
    )
    session.execute(stmt)
