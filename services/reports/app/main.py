from __future__ import annotations

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.responses import Response

from libs.observability.logging import RequestContextMiddleware, configure_logging
from libs.observability.metrics import setup_metrics
from sqlalchemy.orm import Session

from schemas.report import DailyRiskReport, ReportResponse

from .calculations import DailyRiskCalculator, ReportCalculator, load_report_from_snapshots
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


@app.get("/reports/daily", response_model=list[DailyRiskReport], tags=["reports"])
async def daily_risk_report(
    account: str | None = Query(default=None, description="Filter by account identifier"),
    limit: int = Query(default=30, ge=1, le=365, description="Maximum number of rows to return"),
    export: str | None = Query(default=None, pattern="^(csv)$", description="Return the payload as CSV when set to 'csv'"),
    session: Session = Depends(get_session),
):
    calculator = DailyRiskCalculator(session)
    reports = calculator.generate(account=account, limit=limit)
    if export == "csv":
        payload = DailyRiskCalculator.export_csv(reports)
        return Response(
            content=payload,
            media_type="text/csv",
            headers={"Content-Disposition": "attachment; filename=daily_risk_report.csv"},
        )
    return reports


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
