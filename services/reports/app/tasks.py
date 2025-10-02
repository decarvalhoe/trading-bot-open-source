from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Iterable

try:
    from celery import Celery
except ModuleNotFoundError:  # pragma: no cover - fallback when Celery is unavailable
    class _SyncTask:
        def __init__(self, func):
            self._func = func

        def delay(self, *args, **kwargs):
            return self._func(*args, **kwargs)

        def apply_async(self, args=None, kwargs=None):
            args = args or ()
            kwargs = kwargs or {}
            return self._func(*args, **kwargs)

        def __call__(self, *args, **kwargs):
            return self._func(*args, **kwargs)

    class Celery:
        def __init__(self, name: str) -> None:
            self.name = name
            self.conf = type(
                "Config",
                (),
                {"broker_url": None, "result_backend": None, "beat_schedule": {}, "timezone": "UTC"},
            )()

        def task(self, name: str | None = None, **_: object):
            def decorator(func):
                return _SyncTask(func)

            return decorator

from sqlalchemy import select

from .calculations import ReportCalculator
from .config import get_settings
from .database import session_scope
from .tables import ReportDaily, ReportIntraday, ReportJob, ReportJobStatus

settings = get_settings()

celery_app = Celery("reports")
celery_app.conf.broker_url = settings.celery_broker_url
celery_app.conf.result_backend = settings.celery_backend_url
celery_app.conf.beat_schedule = {
    "refresh-reports": {
        "task": "services.reports.app.tasks.refresh_reports",
        "schedule": settings.refresh_interval_seconds,
    }
}
celery_app.conf.timezone = "UTC"


def _load_render_dependencies():  # pragma: no cover - imported lazily in production
    from .main import (
        RenderReportRequest,
        _build_render_payload,
        _render_pdf,
        _render_template,
        _sanitize_filename,
    )

    return RenderReportRequest, _build_render_payload, _render_template, _render_pdf, _sanitize_filename


def _symbols(session) -> Iterable[str]:
    daily_symbols = set(session.scalars(select(ReportDaily.symbol).distinct()))
    intraday_symbols = set(session.scalars(select(ReportIntraday.symbol).distinct()))
    return sorted(daily_symbols | intraday_symbols)


@celery_app.task(name="services.reports.app.tasks.refresh_reports")
def refresh_reports() -> dict[str, datetime]:
    refreshed: dict[str, datetime] = {}
    with session_scope() as session:
        for symbol in _symbols(session):
            calculator = ReportCalculator(session)
            report = calculator.persist_snapshot(symbol)
            timestamp = max(
                filter(
                    None,
                    [
                        report.daily.updated_at if report.daily else None,
                        report.intraday.updated_at if report.intraday else None,
                    ],
                ),
                default=datetime.utcnow(),
            )
            refreshed[symbol] = timestamp
    return refreshed


@celery_app.task(name="services.reports.app.tasks.generate_report_job")
def generate_report_job(report_id: str, payload: dict[str, object]) -> str | None:
    (
        RenderReportRequest,
        _build_render_payload,
        _render_template,
        _render_pdf,
        _sanitize_filename,
    ) = _load_render_dependencies()

    options = dict(payload.get("options") or {})
    symbol = payload.get("symbol")
    if not isinstance(symbol, str) or not symbol:
        raise ValueError("symbol is required to render a report")

    storage_dir = Path(settings.reports_storage_path)
    storage_dir.mkdir(parents=True, exist_ok=True)

    failure: Exception | None = None
    result_path: str | None = None

    with session_scope() as session:
        job = session.get(ReportJob, report_id)
        if job is None:
            return None

        job.status = ReportJobStatus.RUNNING
        session.flush()

        try:
            request_payload = dict(options)
            request_payload.pop("mode", None)
            render_request = RenderReportRequest.model_validate(request_payload)
            template_name, context = _build_render_payload(render_request, session, symbol)
            html = _render_template(template_name, **context)
            pdf_bytes = _render_pdf(html)

            generated_at = context["generated_at"]
            filename = (
                f"{_sanitize_filename(symbol)}-"
                f"{_sanitize_filename(render_request.report_type)}-"
                f"{generated_at.strftime('%Y%m%d%H%M%S')}.pdf"
            )
            output_path = storage_dir / filename
            output_path.write_bytes(pdf_bytes)

            job.parameters = options or None
            job.file_path = str(output_path.resolve())
            job.status = ReportJobStatus.SUCCESS
            result_path = job.file_path
        except Exception as exc:
            job.status = ReportJobStatus.FAILURE
            job.file_path = None
        codex/confirm-ticket-resolution-and-create-task-list
            session.flush()
       
        main
            failure = exc

    if failure is not None:
        raise failure

    return result_path


__all__ = ["celery_app", "refresh_reports", "generate_report_job"]
