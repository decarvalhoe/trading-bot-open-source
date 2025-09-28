from __future__ import annotations

from fastapi import Depends, FastAPI, HTTPException

from libs.observability.logging import RequestContextMiddleware, configure_logging
from libs.observability.metrics import setup_metrics
from sqlalchemy.orm import Session

from schemas.report import ReportResponse

from .calculations import ReportCalculator, load_report_from_snapshots
from .database import get_engine, get_session
from .tables import Base

configure_logging("reports")

app = FastAPI(title="Reports Service", version="0.1.0")
app.add_middleware(RequestContextMiddleware, service_name="reports")
setup_metrics(app, service_name="reports")


@app.on_event("startup")
def create_tables() -> None:
    engine = get_engine()
    Base.metadata.create_all(bind=engine)


@app.get("/health", tags=["system"])
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/reports/{symbol}", response_model=ReportResponse, tags=["reports"])
async def get_report(symbol: str, session: Session = Depends(get_session)) -> ReportResponse:
    cached = load_report_from_snapshots(session, symbol)
    if cached:
        return cached

    calculator = ReportCalculator(session)
    report = calculator.build_report(symbol)
    if not report.daily and not report.intraday:
        raise HTTPException(status_code=404, detail=f"No reports found for symbol '{symbol}'")
    return report


__all__ = ["app"]
