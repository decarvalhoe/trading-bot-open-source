"""Client and FastAPI helpers to work with entitlements."""

from .client import EntitlementsClient, EntitlementsError, QuotaExceeded
from .fastapi import install_entitlements_middleware

__all__ = [
    "EntitlementsClient",
    "EntitlementsError",
    "QuotaExceeded",
    "install_entitlements_middleware",
]
