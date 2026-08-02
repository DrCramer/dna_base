from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import current_user, db_session, edit_user
from app.models import Employee, EmployeeStageRole, User
from app.schemas import EmployeeCreate, EmployeeOut, EmployeeUpdate
from app.services.audit import write_audit


router = APIRouter(prefix="/employees", tags=["employees"])
ALLOWED_EMPLOYEE_ROLES = {"эксперт", "лаборант"}


def _employee_snapshot(employee: Employee) -> dict[str, Any]:
    return {
        "id": employee.id,
        "full_name": employee.full_name,
        "short_name": employee.short_name,
        "initials": employee.initials,
        "role": employee.role,
        "is_verified": employee.is_verified,
        "is_active": employee.is_active,
        "stage_roles": [
            {"stage_type": item.stage_type, "role": item.role, "is_active": item.is_active}
            for item in employee.stage_roles
        ],
    }


def _clean_role(value: str | None) -> str | None:
    role = value.strip().lower() if isinstance(value, str) and value.strip() else None
    if role and role not in ALLOWED_EMPLOYEE_ROLES:
        raise HTTPException(status_code=400, detail="Роль сотрудника должна быть: эксперт или лаборант")
    return role


async def _replace_stage_roles(session: AsyncSession, employee: Employee, stages: list[str] | None) -> None:
    if stages is None:
        return
    result = await session.execute(
        select(EmployeeStageRole).where(EmployeeStageRole.employee_id == employee.id)
    )
    existing = {item.stage_type: item for item in result.scalars().all()}
    requested: set[str] = set()
    for stage in stages:
        stage_type = stage.strip() if isinstance(stage, str) else ""
        if not stage_type or stage_type in requested:
            continue
        requested.add(stage_type)
        item = existing.get(stage_type)
        if item:
            item.is_active = True
            item.role = employee.role
        else:
            session.add(
                EmployeeStageRole(
                    employee_id=employee.id,
                    stage_type=stage_type,
                    role=employee.role,
                    is_active=True,
                )
            )
    for stage_type, item in existing.items():
        if stage_type not in requested:
            item.is_active = False
            item.role = employee.role


async def _get_employee(session: AsyncSession, employee_id: int) -> Employee:
    stmt = (
        select(Employee)
        .options(selectinload(Employee.stage_roles))
        .where(Employee.id == employee_id)
        .execution_options(populate_existing=True)
    )
    result = await session.execute(stmt)
    return result.scalar_one()


async def _find_employee_by_full_name(session: AsyncSession, full_name: str) -> Employee | None:
    result = await session.execute(
        select(Employee).options(selectinload(Employee.stage_roles)).where(Employee.full_name == full_name)
    )
    return result.scalar_one_or_none()


async def _ensure_unique_full_name(session: AsyncSession, full_name: str, employee_id: int | None = None) -> None:
    stmt = select(Employee.id).where(Employee.full_name == full_name)
    if employee_id is not None:
        stmt = stmt.where(Employee.id != employee_id)
    result = await session.execute(stmt.limit(1))
    if result.scalar_one_or_none() is not None:
        raise HTTPException(status_code=400, detail="Сотрудник с таким ФИО уже существует")


@router.get("", response_model=list[EmployeeOut])
async def list_employees(
    q: str | None = None,
    verified: bool | None = None,
    stage_type: str | None = None,
    role: str | None = None,
    include_inactive: bool = False,
    limit: int = Query(default=500, ge=1, le=2000),
    session: AsyncSession = Depends(db_session),
    _user: User = Depends(current_user),
):
    stmt = select(Employee).options(selectinload(Employee.stage_roles))
    if q:
        needle = f"%{q.strip()}%"
        stmt = stmt.where(
            or_(
                Employee.full_name.ilike(needle),
                Employee.short_name.ilike(needle),
                Employee.initials.ilike(needle),
                Employee.role.ilike(needle),
            )
        )
    if verified is not None:
        stmt = stmt.where(Employee.is_verified == verified)
    if not include_inactive:
        stmt = stmt.where(Employee.is_active.is_(True))
    if role:
        stmt = stmt.where(Employee.role == _clean_role(role))
    if stage_type:
        stage_match = select(EmployeeStageRole.employee_id).where(
            EmployeeStageRole.stage_type == stage_type,
            EmployeeStageRole.is_active.is_(True),
        )
        stmt = stmt.where(Employee.id.in_(stage_match))
    result = await session.execute(stmt.order_by(Employee.role, Employee.full_name).limit(limit))
    return list(result.scalars().all())


@router.post("", response_model=EmployeeOut)
async def create_employee(
    payload: EmployeeCreate,
    session: AsyncSession = Depends(db_session),
    user: User = Depends(edit_user),
):
    full_name = payload.full_name.strip()
    if not full_name:
        raise HTTPException(status_code=400, detail="ФИО сотрудника обязательно")
    existing = await _find_employee_by_full_name(session, full_name)
    if existing:
        if existing.is_active:
            raise HTTPException(status_code=400, detail="Сотрудник с таким ФИО уже существует")
        before = _employee_snapshot(existing)
        existing.short_name = payload.short_name
        existing.initials = payload.initials
        existing.role = _clean_role(payload.role)
        existing.is_verified = payload.is_verified
        existing.is_active = True
        await _replace_stage_roles(session, existing, payload.stage_roles)
        await session.flush()
        restored = await _get_employee(session, existing.id)
        await write_audit(
            session,
            user,
            "employee",
            restored.id,
            "restore",
            before,
            _employee_snapshot(restored),
        )
        await session.commit()
        return await _get_employee(session, restored.id)
    employee = Employee(
        full_name=full_name,
        short_name=payload.short_name,
        initials=payload.initials,
        role=_clean_role(payload.role),
        is_verified=payload.is_verified,
        is_active=True,
    )
    session.add(employee)
    await session.flush()
    await _replace_stage_roles(session, employee, payload.stage_roles)
    await session.flush()
    employee = await _get_employee(session, employee.id)
    await write_audit(session, user, "employee", employee.id, "create", None, _employee_snapshot(employee))
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(status_code=400, detail="Сотрудник с таким ФИО уже существует") from exc
    return await _get_employee(session, employee.id)


@router.patch("/{employee_id}", response_model=EmployeeOut)
async def update_employee(
    employee_id: int,
    payload: EmployeeUpdate,
    session: AsyncSession = Depends(db_session),
    user: User = Depends(edit_user),
):
    result = await session.execute(
        select(Employee).options(selectinload(Employee.stage_roles)).where(Employee.id == employee_id)
    )
    employee = result.scalar_one_or_none()
    if not employee:
        raise HTTPException(status_code=404, detail="Сотрудник не найден")
    before = _employee_snapshot(employee)
    data = payload.model_dump(exclude_unset=True)
    if "full_name" in data and data["full_name"] is not None:
        data["full_name"] = data["full_name"].strip()
        if not data["full_name"]:
            raise HTTPException(status_code=400, detail="ФИО сотрудника обязательно")
        await _ensure_unique_full_name(session, data["full_name"], employee.id)
    if "role" in data:
        data["role"] = _clean_role(data["role"])
        employee.role = data["role"]
    for key, value in data.items():
        if key == "stage_roles":
            await _replace_stage_roles(session, employee, value)
            continue
        if key == "role":
            continue
        setattr(employee, key, value)
    for item in employee.stage_roles:
        item.role = employee.role
    await write_audit(session, user, "employee", employee.id, "update", before, _employee_snapshot(employee))
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(status_code=400, detail="Сотрудник с таким ФИО уже существует") from exc
    return await _get_employee(session, employee.id)
