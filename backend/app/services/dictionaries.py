from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import Employee, EmployeeStageRole, ReferenceItem


EMPLOYEE_STAGE_DEFAULTS = [
    "preparation",
    "milling",
    "extraction",
    "realtime",
    "pcr",
    "electrophoresis",
    "analysis",
]

LAB_ASSISTANTS = [
    "Давыдов В.Е.",
    "Джерелиевский Д.Б.",
    "Гуров М.В.",
    "Попова М.М.",
    "Нечитайлова Н.А.",
    "Сотников С.А.",
    "Субботин В.М.",
]

EXPERTS = [
    "Хлынцева Л.А.",
    "Непомнящая Л.В.",
    "Смоляницкая А.И.",
    "Смоляницкий А.Г.",
]

REFERENCE_SEED = {
    "extraction_method": [
        "Gordiz",
        "Мсорб-кость",
        "PrepFiler + BTA",
        "ImpulsSkel",
        "Power Quant",
    ],
    "quant_method": [
        "HP",
        "HP 0.5 V",
        "Real Quant",
        "TRIO",
        "TRIO 0.5V",
    ],
    "pcr_panel": [
        "Identifier_Plus",
        "GlobalFiler",
        "VeriFiler Plus",
        "FGI 34 V3.7",
        "PanGlobal Plus",
        "SBT",
        "VeriFiler Express",
        "GorDIS_Plus",
        "NGM_Detect",
        "PP_CS7",
        "PP_ESI_17_Fast",
        "PP_ESX_17_Fast",
        "PP_Fusion",
        "PP_Y23 (WEN ILS 500 Y23)",
        "PP_Y23 (CC5 ILS 500 Y23)",
        "mt_pcr",
        "PP_Fusion6C_0,5V",
        "PP_Fusion6C",
        "MiniFiler",
        "PP_Fusion6C Direct 0,5V",
        "HDplex",
        "Yfiler_Plus",
        "Y12",
        "Argus X-12",
        "ESS_plex_plus",
    ],
    "electrophoresis_kit": [
        "Identifier_Plus",
        "NGM_Detect",
        "MiniFiler",
        "GlobalFiler",
        "Yfiler_Plus",
        "ESS_plex_plus",
        "HDplex",
        "Argus X-12",
        "Y12",
        "PP_CS7",
        "PP_ESI_17_Fast",
        "PP_ESX_17_Fast",
        "PP_Fusion",
        "PP_Y23 (WEN ILS 500 Y23)",
        "PP_Y23 (CC5 ILS 500 Y23)",
        "mt_pcr",
        "PP_Fusion6C_0,5V",
        "PP_Fusion6C",
        "GOrDIS_Plus",
        "PP_Fusion6C Direct 0,5V",
        "PanGlobal Plus",
        "VeriFiler Plus",
        "SBT",
        "VERiFiler Express",
        "FGI 34 V3.7",
    ],
    "sequencer": [
        "GTZ G08",
        "GTZ G16",
        "GTZ G24",
        "Honor",
    ],
}


def canonical_employee_names() -> dict[str, str]:
    return {name: "лаборант" for name in LAB_ASSISTANTS} | {name: "эксперт" for name in EXPERTS}


async def _replace_employee_stages(employee: Employee) -> None:
    existing = {item.stage_type: item for item in employee.stage_roles}
    for stage in EMPLOYEE_STAGE_DEFAULTS:
        item = existing.get(stage)
        if item:
            item.role = employee.role
            item.is_active = True
        else:
            employee.stage_roles.append(EmployeeStageRole(stage_type=stage, role=employee.role, is_active=True))
    for stage, item in existing.items():
        if stage not in EMPLOYEE_STAGE_DEFAULTS:
            item.is_active = False


async def seed_lab_dictionaries(session: AsyncSession) -> dict[str, int]:
    stats = {
        "employees_active": 0,
        "employees_disabled": 0,
        "references_active": 0,
        "references_disabled": 0,
    }
    required_employees = canonical_employee_names()
    result = await session.execute(select(Employee).options(selectinload(Employee.stage_roles)))
    employees = list(result.scalars().all())
    by_name = {employee.full_name: employee for employee in employees}

    for name, role in required_employees.items():
        employee = by_name.get(name)
        if not employee:
            employee = Employee(
                full_name=name,
                short_name=name,
                initials=name,
                role=role,
                is_verified=True,
                is_active=True,
            )
            session.add(employee)
            await session.flush()
            by_name[name] = employee
        employee.short_name = name
        employee.initials = name
        employee.role = role
        employee.is_verified = True
        employee.is_active = True
        await _replace_employee_stages(employee)
        stats["employees_active"] += 1

    for employee in by_name.values():
        if employee.full_name in required_employees:
            continue
        if employee.is_active:
            stats["employees_disabled"] += 1
        employee.is_active = False

    for category, names in REFERENCE_SEED.items():
        result = await session.execute(select(ReferenceItem).where(ReferenceItem.category == category))
        items = list(result.scalars().all())
        by_item_name = {item.name: item for item in items}
        required_names = set(names)
        for name in names:
            item = by_item_name.get(name)
            if not item:
                item = ReferenceItem(
                    category=category,
                    name=name,
                    short_name=None,
                    comment="задано лабораторным справочником",
                    is_active=True,
                )
                session.add(item)
                await session.flush()
                by_item_name[name] = item
            item.is_active = True
            if not item.comment or item.comment == "импортировано из Excel":
                item.comment = "задано лабораторным справочником"
            stats["references_active"] += 1
        for item in by_item_name.values():
            if item.name in required_names:
                continue
            if item.is_active:
                stats["references_disabled"] += 1
            item.is_active = False

    await session.commit()
    return stats
