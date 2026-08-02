from datetime import date, datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from app.db.base import Base, TimestampMixin


json_type = JSON().with_variant(JSONB, "postgresql")


class UserRole(StrEnum):
    admin = "admin"
    user = "user"
    viewer = "viewer"


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[UserRole] = mapped_column(Enum(UserRole), default=UserRole.viewer)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Employee(Base):
    __tablename__ = "employees"

    id: Mapped[int] = mapped_column(primary_key=True)
    full_name: Mapped[str] = mapped_column(String(255), unique=True)
    short_name: Mapped[str | None] = mapped_column(String(80))
    initials: Mapped[str | None] = mapped_column(String(80), index=True)
    role: Mapped[str | None] = mapped_column(String(120), index=True)
    is_verified: Mapped[bool] = mapped_column(Boolean, default=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    stage_roles: Mapped[list["EmployeeStageRole"]] = relationship(
        back_populates="employee", cascade="all, delete-orphan"
    )


class EmployeeStageRole(Base):
    __tablename__ = "employee_stage_roles"

    id: Mapped[int] = mapped_column(primary_key=True)
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id", ondelete="CASCADE"), index=True)
    stage_type: Mapped[str] = mapped_column(String(80), index=True)
    role: Mapped[str | None] = mapped_column(String(120), index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)

    employee: Mapped[Employee] = relationship(back_populates="stage_roles")

    __table_args__ = (UniqueConstraint("employee_id", "stage_type", name="uq_employee_stage_roles_once"),)


class ReferenceItem(Base, TimestampMixin):
    __tablename__ = "reference_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    category: Mapped[str] = mapped_column(String(120), index=True)
    name: Mapped[str] = mapped_column(String(255), index=True)
    short_name: Mapped[str | None] = mapped_column(String(120))
    comment: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)

    __table_args__ = (UniqueConstraint("category", "name", name="uq_reference_items_category_name"),)


class Party(Base, TimestampMixin):
    __tablename__ = "parties"

    id: Mapped[int] = mapped_column(primary_key=True)
    party_no: Mapped[str] = mapped_column(String(80), index=True)
    case_year: Mapped[int | None] = mapped_column(Integer, index=True)
    title: Mapped[str | None] = mapped_column(String(255))
    comment: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(80), default="active", index=True)
    created_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    object_count: Mapped[int] = mapped_column(Integer, default=0)
    control_actual_decrees: Mapped[str | None] = mapped_column(Text)
    control_decree_without_object: Mapped[str | None] = mapped_column(Text)
    control_object_without_decree: Mapped[str | None] = mapped_column(Text)
    control_unidentified_rostov_no: Mapped[str | None] = mapped_column(Text)
    control_need_recall: Mapped[str | None] = mapped_column(Text)
    control_recalled: Mapped[str | None] = mapped_column(Text)
    raw_control_json: Mapped[dict[str, Any]] = mapped_column(json_type, default=dict)

    objects: Mapped[list["RegistryObject"]] = relationship(back_populates="party")
    work_sessions: Mapped[list["WorkSession"]] = relationship(back_populates="party")

    __table_args__ = (UniqueConstraint("case_year", "party_no", name="uq_parties_case_year_party_no"),)


class RegistryImportBatch(Base):
    __tablename__ = "registry_import_batches"

    id: Mapped[int] = mapped_column(primary_key=True)
    original_filename: Mapped[str] = mapped_column(String(255))
    party_no: Mapped[str | None] = mapped_column(String(80), index=True)
    file_sha256: Mapped[str] = mapped_column(String(64), index=True)
    stored_path: Mapped[str | None] = mapped_column(String(500))
    imported_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    imported_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    rows_total: Mapped[int] = mapped_column(Integer, default=0)
    rows_imported: Mapped[int] = mapped_column(Integer, default=0)
    rows_skipped: Mapped[int] = mapped_column(Integer, default=0)
    import_log_json: Mapped[dict[str, Any]] = mapped_column(json_type, default=dict)

    objects: Mapped[list["RegistryObject"]] = relationship(
        back_populates="source_import_batch", cascade="all, delete-orphan"
    )


class RegistryObject(Base, TimestampMixin):
    __tablename__ = "objects"

    id: Mapped[int] = mapped_column(primary_key=True)
    source_import_batch_id: Mapped[int | None] = mapped_column(
        ForeignKey("registry_import_batches.id", ondelete="SET NULL"), index=True
    )
    party_id: Mapped[int | None] = mapped_column(ForeignKey("parties.id", ondelete="SET NULL"), index=True)
    parent_object_id: Mapped[int | None] = mapped_column(ForeignKey("objects.id", ondelete="SET NULL"), index=True)
    repeat_suffix: Mapped[str | None] = mapped_column(String(32), index=True)
    source_sheet_name: Mapped[str | None] = mapped_column(String(120))
    source_row_number: Mapped[int | None] = mapped_column(Integer)
    party_no: Mapped[str | None] = mapped_column(String(80), index=True)
    case_year: Mapped[int | None] = mapped_column(Integer, index=True)
    registry_row_no: Mapped[str | None] = mapped_column(String(80))
    intake_date: Mapped[date | None] = mapped_column(Date)
    decision_date: Mapped[date | None] = mapped_column(Date)
    investigator: Mapped[str | None] = mapped_column(String(255), index=True)
    incoming_no: Mapped[str | None] = mapped_column(String(120))
    decree_no: Mapped[str | None] = mapped_column(String(120), index=True)
    decree_no_base: Mapped[str | None] = mapped_column(String(80), index=True)
    object_description: Mapped[str | None] = mapped_column(Text)
    external_military_no: Mapped[str | None] = mapped_column(String(255), index=True)
    extraction_note: Mapped[str | None] = mapped_column(String(255))
    box_no: Mapped[str | None] = mapped_column(String(80), index=True)
    packages_count: Mapped[int | None] = mapped_column(Integer)
    rcsme_reg_no: Mapped[str | None] = mapped_column(String(120), index=True)
    rcsme_reg_no_base: Mapped[str | None] = mapped_column(String(80), index=True)
    rcsme_reg_no_is_manual: Mapped[bool] = mapped_column(Boolean, default=False)
    object_type: Mapped[str | None] = mapped_column(String(255), index=True)
    extracted_before: Mapped[str | None] = mapped_column(String(255))
    not_extracted_before: Mapped[str | None] = mapped_column(String(255))
    registry_filled_by: Mapped[str | None] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(80), default="new", index=True)
    raw_registry_json: Mapped[dict[str, Any]] = mapped_column(json_type, default=dict)

    source_import_batch: Mapped[RegistryImportBatch | None] = relationship(back_populates="objects")
    party: Mapped[Party | None] = relationship(back_populates="objects")
    parent_object: Mapped["RegistryObject | None"] = relationship(
        "RegistryObject",
        remote_side=[id],
        back_populates="repeat_objects",
    )
    repeat_objects: Mapped[list["RegistryObject"]] = relationship(
        "RegistryObject",
        back_populates="parent_object",
    )
    stage_events: Mapped[list["StageEvent"]] = relationship(back_populates="object", cascade="all, delete-orphan")
    prep_events: Mapped[list["ObjectPrepEvent"]] = relationship(cascade="all, delete-orphan")
    dna_extractions: Mapped[list["DnaExtraction"]] = relationship(cascade="all, delete-orphan")
    pcr_events: Mapped[list["PcrEvent"]] = relationship(cascade="all, delete-orphan")
    electrophoresis_events: Mapped[list["ElectrophoresisEvent"]] = relationship(cascade="all, delete-orphan")
    electrophoresis_analysis_events: Mapped[list["ElectrophoresisAnalysisEvent"]] = relationship(
        cascade="all, delete-orphan"
    )
    rt_results: Mapped[list["RtResult"]] = relationship(back_populates="object")
    electrophoresis_result_files: Mapped[list["ElectrophoresisResultFile"]] = relationship(cascade="all, delete-orphan")

    __table_args__ = (
        UniqueConstraint("case_year", "rcsme_reg_no", name="uq_objects_case_year_rcsme_reg_no"),
        UniqueConstraint("decree_no", name="uq_objects_decree_no"),
        UniqueConstraint("case_year", "party_no", "rcsme_reg_no", name="uq_objects_case_year_party_rcsme"),
        Index("ix_objects_search_numbers", "rcsme_reg_no", "decree_no", "external_military_no"),
        Index("ix_objects_repeat_lookup", "party_id", "parent_object_id", "repeat_suffix"),
    )


class WorkSession(Base, TimestampMixin):
    __tablename__ = "work_sessions"

    id: Mapped[int] = mapped_column(primary_key=True)
    party_id: Mapped[int | None] = mapped_column(ForeignKey("parties.id", ondelete="SET NULL"), index=True)
    stage_type: Mapped[str] = mapped_column(String(80), index=True)
    title: Mapped[str | None] = mapped_column(String(255))
    work_date: Mapped[date | None] = mapped_column(Date, index=True)
    comment: Mapped[str | None] = mapped_column(Text)
    created_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)
    source: Mapped[str] = mapped_column(String(80), default="manual", index=True)
    status: Mapped[str] = mapped_column(String(80), default="draft", index=True)
    raw_json: Mapped[dict[str, Any]] = mapped_column(json_type, default=dict)

    party: Mapped[Party | None] = relationship(back_populates="work_sessions")
    objects: Mapped[list["WorkSessionObject"]] = relationship(
        back_populates="work_session", cascade="all, delete-orphan"
    )
    stage_events: Mapped[list["StageEvent"]] = relationship(back_populates="work_session")


class WorkSessionObject(Base):
    __tablename__ = "work_session_objects"

    id: Mapped[int] = mapped_column(primary_key=True)
    work_session_id: Mapped[int] = mapped_column(ForeignKey("work_sessions.id", ondelete="CASCADE"), index=True)
    object_id: Mapped[int] = mapped_column(ForeignKey("objects.id", ondelete="CASCADE"), index=True)
    object_order: Mapped[int | None] = mapped_column(Integer)
    per_object_comment: Mapped[str | None] = mapped_column(Text)
    is_excluded: Mapped[bool] = mapped_column(Boolean, default=False)

    work_session: Mapped[WorkSession] = relationship(back_populates="objects")
    object: Mapped[RegistryObject] = relationship()

    __table_args__ = (UniqueConstraint("work_session_id", "object_id", name="uq_work_session_objects_once"),)


class StageEvent(Base, TimestampMixin):
    __tablename__ = "stage_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    object_id: Mapped[int] = mapped_column(ForeignKey("objects.id", ondelete="CASCADE"), index=True)
    work_session_id: Mapped[int | None] = mapped_column(ForeignKey("work_sessions.id", ondelete="SET NULL"), index=True)
    stage_type: Mapped[str] = mapped_column(String(80), index=True)
    attempt_no: Mapped[int] = mapped_column(Integer, default=1, index=True)
    event_date: Mapped[date | None] = mapped_column(Date, index=True)
    source: Mapped[str] = mapped_column(String(80), default="manual", index=True)
    comment: Mapped[str | None] = mapped_column(Text)
    raw_json: Mapped[dict[str, Any]] = mapped_column(json_type, default=dict)
    created_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)
    is_cancelled: Mapped[bool] = mapped_column(Boolean, default=False, index=True)

    object: Mapped[RegistryObject] = relationship(back_populates="stage_events")
    work_session: Mapped[WorkSession | None] = relationship(back_populates="stage_events")
    performers: Mapped[list["StageEventPerformer"]] = relationship(
        back_populates="stage_event", cascade="all, delete-orphan"
    )
    sample_prep_detail: Mapped["SamplePrepDetail | None"] = relationship(
        back_populates="stage_event", cascade="all, delete-orphan", uselist=False
    )
    milling_detail: Mapped["MillingDetail | None"] = relationship(
        back_populates="stage_event", cascade="all, delete-orphan", uselist=False
    )
    dna_extraction_detail: Mapped["DnaExtractionDetail | None"] = relationship(
        back_populates="stage_event", cascade="all, delete-orphan", uselist=False
    )
    realtime_detail: Mapped["RealtimeDetail | None"] = relationship(
        back_populates="stage_event", cascade="all, delete-orphan", uselist=False
    )
    pcr_detail: Mapped["PcrDetail | None"] = relationship(
        back_populates="stage_event", cascade="all, delete-orphan", uselist=False
    )
    electrophoresis_detail: Mapped["ElectrophoresisDetail | None"] = relationship(
        back_populates="stage_event", cascade="all, delete-orphan", uselist=False
    )
    analysis_detail: Mapped["AnalysisDetail | None"] = relationship(
        back_populates="stage_event", cascade="all, delete-orphan", uselist=False
    )


class StageEventPerformer(Base):
    __tablename__ = "stage_event_performers"

    id: Mapped[int] = mapped_column(primary_key=True)
    stage_event_id: Mapped[int] = mapped_column(ForeignKey("stage_events.id", ondelete="CASCADE"), index=True)
    employee_id: Mapped[int | None] = mapped_column(ForeignKey("employees.id", ondelete="SET NULL"), index=True)
    role: Mapped[str] = mapped_column(String(120), index=True)
    order_index: Mapped[int] = mapped_column(Integer, default=0)
    raw_name: Mapped[str | None] = mapped_column(String(255), index=True)

    stage_event: Mapped[StageEvent] = relationship(back_populates="performers")
    employee: Mapped[Employee | None] = relationship()


class SamplePrepDetail(Base):
    __tablename__ = "sample_prep_details"

    id: Mapped[int] = mapped_column(primary_key=True)
    stage_event_id: Mapped[int] = mapped_column(
        ForeignKey("stage_events.id", ondelete="CASCADE"), unique=True, index=True
    )
    registry_filled_by: Mapped[str | None] = mapped_column(String(255))
    photo_performers: Mapped[list[Any]] = mapped_column(json_type, default=list)
    photo_assistants: Mapped[list[Any]] = mapped_column(json_type, default=list)
    washing_performers: Mapped[list[Any]] = mapped_column(json_type, default=list)
    washing_assistants: Mapped[list[Any]] = mapped_column(json_type, default=list)
    washing_date: Mapped[date | None] = mapped_column(Date, index=True)
    bone_tissue_performers: Mapped[list[Any]] = mapped_column(json_type, default=list)
    bone_tissue_date: Mapped[date | None] = mapped_column(Date, index=True)

    stage_event: Mapped[StageEvent] = relationship(back_populates="sample_prep_detail")


class MillingDetail(Base):
    __tablename__ = "milling_details"

    id: Mapped[int] = mapped_column(primary_key=True)
    stage_event_id: Mapped[int] = mapped_column(
        ForeignKey("stage_events.id", ondelete="CASCADE"), unique=True, index=True
    )
    milling_performers: Mapped[list[Any]] = mapped_column(json_type, default=list)
    cups: Mapped[str | None] = mapped_column(String(255))
    milling_date: Mapped[date | None] = mapped_column(Date, index=True)

    stage_event: Mapped[StageEvent] = relationship(back_populates="milling_detail")


class DnaExtractionDetail(Base):
    __tablename__ = "dna_extraction_details"

    id: Mapped[int] = mapped_column(primary_key=True)
    stage_event_id: Mapped[int] = mapped_column(
        ForeignKey("stage_events.id", ondelete="CASCADE"), unique=True, index=True
    )
    extraction_date: Mapped[date | None] = mapped_column(Date, index=True)
    extraction_method: Mapped[str | None] = mapped_column(String(255), index=True)

    stage_event: Mapped[StageEvent] = relationship(back_populates="dna_extraction_detail")


class RealtimeDetail(Base):
    __tablename__ = "realtime_details"

    id: Mapped[int] = mapped_column(primary_key=True)
    stage_event_id: Mapped[int] = mapped_column(
        ForeignKey("stage_events.id", ondelete="CASCADE"), unique=True, index=True
    )
    quant_method: Mapped[str | None] = mapped_column(String(255), index=True)
    quant_date: Mapped[date | None] = mapped_column(Date, index=True)
    quant_performer: Mapped[str | None] = mapped_column(String(255))
    pipetting_method: Mapped[str | None] = mapped_column(String(255))
    concentration: Mapped[float | None] = mapped_column(Float)
    ct_cq: Mapped[float | None] = mapped_column(Float)
    di: Mapped[float | None] = mapped_column(Float)
    ipc: Mapped[float | None] = mapped_column(Float)
    long_quantity: Mapped[float | None] = mapped_column(Float)
    small_quantity: Mapped[float | None] = mapped_column(Float)
    y_quantity: Mapped[float | None] = mapped_column(Float)
    comment: Mapped[str | None] = mapped_column(Text)

    stage_event: Mapped[StageEvent] = relationship(back_populates="realtime_detail")


class PcrDetail(Base):
    __tablename__ = "pcr_details"

    id: Mapped[int] = mapped_column(primary_key=True)
    stage_event_id: Mapped[int] = mapped_column(
        ForeignKey("stage_events.id", ondelete="CASCADE"), unique=True, index=True
    )
    pcr_date: Mapped[date | None] = mapped_column(Date, index=True)
    locus_panel: Mapped[str | None] = mapped_column(String(255), index=True)
    pipetting_method: Mapped[str | None] = mapped_column(String(255))
    normalization_performers: Mapped[list[Any]] = mapped_column(json_type, default=list)
    pcr_performers: Mapped[list[Any]] = mapped_column(json_type, default=list)

    stage_event: Mapped[StageEvent] = relationship(back_populates="pcr_detail")


class ElectrophoresisDetail(Base):
    __tablename__ = "electrophoresis_details"

    id: Mapped[int] = mapped_column(primary_key=True)
    stage_event_id: Mapped[int] = mapped_column(
        ForeignKey("stage_events.id", ondelete="CASCADE"), unique=True, index=True
    )
    electrophoresis_date: Mapped[date | None] = mapped_column(Date, index=True)
    sequencer: Mapped[str | None] = mapped_column(String(255), index=True)
    pipetting_method: Mapped[str | None] = mapped_column(String(255))
    performers: Mapped[list[Any]] = mapped_column(json_type, default=list)

    stage_event: Mapped[StageEvent] = relationship(back_populates="electrophoresis_detail")


class AnalysisDetail(Base):
    __tablename__ = "analysis_details"

    id: Mapped[int] = mapped_column(primary_key=True)
    stage_event_id: Mapped[int] = mapped_column(
        ForeignKey("stage_events.id", ondelete="CASCADE"), unique=True, index=True
    )
    genotype: Mapped[str | None] = mapped_column(String(255), index=True)
    analysis_date: Mapped[date | None] = mapped_column(Date, index=True)
    status: Mapped[str | None] = mapped_column(String(120), index=True)

    stage_event: Mapped[StageEvent] = relationship(back_populates="analysis_detail")


class ObjectPrepEvent(Base):
    __tablename__ = "object_prep_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    object_id: Mapped[int] = mapped_column(ForeignKey("objects.id", ondelete="CASCADE"), index=True)
    stage_type: Mapped[str] = mapped_column(String(80), index=True)
    performer: Mapped[str | None] = mapped_column(String(255))
    assistant: Mapped[str | None] = mapped_column(String(255))
    event_date: Mapped[date | None] = mapped_column(Date, index=True)
    comment: Mapped[str | None] = mapped_column(Text)
    raw_json: Mapped[dict[str, Any]] = mapped_column(json_type, default=dict)


class DnaExtraction(Base):
    __tablename__ = "dna_extractions"

    id: Mapped[int] = mapped_column(primary_key=True)
    object_id: Mapped[int] = mapped_column(ForeignKey("objects.id", ondelete="CASCADE"), index=True)
    extraction_no: Mapped[int] = mapped_column(Integer)
    extraction_date: Mapped[date | None] = mapped_column(Date, index=True)
    performer: Mapped[str | None] = mapped_column(String(255), index=True)
    extraction_method: Mapped[str | None] = mapped_column(String(255), index=True)
    quant_method: Mapped[str | None] = mapped_column(String(255), index=True)
    quant_date: Mapped[date | None] = mapped_column(Date, index=True)
    quant_performer: Mapped[str | None] = mapped_column(String(255))
    pipetting_method: Mapped[str | None] = mapped_column(String(255))
    comment: Mapped[str | None] = mapped_column(Text)
    raw_json: Mapped[dict[str, Any]] = mapped_column(json_type, default=dict)


class PcrEvent(Base):
    __tablename__ = "pcr_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    object_id: Mapped[int] = mapped_column(ForeignKey("objects.id", ondelete="CASCADE"), index=True)
    pcr_date: Mapped[date | None] = mapped_column(Date, index=True)
    locus_panel: Mapped[str | None] = mapped_column(String(255), index=True)
    pipetting_method: Mapped[str | None] = mapped_column(String(255))
    normalization_performer: Mapped[str | None] = mapped_column(String(255))
    pcr_performer: Mapped[str | None] = mapped_column(String(255), index=True)
    comment: Mapped[str | None] = mapped_column(Text)
    raw_json: Mapped[dict[str, Any]] = mapped_column(json_type, default=dict)


class ElectrophoresisEvent(Base):
    __tablename__ = "electrophoresis_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    object_id: Mapped[int] = mapped_column(ForeignKey("objects.id", ondelete="CASCADE"), index=True)
    electrophoresis_date: Mapped[date | None] = mapped_column(Date, index=True)
    sequencer: Mapped[str | None] = mapped_column(String(255), index=True)
    pipetting_method: Mapped[str | None] = mapped_column(String(255))
    performer_1: Mapped[str | None] = mapped_column(String(255))
    performer_2: Mapped[str | None] = mapped_column(String(255))
    genotype: Mapped[str | None] = mapped_column(String(255))
    comment: Mapped[str | None] = mapped_column(Text)
    raw_json: Mapped[dict[str, Any]] = mapped_column(json_type, default=dict)


class ElectrophoresisAnalysisEvent(Base):
    __tablename__ = "electrophoresis_analysis_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    object_id: Mapped[int] = mapped_column(ForeignKey("objects.id", ondelete="CASCADE"), index=True)
    attempt_no: Mapped[int] = mapped_column(Integer, default=1)
    analysis_date: Mapped[date | None] = mapped_column(Date, index=True)
    performer: Mapped[str | None] = mapped_column(String(255), index=True)
    result_status: Mapped[str | None] = mapped_column(String(120), index=True)
    comment: Mapped[str | None] = mapped_column(Text)
    raw_json: Mapped[dict[str, Any]] = mapped_column(json_type, default=dict)


class RtRun(Base):
    __tablename__ = "rt_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    imported_file_id: Mapped[int | None] = mapped_column(Integer)
    run_name: Mapped[str | None] = mapped_column(String(255))
    run_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    instrument: Mapped[str | None] = mapped_column(String(255))
    kit: Mapped[str | None] = mapped_column(String(255))
    plate_name: Mapped[str | None] = mapped_column(String(255))
    operator: Mapped[str | None] = mapped_column(String(255))
    quant_method: Mapped[str | None] = mapped_column(String(255))
    comment: Mapped[str | None] = mapped_column(Text)
    raw_json: Mapped[dict[str, Any]] = mapped_column(json_type, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    results: Mapped[list["RtResult"]] = relationship(back_populates="rt_run", cascade="all, delete-orphan")


class RtResult(Base):
    __tablename__ = "rt_results"

    id: Mapped[int] = mapped_column(primary_key=True)
    rt_run_id: Mapped[int] = mapped_column(ForeignKey("rt_runs.id", ondelete="CASCADE"), index=True)
    object_id: Mapped[int | None] = mapped_column(ForeignKey("objects.id", ondelete="SET NULL"), index=True)
    sample_name_raw: Mapped[str | None] = mapped_column(String(255), index=True)
    normalized_sample_name: Mapped[str | None] = mapped_column(String(255), index=True)
    sample_base: Mapped[str | None] = mapped_column(String(80), index=True)
    well: Mapped[str | None] = mapped_column(String(40))
    target: Mapped[str | None] = mapped_column(String(255))
    ct: Mapped[float | None] = mapped_column(Float)
    cq: Mapped[float | None] = mapped_column(Float)
    quantity_ng_ul: Mapped[float | None] = mapped_column(Float)
    mean_quantity_ng_ul: Mapped[float | None] = mapped_column(Float)
    degradation_index: Mapped[float | None] = mapped_column(Float)
    ipc_ct: Mapped[float | None] = mapped_column(Float)
    y_quantity: Mapped[float | None] = mapped_column(Float)
    replicate_no: Mapped[int | None] = mapped_column(Integer)
    result_flag: Mapped[str | None] = mapped_column(String(255))
    raw_json: Mapped[dict[str, Any]] = mapped_column(json_type, default=dict)

    rt_run: Mapped[RtRun] = relationship(back_populates="results")
    object: Mapped[RegistryObject | None] = relationship(back_populates="rt_results")


class ElectrophoresisResultFile(Base):
    __tablename__ = "electrophoresis_result_files"

    id: Mapped[int] = mapped_column(primary_key=True)
    object_id: Mapped[int] = mapped_column(ForeignKey("objects.id", ondelete="CASCADE"), index=True)
    run_id: Mapped[int | None] = mapped_column(Integer)
    filename: Mapped[str] = mapped_column(String(255))
    file_path: Mapped[str] = mapped_column(String(500))
    file_type: Mapped[str | None] = mapped_column(String(80))
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    uploaded_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    raw_json: Mapped[dict[str, Any]] = mapped_column(json_type, default=dict)




class ElectrophoresisControlFile(Base, TimestampMixin):
    __tablename__ = "electrophoresis_control_files"

    id: Mapped[int] = mapped_column(primary_key=True)
    party_id: Mapped[int] = mapped_column(ForeignKey("parties.id", ondelete="CASCADE"), index=True)
    case_year: Mapped[int | None] = mapped_column(Integer, index=True)
    control_type: Mapped[str] = mapped_column(String(40), index=True)
    control_label: Mapped[str | None] = mapped_column(String(255))
    filename: Mapped[str] = mapped_column(String(255), index=True)
    file_path: Mapped[str] = mapped_column(String(500))
    file_type: Mapped[str | None] = mapped_column(String(80), default="pdf")
    analysis_date: Mapped[date | None] = mapped_column(Date, index=True)
    analysis_performer: Mapped[str | None] = mapped_column(String(255), index=True)
    uploaded_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    raw_json: Mapped[dict[str, Any]] = mapped_column(json_type, default=dict)

    party: Mapped[Party] = relationship()

    __table_args__ = (
        Index("ix_electrophoresis_control_lookup", "party_id", "control_type", "filename"),
    )


class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)
    entity_type: Mapped[str] = mapped_column(String(120), index=True)
    entity_id: Mapped[str] = mapped_column(String(120), index=True)
    action: Mapped[str] = mapped_column(String(80), index=True)
    before_json: Mapped[dict[str, Any] | None] = mapped_column(json_type)
    after_json: Mapped[dict[str, Any] | None] = mapped_column(json_type)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
