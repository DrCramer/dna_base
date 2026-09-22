from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


StageType = Literal["dna_extraction", "realtime", "pcr", "electrophoresis"]
ProtocolStatus = Literal["draft", "final", "archived"]


class ProtocolPerformerInput(BaseModel):
    employee_id: int | None = None
    display_name: str | None = None
    role: str | None = None


class ProtocolStageInput(BaseModel):
    stage_type: StageType
    enabled: bool = True
    work_date: date | None = None
    profile_id: int | None = None
    kit_name: str | None = None
    sequencer_name: str | None = None
    comment: str | None = None
    performer_ids: list[int] = Field(default_factory=list)
    performers: list[ProtocolPerformerInput] = Field(default_factory=list)
    settings: dict[str, Any] = Field(default_factory=dict)


class ProtocolPlateRules(BaseModel):
    rows: int = 8
    columns: int = 12
    fill_order: Literal["column"] = "column"
    ladder_enabled: bool = False
    ladder_wells: list[str] = Field(default_factory=lambda: ["A1", "A3", "A5", "A7", "A9", "A11"])
    pc_enabled: bool = False
    nc_enabled: bool = True


class ProtocolDilutionSettings(BaseModel):
    enabled: bool = True
    target_concentration: float = Field(default=0.1, gt=0)
    source_dna_volume: float = Field(default=3, gt=0)
    dilution_one_volume: float = Field(default=10, gt=0)
    threshold: float = Field(default=100, gt=1)


class ProtocolPreviewRequest(BaseModel):
    protocol_date: date
    protocol_no: int = Field(ge=1)
    name: str = Field(min_length=1, max_length=255)
    comment: str | None = None
    object_ids: list[int] = Field(min_length=1)
    stages: list[ProtocolStageInput] = Field(default_factory=list)
    plate_rules: ProtocolPlateRules = Field(default_factory=ProtocolPlateRules)
    dilution: ProtocolDilutionSettings = Field(default_factory=ProtocolDilutionSettings)


class ProtocolCreateRequest(ProtocolPreviewRequest):
    pass


class ProtocolUpdateRequest(ProtocolPreviewRequest):
    pass


class ProtocolPreviewOut(BaseModel):
    selected_count: int
    capacity: int
    max_capacity: int
    objects: list[dict[str, Any]]
    stages: list[dict[str, Any]]
    layouts: dict[str, Any]
    calculations: dict[str, Any]
    dilutions: list[dict[str, Any]]
    warnings: list[str]
    snapshot: dict[str, Any]


class ProtocolMetaOut(BaseModel):
    protocol_date: date
    suggested_no: int
    suggested_name: str


class ProtocolObjectOut(BaseModel):
    id: int
    party_id: int | None
    party_no: str | None
    case_year: int | None
    rcsme_reg_no: str | None
    decree_no: str | None
    external_military_no: str | None
    object_type: str | None
    box_no: str | None
    has_rt: bool = False
    stage_types: list[str] = Field(default_factory=list)


class ProtocolObjectListOut(BaseModel):
    items: list[ProtocolObjectOut]
    total: int
    limit: int
    offset: int


class ProtocolObjectResolveOut(BaseModel):
    object_ids: list[int]
    total: int


class ProtocolProfileBase(BaseModel):
    stage_type: StageType
    name: str = Field(min_length=1, max_length=255)
    reference_item_id: int | None = None
    active: bool = True
    plate_rules_json: dict[str, Any] = Field(default_factory=dict)
    reagent_config_json: dict[str, Any] = Field(default_factory=dict)
    instrument_config_json: dict[str, Any] = Field(default_factory=dict)


class ProtocolProfileCreate(ProtocolProfileBase):
    pass


class ProtocolProfileUpdate(BaseModel):
    name: str | None = None
    reference_item_id: int | None = None
    active: bool | None = None
    plate_rules_json: dict[str, Any] | None = None
    reagent_config_json: dict[str, Any] | None = None
    instrument_config_json: dict[str, Any] | None = None


class ProtocolProfileOut(ProtocolProfileBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
    updated_at: datetime


class ProtocolSummaryOut(BaseModel):
    id: int
    series_key: str
    protocol_no: int
    protocol_date: date
    name: str
    status: ProtocolStatus
    revision_no: int
    object_count: int
    party_numbers: list[str]
    stage_types: list[str]
    author: str | None
    updated_at: datetime


class ProtocolListOut(BaseModel):
    items: list[ProtocolSummaryOut]
    total: int
    limit: int
    offset: int


class ProtocolRevisionOut(BaseModel):
    id: int
    revision_no: int
    status: ProtocolStatus
    updated_at: datetime


class ProtocolOut(BaseModel):
    id: int
    series_key: str
    protocol_no: int
    protocol_date: date
    name: str
    status: ProtocolStatus
    revision_no: int
    comment: str | None
    created_by_user_id: int | None
    created_at: datetime
    updated_at: datetime
    finalized_at: datetime | None
    snapshot: dict[str, Any]
    revisions: list[ProtocolRevisionOut] = Field(default_factory=list)


class ProtocolDuplicateRequest(BaseModel):
    copy_objects: bool = False
    protocol_date: date | None = None


class ProtocolArchiveOut(BaseModel):
    id: int
    status: ProtocolStatus


class ProtocolExporterOut(BaseModel):
    key: str
    stage_type: str
