from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import current_user, db_session
from app.models import User
from app.services.reports_service import (
    CONTROL_LABELS,
    LAB_STAGES,
    REPORT_STAGE_LABELS,
    ReportFilters,
    build_report_workbook,
    get_party_control_report,
    get_performer_statistics,
    get_period_statistics,
    get_reports_overview,
    get_work_progress_report,
)


router = APIRouter(prefix="/reports", tags=["reports"])


def _parse_party_ids(value: str | None) -> list[int] | None:
    if not value:
        return None
    ids: list[int] = []
    for chunk in value.replace(";", ",").split(","):
        chunk = chunk.strip()
        if chunk.isdigit():
            ids.append(int(chunk))
    return ids or None


def _filters(
    case_year: int | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    party_ids: str | None = None,
    stage_type: str | None = None,
    employee_id: int | None = None,
    object_type: str | None = None,
    box_no: str | None = None,
    include_archived: bool = False,
    include_empty_parties: bool = True,
    only_problematic: bool = False,
    page: int = Query(1, ge=1),
    page_size: int = Query(200, ge=1, le=1000),
    sort_by: str | None = None,
    sort_dir: str = "desc",
) -> ReportFilters:
    return ReportFilters(
        case_year=case_year,
        date_from=date_from,
        date_to=date_to,
        party_ids=_parse_party_ids(party_ids),
        stage_type=stage_type,
        employee_id=employee_id,
        object_type=object_type,
        box_no=box_no,
        include_archived=include_archived,
        include_empty_parties=include_empty_parties,
        only_problematic=only_problematic,
        page=page,
        page_size=page_size,
        sort_by=sort_by,
        sort_dir=sort_dir,
    )


@router.get("/overview")
async def reports_overview(
    filters: ReportFilters = Depends(_filters),
    session: AsyncSession = Depends(db_session),
    _user: User = Depends(current_user),
):
    return await get_reports_overview(session, filters)


@router.get("/party-control")
async def reports_party_control(
    quick: str | None = None,
    filters: ReportFilters = Depends(_filters),
    session: AsyncSession = Depends(db_session),
    _user: User = Depends(current_user),
):
    return await get_party_control_report(session, filters, quick=quick)


@router.get("/work-progress")
async def reports_work_progress(
    quick: str | None = None,
    filters: ReportFilters = Depends(_filters),
    session: AsyncSession = Depends(db_session),
    _user: User = Depends(current_user),
):
    return await get_work_progress_report(session, filters, quick=quick)


@router.get("/statistics/weekly")
async def reports_weekly_statistics(
    filters: ReportFilters = Depends(_filters),
    session: AsyncSession = Depends(db_session),
    _user: User = Depends(current_user),
):
    return await get_period_statistics(session, filters, "weekly")


@router.get("/statistics/monthly")
async def reports_monthly_statistics(
    filters: ReportFilters = Depends(_filters),
    session: AsyncSession = Depends(db_session),
    _user: User = Depends(current_user),
):
    return await get_period_statistics(session, filters, "monthly")


@router.get("/statistics/yearly")
async def reports_yearly_statistics(
    filters: ReportFilters = Depends(_filters),
    session: AsyncSession = Depends(db_session),
    _user: User = Depends(current_user),
):
    return await get_period_statistics(session, filters, "yearly")


@router.get("/performers")
async def reports_performers(
    filters: ReportFilters = Depends(_filters),
    session: AsyncSession = Depends(db_session),
    _user: User = Depends(current_user),
):
    return await get_performer_statistics(session, filters)


@router.get("/export")
async def reports_export(
    report: str = "party-control",
    quick: str | None = None,
    filters: ReportFilters = Depends(_filters),
    session: AsyncSession = Depends(db_session),
    _user: User = Depends(current_user),
):
    filters.page = 1
    filters.page_size = 1000
    if report == "work-progress":
        payload = await get_work_progress_report(session, filters, quick=quick)
        columns = [
            ("case_year", "Год"),
            ("party_no", "Партия"),
            ("object_count", "Объектов"),
            *[(f"stage_{stage}", REPORT_STAGE_LABELS[stage]) for stage in LAB_STAGES],
            ("lagging_stage", "Отстающий этап"),
            ("readiness_percent", "Готовность, %"),
            ("latest_change", "Последнее действие"),
        ]
        rows = []
        for row in payload["items"]:
            flat = dict(row)
            for stage in LAB_STAGES:
                progress = row["stage_progress"][stage]
                flat[f"stage_{stage}"] = f'{progress["done"]} / {progress["total"]} · {progress["percent"]}%'
            rows.append(flat)
        filename = "report_work_progress.xlsx"
        content = build_report_workbook("Ход работы", columns, rows)
    elif report == "overview":
        payload = await get_reports_overview(session, filters)
        columns = [
            ("case_year", "Год"),
            ("party_no", "Партия"),
            ("object_count", "Объектов"),
            *[(f"stage_{stage}", REPORT_STAGE_LABELS[stage]) for stage in LAB_STAGES],
            ("control_problem_count", "Проблемы контроля"),
            ("readiness_percent", "Готовность, %"),
            ("status", "Статус"),
        ]
        rows = []
        for row in payload["items"]:
            flat = dict(row)
            for stage in LAB_STAGES:
                progress = row["stage_progress"][stage]
                flat[f"stage_{stage}"] = f'{progress["done"]} / {progress["total"]} · {progress["percent"]}%'
            rows.append(flat)
        filename = "report_overview.xlsx"
        content = build_report_workbook("Обзор", columns, rows)
    elif report.startswith("statistics"):
        period = "monthly"
        if report.endswith("weekly"):
            period = "weekly"
        elif report.endswith("yearly"):
            period = "yearly"
        payload = await get_period_statistics(session, filters, period)
        columns = [
            ("year", "Год"),
            ("week", "Неделя"),
            ("month", "Месяц"),
            ("new_parties", "Новых партий"),
            ("new_objects", "Новых объектов"),
            *[(f"stage_{stage}", REPORT_STAGE_LABELS[stage]) for stage in LAB_STAGES],
            ("repeat_stage_events", "Повторных этапов"),
            ("control_problems", "Проблем контроля"),
        ]
        rows = []
        for row in payload["items"]:
            flat = dict(row)
            for stage in LAB_STAGES:
                flat[f"stage_{stage}"] = row["stage_counts"].get(stage, 0)
            rows.append(flat)
        filename = "report_statistics.xlsx"
        content = build_report_workbook("Статистика", columns, rows)
    else:
        payload = await get_party_control_report(session, filters, quick=quick)
        columns = [
            ("case_year", "Год"),
            ("party_no", "Партия"),
            ("object_count", "Объектов"),
            *[(field, label) for field, label in CONTROL_LABELS.items()],
            ("problem_count", "Количество проблем"),
            ("control_status", "Статус контроля"),
            ("latest_change", "Последнее изменение"),
        ]
        filename = "report_party_control.xlsx"
        content = build_report_workbook("Контроль партий", columns, payload["items"])
    headers = {"Content-Disposition": f'attachment; filename="{filename}"'}
    return Response(
        content,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers=headers,
    )
