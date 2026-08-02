from __future__ import annotations

from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, Field


JobStatus = Literal["uploaded", "validated", "converting", "ready", "failed", "expired"]


class SequencePayload(BaseModel):
    sequence: str = Field(default="")
    stamping: dict[str, Any] | None = None


class StampingPayload(BaseModel):
    stamping: dict[str, Any] | None = None


class AutoRegistrationPayload(BaseModel):
    start_party_no: str
    case_year: int
    documents_per_party: int = Field(default=100, ge=1, le=500)
    start_rcsme_reg_no: str | None = None
    external_military_numbers: list[str] = Field(default_factory=list)
    intake_date: date | None = None
    decision_date: date | None = None
    investigator: str | None = None
    incoming_no: str | None = None
    box_no: str | None = None
    stamp_field: Literal["decree_no", "rcsme_reg_no"] = "decree_no"
    stamping: dict[str, Any] | None = None


class ApiError(BaseModel):
    detail: str


JsonDict = dict[str, Any]
