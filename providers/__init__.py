"""External market data providers used across services."""

from .fmp import FinancialModelingPrepClient, FinancialModelingPrepError

__all__ = ["FinancialModelingPrepClient", "FinancialModelingPrepError"]
