from services.streaming_gateway.app.security import issue_overlay_token, verify_overlay_token


def test_issue_and_verify_overlay_token():
    token = issue_overlay_token("overlay123", "secret", ttl=5)
    payload = verify_overlay_token(token, "secret")
    assert payload["overlayId"] == "overlay123"
    assert payload["exp"] >= payload["iat"]
