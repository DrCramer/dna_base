from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.models import UserRole


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    role: UserRole
    is_active: bool


class LoginRequest(BaseModel):
    username: str
    password: str


class LoginResponse(BaseModel):
    user: UserOut


class ObjectBase(BaseModel):
    party_id: int | None = None
    party_no: str | None = None
    case_year: int | None = None
    parent_object_id: int | None = None
    repeat_suffix: str | None = None
    registry_row_no: str | None = None
    intake_date: date | None = None
    decision_date: date | None = None
    investigator: str | None = None
    incoming_no: str | None = None
    decree_no: str | None = None
    object_description: str | None = None
    external_military_no: str | None = None
    extraction_note: str | None = None
    box_no: str | None = None
    packages_count: int | None = None
    rcsme_reg_no: str | None = None
    rcsme_reg_no_is_manual: bool | None = None
    object_type: str | None = None
    extracted_before: str | None = None
    not_extracted_before: str | None = None
    registry_filled_by: str | None = None
    status: str | None = None


class ObjectUpdate(ObjectBase):
    pass


class ObjectCreate(ObjectBase):
    pass


class ObjectOut(ObjectBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    source_import_batch_id: int | None
    source_sheet_name: str | None
    source_row_number: int | None
    decree_no_base: str | None
    rcsme_reg_no_base: str | None
    raw_registry_json: dict[str, Any]
    created_at: datetime
    updated_at: datetime
    prep_events: list["ObjectPrepEventOut"] = []
    dna_extractions: list["DnaExtractionOut"] = []
    pcr_events: list["PcrEventOut"] = []
    electrophoresis_events: list["ElectrophoresisEventOut"] = []
    electrophoresis_analysis_events: list["ElectrophoresisAnalysisEventOut"] = []
    rt_results: list["RtResultOut"] = []
    electrophoresis_result_files: list["ElectrophoresisResultFileOut"] = []
    stage_events: list["StageEventOut"] = []


class ObjectListItemOut(ObjectBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    source_import_batch_id: int | None
    source_sheet_name: str | None
    source_row_number: int | None
    decree_no_base: str | None
    rcsme_reg_no_base: str | None
    stage_summary: dict[str, Any] = {}
    last_stage: str | None = None
    last_stage_date: date | None = None
    repeat_count: int = 0
    created_at: datetime
    updated_at: datetime


class EmployeeStageRoleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    stage_type: str
    role: str | None = None
    is_active: bool = True


class EmployeeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    full_name: str
    short_name: str | None
    initials: str | None = None
    role: str | None = None
    is_verified: bool = True
    is_active: bool
    stage_roles: list[EmployeeStageRoleOut] = []


class EmployeeCreate(BaseModel):
    full_name: str
    short_name: str | None = None
    initials: str | None = None
    role: str | None = None
    is_verified: bool = True
    stage_roles: list[str] = []


class EmployeeUpdate(BaseModel):
    full_name: str | None = None
    short_name: str | None = None
    initials: str | None = None
    role: str | None = None
    is_verified: bool | None = None
    is_active: bool | None = None
    stage_roles: list[str] | None = None


class ReferenceItemBase(BaseModel):
    category: str
    name: str
    short_name: str | None = None
    comment: str | None = None
    is_active: bool = True


class ReferenceItemCreate(ReferenceItemBase):
    pass


class ReferenceItemUpdate(BaseModel):
    category: str | None = None
    name: str | None = None
    short_name: str | None = None
    comment: str | None = None
    is_active: bool | None = None


class ReferenceItemOut(ReferenceItemBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
    updated_at: datetime


class StageEventPerformerOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    employee_id: int | None
    role: str
    order_index: int
    raw_name: str | None


class SamplePrepDetailOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    registry_filled_by: str | None
    photo_performers: list[Any]
    photo_assistants: list[Any]
    washing_performers: list[Any]
    washing_assistants: list[Any]
    washing_date: date | None
    bone_tissue_performers: list[Any]
    bone_tissue_date: date | None


class MillingDetailOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    milling_performers: list[Any]
    cups: str | None
    milling_date: date | None


class DnaExtractionDetailOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    extraction_date: date | None
    extraction_method: str | None


class RealtimeDetailOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    quant_method: str | None
    quant_date: date | None
    quant_performer: str | None
    pipetting_method: str | None
    concentration: float | None = None
    ct_cq: float | None = None
    di: float | None = None
    ipc: float | None = None
    long_quantity: float | None = None
    small_quantity: float | None = None
    y_quantity: float | None = None
    comment: str | None


class PcrDetailOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    pcr_date: date | None
    locus_panel: str | None
    pipetting_method: str | None
    normalization_performers: list[Any]
    pcr_performers: list[Any]


class ElectrophoresisDetailOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    electrophoresis_date: date | None
    sequencer: str | None
    pipetting_method: str | None
    performers: list[Any]


class AnalysisDetailOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    genotype: str | None
    analysis_date: date | None
    status: str | None


class StageEventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    object_id: int
    work_session_id: int | None
    stage_type: str
    attempt_no: int
    event_date: date | None
    source: str
    comment: str | None
    raw_json: dict[str, Any]
    created_by_user_id: int | None
    is_cancelled: bool
    created_at: datetime
    updated_at: datetime
    performers: list[StageEventPerformerOut] = []
    sample_prep_detail: SamplePrepDetailOut | None = None
    milling_detail: MillingDetailOut | None = None
    dna_extraction_detail: DnaExtractionDetailOut | None = None
    realtime_detail: RealtimeDetailOut | None = None
    pcr_detail: PcrDetailOut | None = None
    electrophoresis_detail: ElectrophoresisDetailOut | None = None
    analysis_detail: AnalysisDetailOut | None = None


class PartyBase(BaseModel):
    party_no: str
    case_year: int | None = None
    title: str | None = None
    comment: str | None = None
    status: str = "active"


class PartyCreate(PartyBase):
    pass


class PartyUpdate(BaseModel):
    title: str | None = None
    comment: str | None = None
    status: str | None = None
    control_actual_decrees: str | None = None
    control_decree_without_object: str | None = None
    control_object_without_decree: str | None = None
    control_unidentified_rostov_no: str | None = None
    control_need_recall: str | None = None
    control_recalled: str | None = None


class PartyOut(PartyBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_by_user_id: int | None
    object_count: int
    control_actual_decrees: str | None
    control_decree_without_object: str | None
    control_object_without_decree: str | None
    control_unidentified_rostov_no: str | None
    control_need_recall: str | None
    control_recalled: str | None
    raw_control_json: dict[str, Any]
    created_at: datetime
    updated_at: datetime


class PartyList(BaseModel):
    items: list[PartyOut]
    total: int


class PartyYearsOut(BaseModel):
    years: list[int]
    default_year: int | None = None


class PartyProgressOut(BaseModel):
    party_id: int
    object_count: int
    stage_counts: dict[str, int]
    completed_objects: int
    objects_without_events: int


class PartyPermanentDeleteOut(BaseModel):
    party_id: int
    party_no: str
    objects_deleted: int
    stage_events_deleted: int
    rt_results_deleted: int
    files_deleted: int


class RegistrationBulkRequest(BaseModel):
    start_rcsme_reg_no: str | None = None
    count: int = 1
    update_existing: bool = False
    intake_date: date | None = None
    decision_date: date | None = None
    investigator: str | None = None
    incoming_no: str | None = None
    box_no: str | None = None
    external_military_numbers: list[str] = []


class RegistrationBulkRow(BaseModel):
    index: int
    object_id: int | None = None
    registry_row_no: str
    rcsme_reg_no: str
    decree_no: str
    external_military_no: str | None = None
    intake_date: date | None = None
    decision_date: date | None = None
    investigator: str | None = None
    incoming_no: str | None = None
    box_no: str | None = None
    conflicts: list[str] = []


class RegistrationBulkPreviewOut(BaseModel):
    suggested_start_rcsme_reg_no: str
    case_year: int | None = None
    previous_party_no: str | None = None
    previous_last_rcsme_reg_no: str | None = None
    existing_party_object_count: int = 0
    rows: list[RegistrationBulkRow]
    conflicts: list[str] = []
    warnings: list[str] = []
    extra_external_military_numbers: list[str] = []


class RegistrationBulkApplyOut(BaseModel):
    party_id: int
    party_no: str
    objects_created: int
    objects_updated: int = 0
    rows: list[RegistrationBulkRow]
    warnings: list[str] = []


class RegistrationListPartyPreview(BaseModel):
    party_no: str
    case_year: int
    column_letter: str
    object_count: int
    first_external_military_no: str | None = None
    last_external_military_no: str | None = None
    first_rcsme_reg_no: str | None = None
    last_rcsme_reg_no: str | None = None
    existing_party_id: int | None = None
    existing_object_count: int = 0
    will_create_party: bool = False
    status: str
    warnings: list[str] = []
    sample_rows: list[RegistrationBulkRow] = []


class RegistrationListPreviewOut(BaseModel):
    upload_id: str
    filename: str
    file_sha256: str
    sheet_name: str
    start_party_no: str
    case_year: int
    suggested_start_rcsme_reg_no: str
    previous_party_no: str | None = None
    previous_last_rcsme_reg_no: str | None = None
    party_count: int
    total_objects: int
    parties_to_create: int
    existing_parties: int
    conflicts: list[str] = []
    warnings: list[str] = []
    parties: list[RegistrationListPartyPreview]


class RegistrationListCommitRequest(BaseModel):
    upload_id: str
    start_party_no: str
    case_year: int
    intake_date: date | None = None
    decision_date: date | None = None
    investigator: str | None = None
    incoming_no: str | None = None
    box_no: str | None = None
    duplicate_mode: Literal["block", "update_empty_or_existing"] = "block"


class RegistrationListCommitResponse(BaseModel):
    parties_created: int
    parties_updated: int
    objects_created: int
    objects_updated: int = 0
    warnings: list[str] = []
    parties: list[RegistrationListPartyPreview] = []


class WorkSessionPreviewRequest(BaseModel):
    stage_type: str
    party_ids: list[int] = []
    object_ids: list[int] = []
    title: str | None = None
    work_date: date | None = None
    comment: str | None = None
    detail_data: dict[str, Any] = {}
    performers: list[dict[str, Any]] = []


class WorkSessionPreviewResponse(BaseModel):
    object_count: int
    party_ids: list[int]
    stage_type: str
    objects_with_existing_stage: int
    objects_without_stage: int
    next_attempt_min: int
    next_attempt_max: int
    sample_objects: list[ObjectListItemOut]
    warnings: list[str] = []


class WorkSessionCommitRequest(WorkSessionPreviewRequest):
    source: str = "manual"


class WorkSessionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    party_id: int | None
    stage_type: str
    title: str | None
    work_date: date | None
    comment: str | None
    created_by_user_id: int | None
    source: str
    status: str
    raw_json: dict[str, Any]
    created_at: datetime
    updated_at: datetime
    stage_events: list[StageEventOut] = []


class WorkSessionCommitResponse(BaseModel):
    session_id: int
    object_count: int
    stage_events_created: int


class StageTableColumnOut(BaseModel):
    key: str
    label: str
    type: str = "text"
    editable: bool = False
    width: int = 140
    input: str = "text"
    dictionary_category: str | None = None


class StageTableEventOut(BaseModel):
    id: int
    stage_type: str
    attempt_no: int
    event_date: date | None = None
    source: str
    comment: str | None = None
    performers: list[str] = []


class StageTableRowOut(BaseModel):
    object: ObjectListItemOut
    values: dict[str, Any]
    latest_event: StageTableEventOut | None = None
    attempt_no: int | None = None
    repeat_count: int = 0
    history_available: bool = False
    history: list[StageTableEventOut] = []


class StageTableResponse(BaseModel):
    stage_type: str
    party_ids: list[int]
    columns: list[StageTableColumnOut]
    rows: list[StageTableRowOut]
    total: int
    filters: dict[str, Any] = {}


class StageTableQueryRequest(BaseModel):
    party_ids: list[int] = []
    stage_type: str = "registration"
    q: str | None = None
    filters: dict[str, Any] = {}
    include_archived: bool = False
    show_latest_only: bool = True
    show_history: bool = False
    limit: int | None = None
    offset: int = 0


class StageEventsPreviewRequest(BaseModel):
    stage_type: str
    party_ids: list[int] = []
    object_ids: list[int] = []
    q: str | None = None
    filters: dict[str, Any] = {}
    title: str | None = None
    work_date: date | None = None
    comment: str | None = None
    detail_data: dict[str, Any] = {}
    performers: list[dict[str, Any]] = []


class StageEventsApplyRequest(StageEventsPreviewRequest):
    source: str = "manual"
    apply_mode: Literal["append", "update_latest"] = "append"


class StageEventsInlineApplyRequest(BaseModel):
    stage_type: str
    object_id: int
    detail_data: dict[str, Any] = {}
    performers: list[dict[str, Any]] = []
    comment: str | None = None
    source: str = "manual"


class StageEventsPreviewResponse(BaseModel):
    object_count: int
    stage_type: str
    objects_with_existing_stage: int
    objects_without_stage: int
    next_attempt_min: int
    next_attempt_max: int
    filled_fields: list[str] = []
    warnings: list[str] = []
    sample_rows: list[StageTableRowOut] = []


class StageEventsApplyResponse(BaseModel):
    session_id: int
    object_count: int
    stage_events_created: int
    stage_events_updated: int = 0


class StageEventsInlineApplyResponse(BaseModel):
    event_id: int
    object_id: int
    stage_type: str
    attempt_no: int


class ObjectList(BaseModel):
    items: list[ObjectListItemOut]
    total: int
    limit: int | None
    offset: int


class ObjectPrepEventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    stage_type: str
    performer: str | None
    assistant: str | None
    event_date: date | None
    comment: str | None
    raw_json: dict[str, Any]


class DnaExtractionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    extraction_no: int
    extraction_date: date | None
    performer: str | None
    extraction_method: str | None
    quant_method: str | None
    quant_date: date | None
    quant_performer: str | None
    pipetting_method: str | None
    comment: str | None
    raw_json: dict[str, Any]


class PcrEventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    pcr_date: date | None
    locus_panel: str | None
    pipetting_method: str | None
    normalization_performer: str | None
    pcr_performer: str | None
    comment: str | None
    raw_json: dict[str, Any]


class ElectrophoresisEventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    electrophoresis_date: date | None
    sequencer: str | None
    pipetting_method: str | None
    performer_1: str | None
    performer_2: str | None
    genotype: str | None
    comment: str | None
    raw_json: dict[str, Any]


class ElectrophoresisAnalysisEventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    attempt_no: int
    analysis_date: date | None
    performer: str | None
    result_status: str | None
    comment: str | None
    raw_json: dict[str, Any]


class ElectrophoresisResultFileOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    object_id: int
    run_id: int | None
    filename: str
    file_path: str
    file_type: str | None
    uploaded_at: datetime
    uploaded_by: int | None
    raw_json: dict[str, Any]


class RtResultOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    rt_run_id: int
    sample_name_raw: str | None
    normalized_sample_name: str | None
    sample_base: str | None
    well: str | None
    target: str | None
    ct: float | None
    cq: float | None
    quantity_ng_ul: float | None
    mean_quantity_ng_ul: float | None
    degradation_index: float | None
    ipc_ct: float | None
    y_quantity: float | None
    replicate_no: int | None
    result_flag: str | None
    raw_json: dict[str, Any]


class ImportPreviewResponse(BaseModel):
    upload_id: str
    filename: str
    file_sha256: str
    party_no: str | None
    case_year: int | None = None
    sheet_name: str
    rows_detected: int
    rows_skipped: int
    sample_rows: list[dict[str, Any]]
    warnings: list[str]
    duplicates: list[dict[str, Any]]
    stage_event_counts: dict[str, int] = {}
    party_control: dict[str, Any] = {}
    existing_objects_count: int = 0
    new_objects_count: int = 0
    replace_required_count: int = 0


class ImportCommitRequest(BaseModel):
    upload_id: str
    duplicate_mode: Literal["block", "replace"] = "block"


class RtCommitRequest(BaseModel):
    upload_id: str
    quant_performer: str | None = None
    employee_id: int | None = None
    duplicate_mode: Literal["block", "replace", "append"] = "block"


class ElectrophoresisPdfCommitRequest(BaseModel):
    upload_ids: list[str]
    case_year: int | None = None
    party_id: int | None = None
    control_party_ids: list[int] = Field(default_factory=list)
    duplicate_mode: Literal["block", "replace", "append"] = "block"
    file_modes: dict[str, Literal["block", "replace", "append"]] = Field(default_factory=dict)
    analysis_date: date | None = None
    analysis_performer: str | None = None
    employee_id: int | None = None


class ImportCommitResponse(BaseModel):
    batch_id: int
    rows_total: int
    rows_imported: int
    rows_updated: int = 0
    rows_skipped: int
    stage_events_written: int = 0
    warnings: list[str]


class RtPreviewResponse(BaseModel):
    upload_id: str
    filename: str
    file_sha256: str
    parser_type: str
    run_date: date | None = None
    quant_method: str | None = None
    columns: list[str]
    sample_names: list[str]
    sample_rows: list[dict[str, Any]]
    unmatched_samples: list[dict[str, Any]] = []
    warnings: list[str]
    matched_count: int
    unmatched_count: int
    existing_rt_count: int = 0
    existing_rt_samples: list[dict[str, Any]] = []
    repeat_samples: list[dict[str, Any]] = []


class RtCommitResponse(BaseModel):
    run_id: int
    results_written: int
    stage_events_written: int
    matched_count: int
    unmatched_count: int
    replaced_results: int = 0
    replaced_stage_events: int = 0
    warnings: list[str] = []


class ElectrophoresisPdfPreviewItem(BaseModel):
    upload_id: str
    filename: str
    file_sha256: str
    samples: list[dict[str, Any]]
    matched_count: int
    unmatched_count: int
    existing_count: int = 0
    control_count: int = 0
    warnings: list[str] = []


class ElectrophoresisPdfPreviewResponse(BaseModel):
    items: list[ElectrophoresisPdfPreviewItem]
    matched_count: int
    unmatched_count: int
    existing_count: int = 0
    control_count: int = 0


class ElectrophoresisPdfCommitResponse(BaseModel):
    files_written: int
    matched_count: int
    unmatched_count: int
    files_replaced: int = 0
    control_files_written: int = 0
    control_files_replaced: int = 0
    analysis_events_written: int = 0
    warnings: list[str] = []


class WorkProtocolStageBlock(BaseModel):
    stage_type: str
    title: str
    detail_data: dict[str, Any]
    performers: list[dict[str, Any]] = []


class WorkProtocolObjectRow(BaseModel):
    sample_name_raw: str | None = None
    normalized_sample_name: str | None = None
    sample_object_no: str | None = None
    sample_base: str | None = None
    repeat_suffix: str | None = None
    well: str | None = None
    matched: bool = False
    object_id: int | None = None
    object_rcsme_reg_no: str | None = None
    object_decree_no: str | None = None
    party_id: int | None = None
    party_no: str | None = None
    is_repeat_sample: bool = False
    repeat_object_exists: bool = False
    parent_object_id: int | None = None
    parent_rcsme_reg_no: str | None = None


class WorkProtocolPlateCell(BaseModel):
    sample_name_raw: str | None = None
    normalized_sample_name: str | None = None
    sample_object_no: str | None = None
    sample_base: str | None = None
    repeat_suffix: str | None = None
    well: str | None = None
    is_service: bool = False


class WorkProtocolPreviewResponse(BaseModel):
    upload_id: str
    filename: str
    file_sha256: str
    protocol_title: str | None = None
    protocol_no: str | None = None
    protocol_name: str | None = None
    objects: list[WorkProtocolObjectRow]
    plate_cells: list[WorkProtocolPlateCell] = []
    stage_blocks: list[WorkProtocolStageBlock]
    matched_count: int
    unmatched_count: int
    repeat_count: int = 0
    warnings: list[str] = []


class RcsmeFixPreviewItem(BaseModel):
    id: int
    party_no: str | None
    decree_no: str | None
    current_rcsme_reg_no: str
    suggested_rcsme_reg_no: str


class RcsmeFixPreviewResponse(BaseModel):
    total: int
    conflicts: int
    sample_rows: list[RcsmeFixPreviewItem]


class RcsmeFixApplyResponse(BaseModel):
    fixed: int
    skipped: int
    conflicts: int


class AuditOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int | None
    entity_type: str
    entity_id: str
    action: str
    before_json: dict[str, Any] | None
    after_json: dict[str, Any] | None
    created_at: datetime


StageEventOut.model_rebuild()
WorkSessionOut.model_rebuild()
ObjectOut.model_rebuild()
