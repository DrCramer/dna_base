export type Role = 'admin' | 'user' | 'viewer'

export interface User {
  id: number
  username: string
  role: Role
  is_active: boolean
}

export interface RegistryObject {
  id: number
  source_import_batch_id: number | null
  source_sheet_name: string | null
  source_row_number: number | null
  party_id: number | null
  party_no: string | null
  case_year: number | null
  parent_object_id: number | null
  repeat_suffix: string | null
  registry_row_no: string | null
  intake_date: string | null
  decision_date: string | null
  investigator: string | null
  incoming_no: string | null
  decree_no: string | null
  decree_no_base: string | null
  object_description: string | null
  external_military_no: string | null
  extraction_note: string | null
  box_no: string | null
  packages_count: number | null
  rcsme_reg_no: string | null
  rcsme_reg_no_base: string | null
  rcsme_reg_no_is_manual: boolean | null
  object_type: string | null
  extracted_before: string | null
  not_extracted_before: string | null
  registry_filled_by: string | null
  status: string | null
  raw_registry_json: Record<string, unknown>
  created_at: string
  updated_at: string
  prep_events: ObjectPrepEvent[]
  dna_extractions: DnaExtraction[]
  pcr_events: PcrEvent[]
  electrophoresis_events: ElectrophoresisEvent[]
  electrophoresis_analysis_events: ElectrophoresisAnalysisEvent[]
  rt_results: RtResult[]
  electrophoresis_result_files: ElectrophoresisResultFile[]
  stage_events: StageEvent[]
}

export interface StageEventPerformer {
  id: number
  employee_id: number | null
  role: string
  order_index: number
  raw_name: string | null
}

export interface StageEvent {
  id: number
  object_id: number
  work_session_id: number | null
  stage_type: string
  attempt_no: number
  event_date: string | null
  source: string
  comment: string | null
  raw_json: Record<string, unknown>
  created_by_user_id: number | null
  is_cancelled: boolean
  created_at: string
  updated_at: string
  performers: StageEventPerformer[]
  sample_prep_detail: Record<string, unknown> | null
  milling_detail: Record<string, unknown> | null
  dna_extraction_detail: Record<string, unknown> | null
  realtime_detail: Record<string, unknown> | null
  pcr_detail: Record<string, unknown> | null
  electrophoresis_detail: Record<string, unknown> | null
  analysis_detail: Record<string, unknown> | null
}

export interface ObjectPrepEvent {
  id: number
  stage_type: string
  performer: string | null
  assistant: string | null
  event_date: string | null
  comment: string | null
  raw_json: Record<string, unknown>
}

export interface DnaExtraction {
  id: number
  extraction_no: number
  extraction_date: string | null
  performer: string | null
  extraction_method: string | null
  quant_method: string | null
  quant_date: string | null
  quant_performer: string | null
  pipetting_method: string | null
  comment: string | null
  raw_json: Record<string, unknown>
}

export interface PcrEvent {
  id: number
  pcr_date: string | null
  locus_panel: string | null
  pipetting_method: string | null
  normalization_performer: string | null
  pcr_performer: string | null
  comment: string | null
  raw_json: Record<string, unknown>
}

export interface ElectrophoresisEvent {
  id: number
  electrophoresis_date: string | null
  sequencer: string | null
  pipetting_method: string | null
  performer_1: string | null
  performer_2: string | null
  genotype: string | null
  comment: string | null
  raw_json: Record<string, unknown>
}

export interface ElectrophoresisAnalysisEvent {
  id: number
  attempt_no: number
  analysis_date: string | null
  performer: string | null
  result_status: string | null
  comment: string | null
  raw_json: Record<string, unknown>
}

export interface RtResult {
  id: number
  rt_run_id: number
  sample_name_raw: string | null
  normalized_sample_name: string | null
  sample_base: string | null
  well: string | null
  target: string | null
  ct: number | null
  cq: number | null
  quantity_ng_ul: number | null
  mean_quantity_ng_ul: number | null
  degradation_index: number | null
  ipc_ct: number | null
  y_quantity: number | null
  replicate_no: number | null
  result_flag: string | null
  raw_json: Record<string, unknown>
}

export interface ElectrophoresisResultFile {
  id: number
  object_id: number
  run_id: number | null
  filename: string
  file_path: string
  file_type: string | null
  uploaded_at: string
  uploaded_by: number | null
  raw_json: Record<string, unknown>
}

export type RegistryObjectListItem = Omit<
  RegistryObject,
  | 'raw_registry_json'
  | 'prep_events'
  | 'dna_extractions'
  | 'pcr_events'
  | 'electrophoresis_events'
  | 'electrophoresis_analysis_events'
  | 'rt_results'
  | 'electrophoresis_result_files'
  | 'stage_events'
>

export interface RegistryObjectListItemBase extends RegistryObjectListItem {
  stage_summary: Record<string, { count: number; latest_date: string | null }>
  last_stage: string | null
  last_stage_date: string | null
  repeat_count: number
}

export interface ObjectList {
  items: RegistryObjectListItemBase[]
  total: number
  limit: number | null
  offset: number
}

export interface Party {
  id: number
  party_no: string
  case_year: number | null
  title: string | null
  comment: string | null
  status: string
  created_by_user_id: number | null
  object_count: number
  control_actual_decrees: string | null
  control_decree_without_object: string | null
  control_object_without_decree: string | null
  control_unidentified_rostov_no: string | null
  control_need_recall: string | null
  control_recalled: string | null
  raw_control_json: Record<string, unknown>
  created_at: string
  updated_at: string
}

export interface PartyList {
  items: Party[]
  total: number
}

export interface PartyYears {
  years: number[]
  default_year: number | null
}

export interface RegistryExportPreview {
  object_count: number
  party_count: number
}

export interface PartyProgress {
  party_id: number
  object_count: number
  stage_counts: Record<string, number>
  completed_objects: number
  objects_without_events: number
}

export interface PartyPermanentDeleteResponse {
  party_id: number
  party_no: string
  objects_deleted: number
  stage_events_deleted: number
  rt_results_deleted: number
  files_deleted: number
}

export interface RegistrationBulkRequest {
  start_rcsme_reg_no?: string | null
  count: number
  update_existing?: boolean
  intake_date?: string | null
  decision_date?: string | null
  investigator?: string | null
  incoming_no?: string | null
  box_no?: string | null
  external_military_numbers?: string[]
}

export interface RegistrationBulkRow {
  index: number
  object_id?: number | null
  registry_row_no: string
  rcsme_reg_no: string
  decree_no: string
  external_military_no: string | null
  intake_date: string | null
  decision_date: string | null
  investigator: string | null
  incoming_no: string | null
  box_no: string | null
  conflicts: string[]
}

export interface RegistrationBulkPreview {
  suggested_start_rcsme_reg_no: string
  case_year: number | null
  previous_party_no: string | null
  previous_last_rcsme_reg_no: string | null
  existing_party_object_count: number
  rows: RegistrationBulkRow[]
  conflicts: string[]
  warnings: string[]
  extra_external_military_numbers: string[]
}

export interface RegistrationBulkApplyResponse {
  party_id: number
  party_no: string
  objects_created: number
  objects_updated: number
  rows: RegistrationBulkRow[]
  warnings: string[]
}

export interface RegistrationListPartyPreview {
  party_no: string
  case_year: number
  column_letter: string
  object_count: number
  first_external_military_no: string | null
  last_external_military_no: string | null
  first_rcsme_reg_no: string | null
  last_rcsme_reg_no: string | null
  existing_party_id: number | null
  existing_object_count: number
  will_create_party: boolean
  status: string
  warnings: string[]
  sample_rows: RegistrationBulkRow[]
}

export interface RegistrationListPreview {
  upload_id: string
  filename: string
  file_sha256: string
  sheet_name: string
  start_party_no: string
  case_year: number
  suggested_start_rcsme_reg_no: string
  previous_party_no: string | null
  previous_last_rcsme_reg_no: string | null
  party_count: number
  total_objects: number
  parties_to_create: number
  existing_parties: number
  conflicts: string[]
  warnings: string[]
  parties: RegistrationListPartyPreview[]
}

export interface RegistrationListCommitResponse {
  parties_created: number
  parties_updated: number
  objects_created: number
  objects_updated: number
  warnings: string[]
  parties: RegistrationListPartyPreview[]
}

export interface Employee {
  id: number
  full_name: string
  short_name: string | null
  initials: string | null
  role: string | null
  is_verified: boolean
  is_active: boolean
  stage_roles: Array<{ id: number; stage_type: string; role: string | null; is_active: boolean }>
}

export interface ReferenceItem {
  id: number
  category: string
  name: string
  short_name: string | null
  comment: string | null
  is_active: boolean
  created_at: string
  updated_at: string
}

export interface WorkSessionPreviewRequest {
  stage_type: string
  party_ids: number[]
  object_ids: number[]
  title?: string | null
  work_date?: string | null
  comment?: string | null
  detail_data: Record<string, unknown>
  performers: Array<{ raw_name?: string | null; role?: string | null; employee_id?: number | null }>
}

export interface WorkSessionPreview {
  object_count: number
  party_ids: number[]
  stage_type: string
  objects_with_existing_stage: number
  objects_without_stage: number
  next_attempt_min: number
  next_attempt_max: number
  sample_objects: RegistryObjectListItemBase[]
  warnings: string[]
}

export interface WorkSessionCommitResponse {
  session_id: number
  object_count: number
  stage_events_created: number
}

export interface StageTableColumn {
  key: string
  label: string
  type: string
  editable: boolean
  width: number
  input: string
  dictionary_category: string | null
}

export interface StageTableEvent {
  id: number
  stage_type: string
  attempt_no: number
  event_date: string | null
  source: string
  comment: string | null
  performers: string[]
}

export interface StageTableRow {
  object: RegistryObjectListItemBase
  values: Record<string, unknown>
  latest_event: StageTableEvent | null
  attempt_no: number | null
  repeat_count: number
  history_available: boolean
  history: StageTableEvent[]
}

export interface StageTable {
  stage_type: string
  party_ids: number[]
  columns: StageTableColumn[]
  rows: StageTableRow[]
  total: number
  filters: Record<string, unknown>
}

export interface StageTableQueryRequest {
  party_ids: number[]
  stage_type: string
  q?: string | null
  filters?: Record<string, unknown>
  include_archived?: boolean
  show_latest_only?: boolean
  show_history?: boolean
  limit?: number | null
  offset?: number
}

export interface StageEventsPreviewRequest {
  stage_type: string
  party_ids: number[]
  object_ids: number[]
  q?: string | null
  filters?: Record<string, unknown>
  title?: string | null
  work_date?: string | null
  comment?: string | null
  detail_data: Record<string, unknown>
  performers: Array<{ raw_name?: string | null; role?: string | null; employee_id?: number | null }>
  apply_mode?: 'append' | 'update_latest'
}

export interface StageEventsPreview {
  object_count: number
  stage_type: string
  objects_with_existing_stage: number
  objects_without_stage: number
  next_attempt_min: number
  next_attempt_max: number
  filled_fields: string[]
  warnings: string[]
  sample_rows: StageTableRow[]
}

export interface StageEventsApplyResponse {
  session_id: number
  object_count: number
  stage_events_created: number
  stage_events_updated: number
}

export interface StageEventsInlineApplyRequest {
  stage_type: string
  object_id: number
  detail_data: Record<string, unknown>
  performers: Array<{ raw_name?: string | null; role?: string | null; employee_id?: number | null }>
  comment?: string | null
  source?: string
}

export interface StageEventsInlineApplyResponse {
  event_id: number
  object_id: number
  stage_type: string
  attempt_no: number
}

export interface DashboardPartyProgress {
  id: number
  party_no: string
  case_year: number | null
  object_count: number
  stage_counts: Record<string, number>
  control_actual_decrees: string | null
  control_unidentified_rostov_no: string | null
  control_decree_without_object: string | null
  control_object_without_decree: string | null
  control_need_recall: string | null
  control_recalled: string | null
}

export interface Dashboard {
  total_objects: number
  active_parties: number
  archived_parties: number
  active_objects: number
  objects_without_events: number
  import_batches: number
  rt_unmatched: number
  electrophoresis_pdf_unmatched: number
  stage_summary: Record<string, number>
  active_party_progress: DashboardPartyProgress[]
  control_party_progress?: DashboardPartyProgress[]
  latest_imports: Array<{ id: number; filename: string; party_no: string | null; rows_imported: number; imported_at: string }>
}

export interface ReportStageProgress {
  done: number
  total: number
  percent: number
}

export interface ReportPartyRow {
  party_id: number
  party_no: string
  case_year: number | null
  object_count: number
  stage_counts: Record<string, number>
  stage_progress: Record<string, ReportStageProgress>
  control_problem_count: number
  control_status: string
  readiness_percent: number
  lagging_stage: string | null
  latest_change: string | null
  status: string
  repeat_stage_objects: number
  no_object_count: number
  no_decree_count: number
  no_biomaterial_count: number
  burnt_bone_count: number
}

export interface ReportOverview {
  kpis: Record<string, number>
  items: ReportPartyRow[]
  total: number
  page: number
  page_size: number
  quick_counts?: Record<string, number>
}

export interface PartyControlReportRow {
  party_id: number
  party_no: string
  case_year: number | null
  object_count: number
  control_actual_decrees: string | null
  control_decree_without_object: string | null
  control_object_without_decree: string | null
  control_unidentified_rostov_no: string | null
  control_need_recall: string | null
  control_recalled: string | null
  problem_count: number
  control_status: string
  latest_change: string | null
  status: string
  stage_counts: Record<string, number>
}

export interface PartyControlReport {
  items: PartyControlReportRow[]
  total: number
  page: number
  page_size: number
  quick_counts?: Record<string, number>
}

export interface PeriodStatisticsRow {
  period_key: string
  year: number | null
  week: number | null
  month: number | null
  new_parties: number
  new_objects: number
  stage_counts: Record<string, number>
  repeat_stage_events: number
  control_problems: number
}

export interface PeriodStatisticsReport {
  items: PeriodStatisticsRow[]
  total: number
  page: number
  page_size: number
}

export interface PerformerStatisticsRow {
  employee: string
  role: string
  stage_counts: Record<string, number>
  total_actions: number
}

export interface PerformerStatisticsReport {
  items: PerformerStatisticsRow[]
  total: number
  page: number
  page_size: number
}

export interface RegistryPreview {
  upload_id: string
  filename: string
  file_sha256: string
  party_no: string | null
  case_year: number | null
  sheet_name: string
  rows_detected: number
  rows_skipped: number
  sample_rows: RegistryObject[]
  warnings: string[]
  duplicates: Array<{ row_number: number; field: string; value: string; scope: string; party_no?: string | null; current_party_no?: string | null }>
  stage_event_counts: Record<string, number>
  party_control: Record<string, unknown>
  existing_objects_count: number
  new_objects_count: number
  replace_required_count: number
}

export interface CommitResponse {
  batch_id: number
  rows_total: number
  rows_imported: number
  rows_updated: number
  rows_skipped: number
  stage_events_written: number
  warnings: string[]
}

export interface RtPreview {
  upload_id: string
  filename: string
  file_sha256: string
  parser_type: string
  run_date: string | null
  quant_method: string | null
  columns: string[]
  sample_names: string[]
  sample_rows: Array<Record<string, unknown>>
  unmatched_samples: Array<Record<string, unknown>>
  warnings: string[]
  matched_count: number
  unmatched_count: number
  existing_rt_count: number
  existing_rt_samples: Array<Record<string, unknown>>
  repeat_samples: Array<Record<string, unknown>>
}

export interface RtCommitResponse {
  run_id: number
  results_written: number
  stage_events_written: number
  matched_count: number
  unmatched_count: number
  replaced_results: number
  replaced_stage_events: number
  warnings: string[]
}

export interface ElectrophoresisPdfPreviewItem {
  upload_id: string
  filename: string
  file_sha256: string
  samples: Array<Record<string, unknown>>
  matched_count: number
  unmatched_count: number
  existing_count: number
  control_count: number
  warnings: string[]
}

export interface ElectrophoresisPdfPreview {
  items: ElectrophoresisPdfPreviewItem[]
  matched_count: number
  unmatched_count: number
  existing_count: number
  control_count: number
}

export interface ElectrophoresisPdfCommitResponse {
  files_written: number
  matched_count: number
  unmatched_count: number
  files_replaced: number
  control_files_written: number
  control_files_replaced: number
  analysis_events_written: number
  warnings: string[]
}

export interface WorkProtocolStageBlock {
  stage_type: string
  title: string
  detail_data: Record<string, unknown>
  performers: Array<{ raw_name?: string | null; role?: string | null; employee_id?: number | null }>
}

export interface WorkProtocolObjectRow {
  sample_name_raw: string | null
  normalized_sample_name: string | null
  sample_object_no: string | null
  sample_base: string | null
  repeat_suffix: string | null
  well: string | null
  matched: boolean
  object_id: number | null
  object_rcsme_reg_no: string | null
  object_decree_no: string | null
  party_id: number | null
  party_no: string | null
  is_repeat_sample: boolean
  repeat_object_exists: boolean
  parent_object_id: number | null
  parent_rcsme_reg_no: string | null
}

export interface WorkProtocolPlateCell {
  sample_name_raw: string | null
  normalized_sample_name: string | null
  sample_object_no: string | null
  sample_base: string | null
  repeat_suffix: string | null
  well: string | null
  is_service: boolean
}

export interface WorkProtocolPreview {
  upload_id: string
  filename: string
  file_sha256: string
  protocol_title: string | null
  protocol_no: string | null
  protocol_name: string | null
  objects: WorkProtocolObjectRow[]
  plate_cells?: WorkProtocolPlateCell[]
  stage_blocks: WorkProtocolStageBlock[]
  matched_count: number
  unmatched_count: number
  repeat_count: number
  warnings: string[]
}

export interface RcsmeFixPreview {
  total: number
  conflicts: number
  sample_rows: Array<{
    id: number
    party_no: string | null
    decree_no: string | null
    current_rcsme_reg_no: string
    suggested_rcsme_reg_no: string
  }>
}

export interface RcsmeFixApplyResponse {
  fixed: number
  skipped: number
  conflicts: number
}
