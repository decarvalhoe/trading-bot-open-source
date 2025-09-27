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
        watchlists=["momentum"],
    )

    with TestClient(app) as client:
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
                watchlists=["momentum"],
            )
            stream.publish(updated_payload)

            message = websocket.receive_json()
            latest_setup = message["payload"]["symbols"][0]["setups"][0]
            assert latest_setup["target"] == updated_payload.target
            assert latest_setup["probability"] == updated_payload.probability
