"""Environment configuration for the Codex worker."""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Settings loaded from environment variables."""

    github_token: str = Field("", description="GitHub token used to call the REST API", repr=False)
    sandbox_image: str = Field(
        "ghcr.io/trading-bot/codex-sandbox:latest",
        description="Container image used to run plan and test commands",
    )
    checkout_root: str = Field(
        "/tmp/codex",
        description="Directory where repositories are cloned before running commands",
    )
    feature_flag_environment: str = Field(
        "codex",
        description="OpenFeature client name used for entitlement checks",
    )

    class Config:
        env_prefix = "CODEX_WORKER_"
        case_sensitive = False


@lru_cache()
def get_settings() -> Settings:
    return Settings()
