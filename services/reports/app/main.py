from __future__ import annotations

from datetime import datetime, timezone
import importlib
import re
from pathlib import Path
from typing import Literal

from fastapi import Body, Depends, FastAPI, HTTPException, Query
from fastapi.responses import Response

from libs.observability.logging import RequestContextMiddleware, configure_logging
from libs.observability.metrics import setup_metrics
from sqlalchemy.orm import Session

from jinja2 import Environment, FileSystemLoader, select_autoescape
from pydantic import BaseModel, Field, model_validator

from schemas.report import DailyRiskReport, PortfolioPerformance, ReportResponse

from .calculations import DailyRiskCalculator, ReportCalculator, load_report_from_snapshots
from .config import Settings, get_settings
from .database import get_engine, get_session
from .tables import Base

configure_logging("reports")

app = FastAPI(title="Reports Service", version="0.1.0")
app.add_middleware(RequestContextMiddleware, service_name="reports")
setup_metrics(app, service_name="reports")

_TEMPLATES_DIR = Path(__file__).parent / "templates"
_template_env = Environment(
    loader=FileSystemLoader(_TEMPLATES_DIR),
    autoescape=select_autoescape(["html", "xml"]),
)


class RenderReportRequest(BaseModel):
    report_type: Literal["symbol", "daily", "performance"] = "symbol"
    timeframe: Literal["daily", "intraday", "both"] = "both"
    account: str | None = None
    limit: int | None = Field(default=None, ge=1, le=365)

    @model_validator(mode="after")
    def validate_options(self) -> "RenderReportRequest":  # noqa: D401
        """Ensure parameters are compatible with the selected report type."""

        if self.report_type != "symbol" and self.timeframe != "both":
            raise ValueError("timeframe option is only supported for symbol reports")
        if self.report_type != "daily" and self.limit is not None:
            raise ValueError("limit option is only supported for daily risk reports")
        return self


def _sanitize_filename(value: str) -> str:
    sanitized = re.sub(r"[^A-Za-z0-9_.-]", "-", value)
    sanitized = sanitized.strip("-.")
    return sanitized or "report"


def _render_template(name: str, **context: object) -> str:
    template = _template_env.get_template(name)
    return template.render(**context)


def _render_pdf(html: str) -> bytes:
    weasyprint = importlib.import_module("weasyprint")
    html_document = weasyprint.HTML(string=html)
    return html_document.write_pdf()


def _load_symbol_report(
    session: Session,
    symbol: str,
    timeframe: Literal["daily", "intraday", "both"],
) -> ReportResponse:
    report = load_report_from_snapshots(session, symbol)
    if report is None:
        calculator = ReportCalculator(session)
        report = calculator.build_report(symbol)

    if timeframe == "daily":
        report = ReportResponse(symbol=report.symbol, daily=report.daily, intraday=None)
    elif timeframe == "intraday":
        report = ReportResponse(symbol=report.symbol, daily=None, intraday=report.intraday)

    if not report.daily and not report.intraday:
        raise HTTPException(status_code=404, detail=f"No reports found for symbol '{symbol}'")

    return report


def _build_render_payload(
    request: RenderReportRequest,
    session: Session,
    symbol: str,
) -> tuple[str, dict[str, object]]:
    generated_at = datetime.now(timezone.utc)
    if request.report_type == "symbol":
        report = _load_symbol_report(session, symbol, request.timeframe)
        context = {
            "title": f"{report.symbol} strategy report",
            "report": report,
            "generated_at": generated_at,
        }
        return "symbol_report.html", context

    calculator = DailyRiskCalculator(session)
    if request.report_type == "daily":
        limit = request.limit or 30
        reports = calculator.generate(account=request.account, limit=limit)
        if not reports:
            raise HTTPException(status_code=404, detail="No daily risk data available")
        context = {
            "title": "Daily risk report",
            "reports": reports,
            "account": request.account,
            "limit": limit,
            "generated_at": generated_at,
        }
        return "daily_risk_report.html", context

    performance = calculator.performance(account=request.account)
    if not performance:
        raise HTTPException(status_code=404, detail="No portfolio performance data available")
    context = {
        "title": "Portfolio performance",
        "performance": performance,
        "account": request.account,
        "generated_at": generated_at,
    }
    return "portfolio_performance.html", context


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


@app.get(
    "/reports/performance",
    response_model=list[PortfolioPerformance],
    tags=["reports"],
)
async def portfolio_performance(
    account: str | None = Query(default=None, description="Filter by account identifier"),
    session: Session = Depends(get_session),
) -> list[PortfolioPerformance]:
    calculator = DailyRiskCalculator(session)
    return calculator.performance(account=account)


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


@app.post("/reports/{symbol}/render", tags=["reports"])
async def render_report(
    symbol: str,
    request: RenderReportRequest = Body(default_factory=RenderReportRequest),
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> Response:
    template_name, context = _build_render_payload(request, session, symbol)
    html = _render_template(template_name, **context)
    pdf_bytes = _render_pdf(html)

    generated_at = context["generated_at"]
    storage_dir = Path(settings.reports_storage_path)
    storage_dir.mkdir(parents=True, exist_ok=True)
    filename = (
        f"{_sanitize_filename(symbol)}-"
        f"{_sanitize_filename(request.report_type)}-"
        f"{generated_at.strftime('%Y%m%d%H%M%S')}.pdf"
    )
    output_path = storage_dir / filename
    output_path.write_bytes(pdf_bytes)

    headers = {
        "Content-Disposition": f'attachment; filename="{filename}"',
        "X-Report-Path": str(output_path.resolve()),
    }
    return Response(content=pdf_bytes, media_type="application/pdf", headers=headers)


__all__ = ["app"]
