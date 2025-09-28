#!/usr/bin/env python3
"""Trigger the sandbox MVP flow without relying on running services."""
from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from typing import Any

from providers.limits import build_plan, get_pair_limit
from schemas.market import ExecutionVenue, OrderRequest, OrderSide, OrderType


def _parse_order_type(value: str) -> OrderType:
    try:
        return OrderType(value.lower())  # type: ignore[arg-type]
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"Unsupported order type: {value}") from exc


def _parse_side(value: str) -> OrderSide:
    try:
        return OrderSide(value.lower())  # type: ignore[arg-type]
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"Unsupported order side: {value}") from exc


def _parse_venue(value: str) -> ExecutionVenue:
    try:
        return ExecutionVenue(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"Unsupported venue: {value}") from exc


def _order_dump(order: OrderRequest) -> dict[str, Any]:
    data = order.model_dump()
    data["venue"] = order.venue.value
    data["side"] = order.side.value
    data["order_type"] = order.order_type.value
    data["time_in_force"] = order.time_in_force.value
    return data


def main() -> None:
    parser = argparse.ArgumentParser(description="Sandbox orchestration for the MVP trading flow")
    parser.add_argument("symbol", help="Trading symbol to use (e.g. BTCUSDT)")
    parser.add_argument("quantity", type=float, help="Order quantity to route")
    parser.add_argument(
        "--broker",
        default="binance",
        help="Broker identifier compatible with the order-router service",
    )
    parser.add_argument(
        "--venue",
        type=_parse_venue,
        default=ExecutionVenue.BINANCE_SPOT,
        help="Execution venue key (default: binance.spot)",
    )
    parser.add_argument(
        "--side",
        type=_parse_side,
        default=OrderSide.BUY,
        help="Order side: buy or sell",
    )
    parser.add_argument(
        "--type",
        dest="order_type",
        type=_parse_order_type,
        default=OrderType.LIMIT,
        help="Order type: limit or market",
    )
    parser.add_argument("--price", type=float, default=None, help="Limit price (ignored for market orders)")

    args = parser.parse_args()
    limit = get_pair_limit(args.venue, args.symbol)
    if limit is None:
        raise SystemExit(f"Symbol {args.symbol} is not configured for venue {args.venue.value}.")
    if args.quantity > limit.max_order_size:
        raise SystemExit(
            f"Requested quantity {args.quantity} exceeds sandbox limit {limit.max_order_size} for {args.symbol}."
        )

    order = OrderRequest(
        broker=args.broker,
        venue=args.venue,
        symbol=args.symbol,
        side=args.side,
        order_type=args.order_type,
        quantity=args.quantity,
        price=args.price,
    )
    plan = build_plan(order)
    payload = {
        "order": _order_dump(order),
        "quote": plan.quote.model_dump(),
        "orderbook": plan.orderbook.model_dump(),
        "plan": plan.model_dump(),
        "limits": asdict(limit),
    }
    print(json.dumps(payload, indent=2, sort_keys=True, default=str))


if __name__ == "__main__":
    main()
