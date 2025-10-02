import re
from datetime import datetime, timezone

import httpx
import pytest
from jose import jwt
from playwright.async_api import Page, expect

pytestmark = pytest.mark.asyncio

TEST_JWT_SECRET = "test-onboarding-secret"


def _service_token() -> str:
    now = int(datetime.now(timezone.utc).timestamp())
    return jwt.encode({"sub": "auth-service", "iat": now}, TEST_JWT_SECRET, algorithm="HS256")


async def _register_user(user_service_base_url: str) -> int:
    email = f"onboarding-user-{int(datetime.now(timezone.utc).timestamp()*1000)}@example.com"
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{user_service_base_url}/users/register",
            headers={"Authorization": f"Bearer {_service_token()}"},
            json={
                "email": email,
                "first_name": "Demo",
                "last_name": "Trader",
                "phone": None,
            },
        )
    response.raise_for_status()
    payload = response.json()
    return payload["id"]


async def test_onboarding_walkthrough(
    page: Page,
    dashboard_base_url: str,
    user_service_base_url: str,
):
    user_id = await _register_user(user_service_base_url)

    await page.goto(f"{dashboard_base_url}/dashboard?user_id={user_id}", wait_until="networkidle")

    summary = page.locator("#onboarding-root").get_by_role("status").nth(0)
    await expect(summary).to_have_text(re.compile(r"0 / 3"))

    steps_list = page.get_by_role("list", name="Parcours d'onboarding")

    first_step = steps_list.get_by_role("listitem").filter(has_text="Connexion broker").nth(0)
    await expect(first_step).to_be_visible()
    await first_step.get_by_role("button", name=re.compile("Connexion broker", re.I)).click()
    await expect(summary).to_have_text(re.compile(r"1 / 3"))
    await expect(first_step.get_by_text("Terminée")).to_be_visible()

    second_step = steps_list.get_by_role("listitem").filter(has_text="Créer une stratégie").nth(0)
    await second_step.get_by_role("button", name=re.compile("Créer une stratégie", re.I)).click()
    await expect(summary).to_have_text(re.compile(r"2 / 3"))
    await expect(second_step.get_by_text("Terminée")).to_be_visible()

    third_step = steps_list.get_by_role("listitem").filter(has_text="Premier backtest").nth(0)
    await third_step.get_by_role("button", name=re.compile("Premier backtest", re.I)).click()
    await expect(summary).to_have_text(re.compile(r"3 / 3"))
    await expect(summary).to_have_text(re.compile("Parcours terminé", re.I))
    await expect(third_step.get_by_text("Terminée")).to_be_visible()

    restart_button = page.get_by_role("button", name="Relancer le tutoriel")
    await expect(restart_button).to_be_enabled()
    await restart_button.click()
    await expect(summary).to_have_text(re.compile(r"0 / 3"))
    await expect(first_step.get_by_text("Étape en cours")).to_be_visible()
