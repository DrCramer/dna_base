from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


StageType = Literal["dna_extraction", "realtime", "pcr", "electrophoresis"]
ProtocolStatus = Literal["draft", "final", "archived"]
ProtocolKind = Literal["chs", "genetic_examination"]
DilutionTarget = Literal["long", "small", "y"]


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


class ProtocolPipettingConstraints(BaseModel):
    water_increment_ul: float | None = Field(default=None, gt=0, allow_inf_nan=False)
    water_min_ul: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    water_max_ul: float | None = Field(default=None, gt=0, allow_inf_nan=False)
    dna_increment_ul: float | None = Field(default=None, gt=0, allow_inf_nan=False)
    dna_min_ul: float | None = Field(default=None, gt=0, allow_inf_nan=False)
    dna_max_ul: float | None = Field(default=None, gt=0, allow_inf_nan=False)
    first_dilution_reserve_ul: float = Field(default=0, ge=0, allow_inf_nan=False)

    @model_validator(mode="after")
    def valid_ranges(self):
        for prefix in ("water", "dna"):
            lower = getattr(self, f"{prefix}_min_ul")
            upper = getattr(self, f"{prefix}_max_ul")
            if lower is not None and upper is not None and lower > upper:
                raise ValueError("Минимальный объём не может превышать максимальный")
        return self


class ProtocolDilutionSettings(BaseModel):
    enabled: bool = True
    show_all_targets: bool = False
    target_overrides: dict[str, DilutionTarget] = Field(default_factory=dict, max_length=10000)
    target_concentration: float = Field(default=0.1, gt=0, allow_inf_nan=False)
    source_dna_volume: float = Field(default=3, gt=0, allow_inf_nan=False)
    dilution_one_volume: float = Field(default=10, gt=0, allow_inf_nan=False)
    threshold: float = Field(default=100, gt=1, allow_inf_nan=False)
    minimum_final_volume_enabled: bool = False
    minimum_final_volume: float = Field(default=15, gt=0, allow_inf_nan=False)
    source_available_volume: float = Field(default=50, gt=0, allow_inf_nan=False)
    optimize_water_volumes: bool = False
    allowed_concentration_error_percent: float = Field(default=5, ge=0, lt=100, allow_inf_nan=False)
    preferred_water_step_ul: int = Field(default=10, ge=1, le=1000)
    optimization_priority: Literal["fewest_volumes", "minimum_error"] = "fewest_volumes"
    max_under_target_pct: float | None = Field(default=None, ge=0, lt=100, allow_inf_nan=False)
    max_over_target_pct: float | None = Field(default=None, ge=0, lt=100, allow_inf_nan=False)
    pipetting: ProtocolPipettingConstraints = Field(default_factory=ProtocolPipettingConstraints)


class ProtocolSelectionSettings(BaseModel):
    case_year: int | None = None
    party_ids: list[int] = Field(default_factory=list)
    rcsme_from: str | None = None
    rcsme_to: str | None = None
    description: str | None = None
    numbers: list[str] = Field(default_factory=list)


class ProtocolPreviewRequest(BaseModel):
    kind: ProtocolKind = "chs"
    examination_year: int | None = Field(default=None, ge=1900, le=2200)
    imported_wells: list["ProtocolImportedWell"] = Field(default_factory=list, max_length=40000)
    protocol_date: date
    protocol_no: int = Field(ge=1)
    name: str = Field(min_length=1, max_length=255)
    comment: str | None = None
    object_ids: list[int] = Field(min_length=1)
    stages: list[ProtocolStageInput] = Field(default_factory=list)
    plate_rules: ProtocolPlateRules = Field(default_factory=ProtocolPlateRules)
    dilution: ProtocolDilutionSettings = Field(default_factory=ProtocolDilutionSettings)
    selection: ProtocolSelectionSettings | None = None

    @field_validator("object_ids")
    @classmethod
    def unique_object_ids(cls, value: list[int]) -> list[int]:
        return list(dict.fromkeys(value))

    @model_validator(mode="after")
    def valid_source(self):
        if self.kind == "genetic_examination" and self.examination_year is None:
            raise ValueError("Год экспертизы обязателен")
        if self.kind == "genetic_examination" and self.selection and self.selection.party_ids:
            raise ValueError("Генетические экспертизы не относятся к партиям")
        if self.imported_wells and self.kind != "genetic_examination":
            raise ValueError("Импортированная раскладка относится к генетическим экспертизам")
        return self


class ProtocolImportedWell(BaseModel):
    layout_key: Literal["source", "pcr"]
    plate_index: int = Field(ge=1, le=500)
    well: str = Field(pattern=r"^[A-H](?:[1-9]|1[0-2])$")
    kind: Literal["sample", "ladder", "pc", "nc", "standard", "empty"]
    source_id: int | None = None
    label: str | None = Field(default=None, max_length=255)


ProtocolPreviewRequest.model_rebuild()


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
    dilution_optimization: dict[str, Any] | None = None
    warnings: list[str]
    snapshot: dict[str, Any]


class ProtocolMetaOut(BaseModel):
    protocol_date: date
    suggested_no: int
    suggested_name: str
    max_objects: int = 2000


class ProtocolObjectOut(BaseModel):
    id: int
    party_id: int | None
    party_no: str | None
    case_year: int | None
    rcsme_reg_no: str | None
    object_description: str | None
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
    matched_numbers: list[str] = Field(default_factory=list)
    missing_numbers: list[str] = Field(default_factory=list)


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
    kind: ProtocolKind = "chs"
    examination_names: list[str] = Field(default_factory=list)
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
    kind: ProtocolKind = "chs"
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
    plate_calculations: dict[str, Any] = Field(default_factory=dict)


class ProtocolDuplicateRequest(BaseModel):
    copy_objects: bool = False
    protocol_date: date | None = None


class ProtocolArchiveOut(BaseModel):
    id: int
    status: ProtocolStatus


class ProtocolExporterOut(BaseModel):
    key: str
    stage_type: str
