from __future__ import annotations

import time

from fastapi.testclient import TestClient

from services.inplay.app.config import Settings
from services.inplay.app.main import SimulatedTickStream, create_app
from services.inplay.app.schemas import TickPayload


def test_tick_stream_updates_watchlist_and_websocket() -> None:
    stream = SimulatedTickStream()
    settings = Settings(watchlists={"momentum": ["AAPL", "MSFT"]})
    app = create_app(settings=settings, stream_factory=lambda: stream)

    payload = TickPayload(
        symbol="AAPL",
        strategy="ORB",
        entry=190.0,
        target=191.5,
        stop=189.0,
        probability=0.65,
        status="pending",
        session="london",
        watchlists=["momentum"],
    )

    with TestClient(app) as client:
        assert stream._ready.wait(timeout=1.0)
        stream.publish(payload)

        deadline = time.time() + 1.0
        data = None
        while time.time() < deadline:
            response = client.get("/inplay/watchlists/momentum")
            assert response.status_code == 200
            data = response.json()
            setups = data["symbols"][0]["setups"]
            if setups:
                break
            time.sleep(0.05)
        assert data is not None
        setups = data["symbols"][0]["setups"]
        assert setups[0]["strategy"] == "ORB"
        assert setups[0]["probability"] == payload.probability
        assert setups[0]["status"] == payload.status
        assert setups[0]["session"] == "london"

        with client.websocket_connect("/inplay/ws") as websocket:
            initial = websocket.receive_json()
            assert initial["payload"]["symbols"][0]["setups"][0]["strategy"] == "ORB"

            updated_payload = TickPayload(
                symbol="AAPL",
                strategy="ORB",
                entry=190.5,
                target=192.0,
                stop=189.5,
                probability=0.7,
                status="validated",
                session="london",
                watchlists=["momentum"],
            )
            stream.publish(updated_payload)

            message = websocket.receive_json()
            latest_setup = message["payload"]["symbols"][0]["setups"][0]
            assert latest_setup["target"] == updated_payload.target
            assert latest_setup["probability"] == updated_payload.probability
            assert latest_setup["status"] == updated_payload.status
            assert latest_setup["session"] == "london"


def test_watchlist_session_filtering() -> None:
    stream = SimulatedTickStream()
    settings = Settings(watchlists={"momentum": ["AAPL", "MSFT"]})
    app = create_app(settings=settings, stream_factory=lambda: stream)

    london_payload = TickPayload(
        symbol="AAPL",
        strategy="ORB",
        entry=190.0,
        target=191.5,
        stop=189.0,
        probability=0.65,
        status="pending",
        session="london",
        watchlists=["momentum"],
    )
    asia_payload = TickPayload(
        symbol="AAPL",
        strategy="Breakout",
        entry=189.5,
        target=192.5,
        stop=188.5,
        probability=0.55,
        status="pending",
        session="asia",
        watchlists=["momentum"],
    )

    with TestClient(app) as client:
        assert stream._ready.wait(timeout=1.0)
        stream.publish(london_payload)
        stream.publish(asia_payload)

        deadline = time.time() + 1.0
        while time.time() < deadline:
            response = client.get("/inplay/watchlists/momentum")
            assert response.status_code == 200
            data = response.json()
            setups = data["symbols"][0]["setups"]
            if len(setups) >= 2:
                break
            time.sleep(0.05)
        else:
            raise AssertionError("Setups not available in time")

        response = client.get("/inplay/watchlists/momentum", params={"session": "asia"})
        assert response.status_code == 200
        filtered = response.json()
        filtered_setups = filtered["symbols"][0]["setups"]
        assert filtered_setups
        assert all(setup["session"] == "asia" for setup in filtered_setups)
        assert all(setup["strategy"] == "Breakout" for setup in filtered_setups)

        response_default = client.get("/inplay/watchlists/momentum")
        assert response_default.status_code == 200
        combined_setups = response_default.json()["symbols"][0]["setups"]
        assert any(setup["session"] == "london" for setup in combined_setups)
        assert any(setup["session"] == "asia" for setup in combined_setups)
