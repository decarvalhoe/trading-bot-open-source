from __future__ import annotations

from datetime import datetime, timezone
import importlib
import re
from pathlib import Path
from typing import Literal

from fastapi import Body, Depends, FastAPI, HTTPException, Query, status
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
from .tables import Base, ReportJob, ReportJobStatus

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
    mode: Literal["sync", "async"] = "sync"

    @model_validator(mode="after")
    def validate_options(self) -> "RenderReportRequest":  # noqa: D401
        """Ensure parameters are compatible with the selected report type."""

        if self.report_type != "symbol" and self.timeframe != "both":
            raise ValueError("timeframe option is only supported for symbol reports")
        if self.report_type != "daily" and self.limit is not None:
            raise ValueError("limit option is only supported for daily risk reports")
        return self


class GenerateReportRequest(RenderReportRequest):
    symbol: str = Field(..., min_length=1)

    @model_validator(mode="after")
    def validate_async_mode(self) -> "GenerateReportRequest":  # noqa: D401
        """Ensure async jobs explicitly request asynchronous execution."""

        if self.mode != "async":
            raise ValueError("mode must be set to 'async' when generating asynchronous jobs")
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


class RiskSummary(BaseModel):
    """Aggregate risk metrics derived from DailyRiskCalculator."""

    total_pnl: float = 0.0
    max_drawdown: float = Field(0.0, ge=0.0)
    incident_count: int = Field(0, ge=0)
    recent: list[DailyRiskReport] = Field(default_factory=list)


class SymbolSummary(BaseModel):
    """Combined strategy and risk summary for a trading symbol."""

    symbol: str
    report: ReportResponse | None = None
    risk: RiskSummary


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


@app.get(
    "/symbols/{symbol}/summary",
    response_model=SymbolSummary,
    tags=["reports"],
)
async def symbol_summary(
    symbol: str,
    limit: int = Query(default=30, ge=1, le=365, description="Maximum number of daily risk rows"),
    session: Session = Depends(get_session),
) -> SymbolSummary:
    report = load_report_from_snapshots(session, symbol)
    if report is None:
        calculator = ReportCalculator(session)
        report = calculator.build_report(symbol)
    has_report = bool(report.daily or report.intraday)

    risk_calculator = DailyRiskCalculator(session)
    recent = risk_calculator.generate_for_symbol(symbol, limit=limit)
    total_pnl = sum(item.pnl for item in recent)
    max_drawdown = max((item.max_drawdown for item in recent), default=0.0)
    incident_count = sum(len(item.incidents) for item in recent)
    risk = RiskSummary(
        total_pnl=total_pnl,
        max_drawdown=max_drawdown,
        incident_count=incident_count,
        recent=recent,
    )

    if not has_report and not recent:
        raise HTTPException(status_code=404, detail=f"No analytics available for symbol '{symbol}'")

    payload_report = report if has_report else None
    return SymbolSummary(symbol=symbol, report=payload_report, risk=risk)


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
    if request.mode == "async":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Asynchronous rendering must be initiated via /reports/generate",
        )

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


@app.post("/reports/generate", status_code=status.HTTP_202_ACCEPTED, tags=["reports"])
async def create_report_job(
    request: GenerateReportRequest = Body(...),
    session: Session = Depends(get_session),
) -> dict[str, str]:
    job = ReportJob(
        symbol=request.symbol,
        parameters=request.model_dump(exclude={"symbol"}),
        status=ReportJobStatus.PENDING,
    )
    session.add(job)
    session.commit()
    session.refresh(job)

    payload = {
        "symbol": request.symbol,
        "options": request.model_dump(exclude={"symbol"}),
    }
    from .tasks import generate_report_job

    generate_report_job.delay(job.id, payload)
    return {"job_id": job.id}


@app.get("/reports/jobs/{job_id}", tags=["reports"])
async def get_report_job(job_id: str, session: Session = Depends(get_session)) -> dict[str, object]:
    job = session.get(ReportJob, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Report job not found")

    payload: dict[str, object] = {
        "id": job.id,
        "status": job.status.value,
        "parameters": job.parameters,
    }
    if job.file_path:
        payload["resource"] = job.file_path
    if job.symbol:
        payload["symbol"] = job.symbol
    return payload


__all__ = ["app"]
