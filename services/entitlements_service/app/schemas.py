from __future__ import annotations

from datetime import datetime
from typing import Dict, Optional

from pydantic import BaseModel


class ResolveResponse(BaseModel):
    customer_id: str
    capabilities: Dict[str, bool]
    quotas: Dict[str, Optional[int]]
    cached_at: Optional[datetime] = None
