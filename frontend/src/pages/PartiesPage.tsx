import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Archive, BarChart3, Check, ChevronDown, ChevronRight, ClipboardList, Columns3, Copy, Eye, FileDown, Filter, History, Plus, Printer, Save, Search, X } from 'lucide-react'
import { useEffect, useMemo, useRef, useState } from 'react'
import { api } from '../api/client'
import type { Employee, Party, ReferenceItem, RegistrationBulkRequest, RegistrationBulkRow, RegistryObject, StageTable, StageTableColumn, StageTableEvent, StageTableRow, User } from '../api/types'
import { useDebouncedValue } from '../hooks/useDebouncedValue'

const stageTabs = [
  ['registration', 'Регистрация'],
  ['preparation', 'Пробоподготовка'],
  ['milling', 'Измельчение'],
  ['extraction', 'Выделение'],
  ['realtime', 'RealTime'],
  ['pcr', 'ПЦР'],
  ['electrophoresis', 'Электрофорез'],
  ['analysis', 'Анализ'],
  ['all', 'Все этапы']
] as const

const printableStageTabs = stageTabs.filter(([key]) => key !== 'all')

const stageLabels: Record<string, string> = {
  sample_prep: 'Пробоподготовка',
  preparation: 'Пробоподготовка',
  milling: 'Измельчение',
  dna_extraction: 'Выделение',
  extraction: 'Выделение',
  realtime: 'RealTime',
  pcr: 'ПЦР',
  electrophoresis: 'Электрофорез',
  analysis: 'Анализ',
  registration: 'Регистрация',
  all: 'Все этапы'
}

const progressStageOrder = [
  'registration',
  'sample_prep',
  'preparation',
  'milling',
  'dna_extraction',
  'extraction',
  'realtime',
  'pcr',
  'electrophoresis',
  'analysis'
]

function orderedStageCounts(stageCounts: Record<string, number>) {
  const used = new Set<string>()
  const ordered = progressStageOrder.flatMap((stage) => {
    if (!(stage in stageCounts) || used.has(stage)) return []
    used.add(stage)
    return [[stage, stageCounts[stage]] as const]
  })
  const rest = Object.entries(stageCounts)
    .filter(([stage]) => !used.has(stage))
    .sort(([left], [right]) => left.localeCompare(right))
  return [...ordered, ...rest]
}

const sourceLabels: Record<string, string> = {
  registry_excel: 'импортировано из Excel',
  manual: 'внесено вручную',
  rt_import: 'импорт RT',
  legacy: 'старые данные'
}

const statusLabels: Record<string, string> = {
  new: 'новый',
  active: 'активна',
  archived: 'архив',
  draft: 'черновик',
  applied: 'применено',
  cancelled: 'отменено'
}

const quickFilters = [
  ['', 'Все'],
  ['empty', 'Пустые'],
  ['filled', 'Заполненные'],
  ['repeat', 'Есть повтор']
] as const

type StageFieldConfig = { key: string; label: string; type?: string; performerRole?: string }

async function copyTextToClipboard(text: string) {
  if (!text) return false
  try {
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(text)
      return true
    }
  } catch {
    // Some browsers expose Clipboard API but block it outside trusted contexts.
  }

  const textarea = document.createElement('textarea')
  textarea.value = text
  textarea.setAttribute('readonly', '')
  textarea.style.position = 'fixed'
  textarea.style.left = '-9999px'
  textarea.style.top = '0'
  textarea.style.opacity = '0'
  document.body.appendChild(textarea)
  textarea.focus()
  textarea.select()
  try {
    return document.execCommand('copy')
  } catch {
    return false
  } finally {
    document.body.removeChild(textarea)
  }
}

const stageFieldConfigs: Record<string, StageFieldConfig[]> = {
  preparation: [
    { key: 'registry_filled_by', label: 'Заполнение реестра' },
    { key: 'photo_performers', label: 'Фотофиксация', performerRole: 'photo' },
    { key: 'photo_assistants', label: 'Помощь в фотофиксации', performerRole: 'photo_assistant' },
    { key: 'washing_performers', label: 'Отмывка', performerRole: 'washing' },
    { key: 'washing_assistants', label: 'Помощь в отмывке', performerRole: 'washing_assistant' },
    { key: 'washing_date', label: 'Дата отмывки', type: 'date' },
    { key: 'bone_tissue_performers', label: 'Размельчение / изъятие тканей', performerRole: 'bone_tissue' },
    { key: 'bone_tissue_date', label: 'Дата размельчения / изъятия', type: 'date' }
  ],
  milling: [
    { key: 'milling_performers', label: 'Размельчение на мельнице', performerRole: 'milling' },
    { key: 'cups', label: 'Стаканы', performerRole: 'cups' },
    { key: 'milling_date', label: 'Дата', type: 'date' }
  ],
  extraction: [
    { key: 'extraction_date', label: 'Дата получения препарата ДНК', type: 'date' },
    { key: 'extraction_performers', label: 'Исполнитель', performerRole: 'dna_extraction' },
    { key: 'extraction_method', label: 'Метод' }
  ],
  realtime: [
    { key: 'quant_method', label: 'Метод измерения концентрации' },
    { key: 'quant_date', label: 'Дата измерения', type: 'date' },
    { key: 'quant_performer', label: 'Исполнитель', performerRole: 'quant' },
    { key: 'pipetting_method', label: 'Робот / ручной / NA' }
  ],
  pcr: [
    { key: 'pcr_date', label: 'Дата PCR', type: 'date' },
    { key: 'locus_panel', label: 'Панель локусов' },
    { key: 'pipetting_method', label: 'Робот / ручной' },
    { key: 'normalization_performers', label: 'Нормализация PCR', performerRole: 'normalization' },
    { key: 'pcr_performers', label: 'Постановка PCR', performerRole: 'pcr' }
  ],
  electrophoresis: [
    { key: 'electrophoresis_date', label: 'Дата электрофореза', type: 'date' },
    { key: 'sequencer', label: 'Секвенатор' },
    { key: 'pipetting_method', label: 'Робот / ручной' },
    { key: 'performer_1', label: 'Исполнитель 1', performerRole: 'performer_1' },
    { key: 'performer_2', label: 'Исполнитель 2', performerRole: 'performer_2' },
    { key: 'extra_performers', label: 'Дополнительные исполнители', performerRole: 'extra' }
  ],
  analysis: [
    { key: 'genotype', label: 'Генотип' },
    { key: 'analysis_date', label: 'Дата анализа', type: 'date' },
    { key: 'analysis_performers', label: 'Исполнитель', performerRole: 'analysis' },
    { key: 'analysis_status', label: 'Статус анализа' }
  ]
}

const registrationEditable = new Set([
  'registry_row_no',
  'rcsme_reg_no',
  'decree_no',
  'external_military_no',
  'intake_date',
  'decision_date',
  'investigator',
  'incoming_no',
  'box_no',
  'packages_count',
  'object_type',
  'extracted_before',
  'not_extracted_before',
  'object_description'
])
const realtimeQuantityKeys = new Set(['long_quantity', 'small_quantity', 'y_quantity'])

const objectPatchKeys = new Set(['object_description'])

type DraftValue = string | number | string[] | null
type DraftMap = Record<string, Record<string, DraftValue>>
type HiddenColumnState = Record<string, string[]>
type ColumnFilterState = Record<string, string[]>
type RegistrationActiveState = Record<string, number[]>
type RegistrationFillForm = {
  start_rcsme_reg_no: string
  count: string
  update_existing: boolean
  intake_date: string
  decision_date: string
  investigator: string
  incoming_no: string
  box_no: string
}
type ObjectListMatch = {
  foundIds: number[]
  missing: string[]
  duplicates: string[]
  blocked: string[]
  sourceCount: number
}

function canonicalStageKey(stage: string) {
  return stage === 'preparation' ? 'sample_prep' : stage === 'extraction' ? 'dna_extraction' : stage
}

const actionsColumnKey = '__actions'
const registrationActiveColumnKey = '__registration_active'
const actionsColumn: StageTableColumn = {
  key: actionsColumnKey,
  label: 'Действия',
  type: 'text',
  editable: false,
  width: 130,
  input: 'text',
  dictionary_category: null
}
const registrationActiveColumn: StageTableColumn = {
  key: registrationActiveColumnKey,
  label: 'Активно',
  type: 'boolean',
  editable: false,
  width: 88,
  input: 'text',
  dictionary_category: null
}

function hiddenColumnsKey(username: string) {
  return `dna_registry.hidden_columns.v4.${username}`
}

function registrationActiveChecksKey(username: string) {
  return `dna_registry.registration_active_checks.v1.${username}`
}

function loadHiddenColumns(username: string): HiddenColumnState {
  if (typeof window === 'undefined') return {}
  try {
    const raw = window.localStorage.getItem(hiddenColumnsKey(username))
    if (!raw) return {}
    const parsed = JSON.parse(raw) as unknown
    if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) return {}
    return Object.fromEntries(
      Object.entries(parsed).filter(([, value]) => Array.isArray(value)).map(([key, value]) => [key, (value as unknown[]).map(String)])
    )
  } catch {
    return {}
  }
}

function saveHiddenColumns(username: string, state: HiddenColumnState) {
  if (typeof window === 'undefined') return
  try {
    window.localStorage.setItem(hiddenColumnsKey(username), JSON.stringify(state))
  } catch {
    // localStorage can be unavailable in private mode; column visibility remains session-only.
  }
}

function loadRegistrationActiveChecks(username: string): RegistrationActiveState {
  if (typeof window === 'undefined') return {}
  try {
    const raw = window.localStorage.getItem(registrationActiveChecksKey(username))
    if (!raw) return {}
    const parsed = JSON.parse(raw) as unknown
    if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) return {}
    return Object.fromEntries(
      Object.entries(parsed)
        .filter(([, value]) => Array.isArray(value))
        .map(([key, value]) => [key, (value as unknown[]).map(Number).filter((id) => Number.isFinite(id))])
    )
  } catch {
    return {}
  }
}

function saveRegistrationActiveChecks(username: string, state: RegistrationActiveState) {
  if (typeof window === 'undefined') return
  try {
    window.localStorage.setItem(registrationActiveChecksKey(username), JSON.stringify(state))
  } catch {
    // This checklist is a browser convenience only; it can safely remain session-only.
  }
}

function defaultHiddenColumns(stage: string) {
  const hidden = [actionsColumnKey]
  if (stage === 'registration' || stage === 'all') return hidden
  hidden.push('decree_no', 'object_type', 'box_no')
  if (stage === 'analysis') hidden.push('genotype', 'attempt_no')
  return hidden
}

function orderVisibleColumns(stage: string, columns: StageTableColumn[]) {
  const anchorKeys = stage === 'preparation'
    ? ['object_description', 'burnt_bone', 'no_biomaterial', 'external_military_no', 'comment', 'no_object', 'no_decree']
    : stage === 'registration'
      ? ['external_military_no', registrationActiveColumnKey, 'no_object', 'no_decree', 'burnt_bone']
      : ['no_object', 'no_decree', 'burnt_bone']
  const anchorColumns = anchorKeys
    .map((key) => columns.find((column) => column.key === key))
    .filter((column): column is StageTableColumn => Boolean(column))
  if (!anchorColumns.length) return columns
  const rest = columns.filter((column) => !anchorKeys.includes(column.key))
  const insertAfterIndex = rest.findIndex((column) => column.key === 'rcsme_reg_no')
  const insertAt = insertAfterIndex >= 0 ? insertAfterIndex + 1 : Math.min(1, rest.length)
  return [...rest.slice(0, insertAt), ...anchorColumns, ...rest.slice(insertAt)]
}

function withRegistrationActiveColumn(stage: string, columns: StageTableColumn[]) {
  if (stage !== 'registration' || columns.some((column) => column.key === registrationActiveColumnKey)) return columns
  const externalIndex = columns.findIndex((column) => column.key === 'external_military_no')
  const insertAt = externalIndex >= 0 ? externalIndex + 1 : Math.min(2, columns.length)
  return [...columns.slice(0, insertAt), registrationActiveColumn, ...columns.slice(insertAt)]
}

function fieldConfig(stage: string, key: string) {
  return (stageFieldConfigs[stage] || []).find((field) => field.key === key)
}

function isStageEditable(activeStage: string, column: StageTableColumn) {
  if (!column.editable) return false
  if (activeStage === 'registration') return registrationEditable.has(column.key)
  if (activeStage === 'realtime' && realtimeQuantityKeys.has(column.key)) return false
  if (column.key === 'comment') return activeStage !== 'all'
  if (activeStage === 'preparation' && column.key === 'object_description') return true
  return activeStage !== 'all' && Boolean(fieldConfig(activeStage, column.key))
}

function display(value: unknown) {
  if (value === null || value === undefined || value === '') return '—'
  if (Array.isArray(value)) return value.filter(Boolean).join(', ') || '—'
  return String(value)
}

function formatDate(value: unknown) {
  if (!value || typeof value !== 'string') return display(value)
  const match = /^(\d{4})-(\d{2})-(\d{2})/.exec(value)
  if (!match) return value
  return `${match[3]}-${match[2]}-${match[1]}`
}

function formatCell(value: unknown, column?: StageTableColumn) {
  if (column?.key === 'no_object' || column?.key === 'no_decree' || column?.key === 'burnt_bone' || column?.key === 'no_biomaterial' || column?.key === registrationActiveColumnKey) return value === true ? 'Да' : '—'
  if (column && realtimeQuantityKeys.has(column.key) && value === 'n/a') return 'n/a'
  if (column?.type === 'date') return formatDate(value)
  if (column?.key === 'source' && typeof value === 'string') return sourceLabels[value] || value
  if (column && ['long_quantity', 'small_quantity', 'y_quantity'].includes(column.key) && typeof value === 'number') return value.toFixed(4)
  return display(value)
}

function isControlRow(row: StageTableRow) {
  return row.values.is_control_row === true || row.object.id < 0
}

function isNoObjectRow(row: StageTableRow) {
  return row.values.no_object === true
}

function isBlockedNoObjectStageRow(activeStage: string, row: StageTableRow) {
  return activeStage !== 'registration' && activeStage !== 'all' && isNoObjectRow(row)
}

function isRepeatObjectRow(row: StageTableRow) {
  return row.values.is_repeat === true || Boolean(row.object.parent_object_id || row.object.repeat_suffix)
}

function objectRepeatCount(row: StageTableRow) {
  const value = row.values.object_repeat_count
  if (typeof value === 'number') return value
  if (typeof value === 'string') {
    const parsed = Number(value)
    return Number.isFinite(parsed) ? parsed : 0
  }
  return 0
}

function isStageAttemptRepeatRow(row: StageTableRow) {
  return row.values.is_stage_attempt_repeat === true
}

function stageAttemptCount(row: StageTableRow) {
  const value = row.values.stage_attempt_count
  if (typeof value === 'number') return value
  if (typeof value === 'string') {
    const parsed = Number(value)
    return Number.isFinite(parsed) ? parsed : 0
  }
  return 0
}

function stageRowKey(row: StageTableRow) {
  const key = row.values.stage_attempt_key
  return typeof key === 'string' && key ? key : String(row.object.id)
}

function objectIdFromDraftKey(key: string) {
  return Number(key.split(':')[0])
}

function normalizeObjectNo(value: string) {
  return value
    .trim()
    .replace(/[–—−]/g, '-')
    .replace(/\s+/g, '')
    .replace(/([0-9]+-[0-9]+)[A-Za-zА-Яа-яЁё]+$/, '$1')
    .toLowerCase()
}

function parseObjectNoList(value: string) {
  return value
    .split(/[\s,;]+/)
    .map((item) => item.trim())
    .filter(Boolean)
}

function normalizeControlNo(value: unknown) {
  return String(value || '').trim().toLocaleLowerCase('ru-RU')
}

function splitControlNumbers(value: string | null | undefined) {
  return String(value || '')
    .replace(/\r/g, '\n')
    .replace(/;/g, ',')
    .split(/[,\n\t]+/)
    .map((item) => item.trim())
    .filter(Boolean)
}

function joinControlNumbers(values: string[]) {
  const seen = new Set<string>()
  const unique: string[] = []
  for (const value of values) {
    const trimmed = value.trim()
    const normalized = normalizeControlNo(trimmed)
    if (!trimmed || seen.has(normalized)) continue
    seen.add(normalized)
    unique.push(trimmed)
  }
  return unique.join(', ')
}

function controlTokenBase(value: unknown) {
  return normalizeControlNo(String(value || '').replace(/\s*(?:\[[^\]]+\]|\([^)]+\))\s*$/, ''))
}

function rowExternalMilitaryNo(row: StageTableRow) {
  return String(row.values.external_military_no || row.object.external_military_no || '').trim()
}

function rowRcsmeNo(row: StageTableRow) {
  return String(row.values.rcsme_reg_no || row.object.rcsme_reg_no || '').trim()
}

function controlTokenForRow(row: StageTableRow, precise: boolean) {
  const externalMilitaryNo = rowExternalMilitaryNo(row)
  if (!externalMilitaryNo) return ''
  if (!precise) return externalMilitaryNo
  return `${externalMilitaryNo} [${rowRcsmeNo(row) || `#${row.object.id}`}]`
}

function controlSetHasRow(tokens: Set<string>, row: StageTableRow, preciseOnly = false) {
  const externalMilitaryNo = rowExternalMilitaryNo(row)
  if (!externalMilitaryNo) return false
  const external = normalizeControlNo(externalMilitaryNo)
  const regNo = normalizeControlNo(rowRcsmeNo(row))
  const objectId = `#${row.object.id}`
  for (const token of tokens) {
    if (controlTokenBase(token) !== external) continue
    if (token === external) return !preciseOnly
    if ((regNo && token.includes(regNo)) || token.includes(objectId)) return true
  }
  return false
}

function columnFilterValue(row: StageTableRow, column: StageTableColumn) {
  return formatCell(row.values[column.key], column)
}

function applyColumnFilters(rows: StageTableRow[], columns: StageTableColumn[], filters: ColumnFilterState) {
  const active = Object.entries(filters)
  if (!active.length) return rows
  const columnMap = new Map(columns.map((column) => [column.key, column]))
  return rows.filter((row) =>
    active.every(([key, allowed]) => {
      const column = columnMap.get(key)
      if (!column) return true
      return allowed.includes(columnFilterValue(row, column))
    })
  )
}

function printableColumns(stage: string, columns: StageTableColumn[]) {
  return orderVisibleColumns(stage, columns.filter((column) => column.key !== actionsColumnKey))
}

function printRowsForObjects(rows: StageTableRow[], objectIds: number[]) {
  const selected = new Set(objectIds)
  return rows.filter((row) => !isControlRow(row) && selected.has(row.object.id))
}

function objectWord(count: number) {
  const mod10 = count % 10
  const mod100 = count % 100
  if (mod10 === 1 && mod100 !== 11) return 'объект'
  if (mod10 >= 2 && mod10 <= 4 && (mod100 < 12 || mod100 > 14)) return 'объекта'
  return 'объектов'
}

const partyControlFields = [
  ['control_actual_decrees', 'Фактическое количество постановлений'],
  ['control_decree_without_object', 'Есть постановление, но нет объекта'],
  ['control_object_without_decree', 'Есть объект, но нет постановления'],
  ['control_unidentified_rostov_no', 'Неидентифицируемый ростовский номер'],
  ['control_need_recall', 'Надо отозвать'],
  ['control_recalled', 'Отозваны']
] as const

type PartyControlKey = (typeof partyControlFields)[number][0]
type PartyControlDraft = Record<PartyControlKey, string>
type ControlToggleVariables = {
  partyId: number
  payload: Partial<Party>
  nextDraft: PartyControlDraft
  previousDraft: PartyControlDraft
}

function partyControlDraft(party: Party | null | undefined): PartyControlDraft {
  return Object.fromEntries(
    partyControlFields.map(([key]) => [key, String(party?.[key] || '')])
  ) as PartyControlDraft
}

function controlDraftWithToggle(
  draft: PartyControlDraft,
  key: PartyControlKey,
  row: StageTableRow,
  checked: boolean,
  precise: boolean
) {
  const token = controlTokenForRow(row, precise)
  const normalized = normalizeControlNo(token)
  const current = splitControlNumbers(draft[key])
  const next = checked
    ? [...current, token]
    : current.filter((item) => normalizeControlNo(item) !== normalized)
  return {
    ...draft,
    [key]: joinControlNumbers(next)
  }
}

function headerLines(label: string) {
  if (label.length < 24) return [label]
  return label.split(/ (?=[^ ]+$)/)
}

function columnLabel(column: StageTableColumn) {
  if (column.key === 'external_military_no') return '№ в в/ч №522'
  return column.label
}

function clampWidth(value: number, min: number, max: number) {
  return Math.max(min, Math.min(max, value))
}

function stageColumnTrack(column: StageTableColumn) {
  if (column.key === 'attempt_no') return '78px'
  if (column.key === 'registry_row_no') return '70px'
  if (column.key === 'rcsme_reg_no') return '158px'
  if (column.key === registrationActiveColumnKey) return '88px'
  if (column.key === 'no_object') return '96px'
  if (column.key === 'no_decree') return '120px'
  if (column.key === 'burnt_bone') return '120px'
  if (column.key === 'no_biomaterial') return '140px'
  if (column.key === 'analysis_pdf') return '190px'
  if (column.key === 'decree_no') return '142px'
  if (column.key === 'external_military_no') return '130px'
  if (column.key === 'box_no') return '78px'
  if (column.key === 'incoming_no') return '88px'
  if (column.key === 'packages_count') return '124px'
  if (column.key === 'object_type') return '150px'
  if (column.type === 'date') return '138px'
  if (column.type === 'number') return '96px'
  if (column.input === 'employee_multi') return `${clampWidth(column.width, 170, 220)}px`
  if (column.input === 'employee') return `${clampWidth(column.width, 150, 200)}px`
  if (column.input === 'dictionary') return `${clampWidth(column.width, 145, 190)}px`
  if (column.key === 'object_description') return '250px'
  if (column.key === 'comment') return '210px'
  return `${clampWidth(column.width, 90, 220)}px`
}

function patchValue(value: string, column: StageTableColumn) {
  if (value === '') return null
  if (column.type === 'number') {
    const parsed = Number(value)
    return Number.isFinite(parsed) ? parsed : value
  }
  return value
}

function listValue(value: unknown) {
  if (Array.isArray(value)) return value.map(String)
  if (typeof value === 'string') return value.split(/[,/]/).map((item) => item.trim()).filter(Boolean)
  return []
}

function employeeName(employee: Employee) {
  return employee.short_name || employee.initials || employee.full_name
}

function employeesForStage(employees: Employee[], activeStage: string) {
  if (activeStage === 'registration' || activeStage === 'all') return employees.filter((employee) => employee.is_active)
  const stage = canonicalStageKey(activeStage)
  const active = employees.filter((employee) => employee.is_active)
  const matched = active.filter((employee) => {
    const roles = employee.stage_roles || []
    if (!roles.length) return true
    return roles.some((item) => item.is_active && (item.stage_type === activeStage || item.stage_type === stage))
  })
  return matched.length ? matched : active
}

function dictionaryOptions(items: ReferenceItem[], column: StageTableColumn) {
  if (!column.dictionary_category) return []
  return items.filter((item) => item.category === column.dictionary_category && item.is_active)
}

function valueSummary(value: unknown) {
  const values = listValue(value)
  if (!values.length) return '—'
  if (values.length <= 2) return values.join(', ')
  return `${values.slice(0, 2).join(', ')} +${values.length - 2}`
}

function stagePayloadFromValues(activeStage: string, values: Record<string, DraftValue>) {
  const detail_data: Record<string, unknown> = {}
  const performers: Array<{ raw_name?: string | null; role?: string | null; employee_id?: number | null }> = []
  const electrophoresisPerformers: string[] = []
  for (const [key, value] of Object.entries(values)) {
    const config = fieldConfig(activeStage, key)
    if (!config) continue
    if (!config.performerRole) {
      detail_data[key] = value
      continue
    }
    const names = Array.isArray(value) ? value.map(String).filter(Boolean) : (value ? [String(value)] : [])
    performers.push(...names.map((raw_name) => ({ raw_name, role: config.performerRole })))
    if (activeStage === 'preparation' || activeStage === 'milling' || activeStage === 'pcr') {
      detail_data[key] = names
    } else if (activeStage === 'realtime' && key === 'quant_performer') {
      detail_data[key] = names[0] || null
    } else if (activeStage === 'extraction' && key === 'extraction_performers') {
      detail_data[key] = names
    } else if (activeStage === 'analysis' && key === 'analysis_performers') {
      detail_data[key] = names
    } else if (activeStage === 'electrophoresis') {
      electrophoresisPerformers.push(...names)
    }
  }
  const electrophoresisPerformerTouched = activeStage === 'electrophoresis'
    && Object.keys(values).some((key) => Boolean(fieldConfig(activeStage, key)?.performerRole))
  if (activeStage === 'electrophoresis' && electrophoresisPerformerTouched) {
    detail_data.performers = electrophoresisPerformers
  }
  return { detail_data, performers }
}

function StageGrid({
  columns,
  rows,
  allRows,
  columnFilters,
  selectedIds,
  drafts,
  employees,
  referenceItems,
  canEdit,
  activeStage,
  showActionsColumn,
  registrationNoObjectNumbers,
  registrationNoDecreeNumbers,
  registrationActiveIds,
  onToggle,
  onToggleAll,
  onDraft,
  onOpen,
  onHistory,
  onColumnFilter,
  onToggleNoObjectControl,
  onToggleNoDecreeControl,
  onToggleBurntBone,
  onToggleNoBiomaterial,
  onToggleRegistrationActive
}: {
  columns: StageTableColumn[]
  rows: StageTableRow[]
  allRows: StageTableRow[]
  columnFilters: ColumnFilterState
  selectedIds: Set<number>
  drafts: DraftMap
  employees: Employee[]
  referenceItems: ReferenceItem[]
  canEdit: boolean
  activeStage: string
  showActionsColumn: boolean
  registrationNoObjectNumbers: Set<string>
  registrationNoDecreeNumbers: Set<string>
  registrationActiveIds: Set<number>
  onToggle: (id: number) => void
  onToggleAll: () => void
  onDraft: (id: string, key: string, value: DraftValue) => void
  onOpen: (id: number) => void
  onHistory: (row: StageTableRow) => void
  onColumnFilter: (key: string, values: string[] | null) => void
  onToggleNoObjectControl: (row: StageTableRow, checked: boolean) => void
  onToggleNoDecreeControl: (row: StageTableRow, checked: boolean) => void
  onToggleBurntBone: (row: StageTableRow, checked: boolean) => void
  onToggleNoBiomaterial: (row: StageTableRow, checked: boolean) => void
  onToggleRegistrationActive: (row: StageTableRow, checked: boolean) => void
}) {
  const [multiPicker, setMultiPicker] = useState<{ rowId: string; column: StageTableColumn; value: string[] } | null>(null)
  const [filterColumn, setFilterColumn] = useState<StageTableColumn | null>(null)
  const [filterSearch, setFilterSearch] = useState('')
  const [filterDraft, setFilterDraft] = useState<string[]>([])
  const stageEmployees = useMemo(() => employeesForStage(employees, activeStage), [activeStage, employees])
  const gridTemplateColumns = `44px ${columns.map(stageColumnTrack).join(' ')}${showActionsColumn ? ' 130px' : ''}`
  const rowStyle = { gridTemplateColumns }
  const stickyLeftByKey = useMemo(() => {
    const stickyKeys = new Set(['registry_row_no', 'rcsme_reg_no', 'external_military_no'])
    const result: Record<string, number> = {}
    let left = 44
    let contiguous = true
    for (const column of columns) {
      if (!contiguous || !stickyKeys.has(column.key)) {
        contiguous = false
        continue
      }
      result[column.key] = left
      left += Number.parseInt(stageColumnTrack(column), 10) || 0
    }
    return result
  }, [columns])
  function stickyCellClass(column: StageTableColumn) {
    const left = stickyLeftByKey[column.key]
    return left === undefined ? '' : 'stage-sticky-cell'
  }
  function stickyCellStyle(column: StageTableColumn) {
    const left = stickyLeftByKey[column.key]
    return left === undefined ? undefined : { left }
  }
  const filterValues = useMemo(() => {
    if (!filterColumn) return []
    return Array.from(new Set(allRows.map((row) => columnFilterValue(row, filterColumn)))).sort((a, b) => a.localeCompare(b, 'ru'))
  }, [allRows, filterColumn])
  const visibleFilterValues = useMemo(() => {
    const needle = filterSearch.trim().toLowerCase()
    return needle ? filterValues.filter((value) => value.toLowerCase().includes(needle)) : filterValues
  }, [filterSearch, filterValues])
  const externalMilitaryCounts = useMemo(() => {
    const counts = new Map<string, number>()
    for (const row of allRows) {
      const normalized = normalizeControlNo(rowExternalMilitaryNo(row))
      if (!normalized) continue
      counts.set(normalized, (counts.get(normalized) || 0) + 1)
    }
    return counts
  }, [allRows])
  const selectableRows = rows.filter((row) => !isControlRow(row) && !isBlockedNoObjectStageRow(activeStage, row))
  function openFilter(column: StageTableColumn) {
    const values = Array.from(new Set(allRows.map((row) => columnFilterValue(row, column)))).sort((a, b) => a.localeCompare(b, 'ru'))
    setFilterColumn(column)
    setFilterSearch('')
    setFilterDraft(columnFilters[column.key] || values)
  }
  if (!rows.length) return <div className="empty">Объекты не найдены</div>
  return (
    <div className="stage-grid-wrap">
      <div className="stage-grid" role="table" style={{ gridTemplateColumns }}>
        <div className="stage-grid-row stage-grid-head" role="row" style={rowStyle}>
          <div className="stage-sticky-cell stage-select-sticky" style={{ left: 0 }} role="columnheader">
            <input
              type="checkbox"
              checked={selectableRows.length > 0 && selectableRows.every((row) => selectedIds.has(row.object.id))}
              disabled={!selectableRows.length}
              onChange={onToggleAll}
              aria-label="Выбрать все строки"
            />
          </div>
          {columns.map((column) => (
            <div className={stickyCellClass(column)} style={stickyCellStyle(column)} role="columnheader" key={column.key}>
              <button
                type="button"
                className={`stage-filter-button ${Object.prototype.hasOwnProperty.call(columnFilters, column.key) ? 'active' : ''}`}
                onClick={() => openFilter(column)}
                title={`Фильтр: ${columnLabel(column)}`}
              >
                <span>{headerLines(columnLabel(column)).map((line) => <span key={line}>{line}</span>)}</span>
                <Filter size={13} />
              </button>
            </div>
          ))}
          {showActionsColumn && <div role="columnheader">Действия</div>}
        </div>
        {rows.map((row) => {
          const rowKey = stageRowKey(row)
          const draft = drafts[rowKey] || {}
          const repeatCount = objectRepeatCount(row)
          const repeatRow = isRepeatObjectRow(row)
          const stageAttemptRepeatRow = isStageAttemptRepeatRow(row)
          const analysisCount = stageAttemptCount(row)
          const controlRow = isControlRow(row)
          const blockedNoObjectRow = isBlockedNoObjectStageRow(activeStage, row)
          const externalMilitaryNo = rowExternalMilitaryNo(row)
          const requiresPreciseControl = (externalMilitaryCounts.get(normalizeControlNo(externalMilitaryNo)) || 0) > 1
          const noObjectControlChecked = externalMilitaryNo ? controlSetHasRow(registrationNoObjectNumbers, row, requiresPreciseControl) : false
          const noDecreeControlChecked = externalMilitaryNo ? controlSetHasRow(registrationNoDecreeNumbers, row, requiresPreciseControl) : false
          return (
            <div
              className={`stage-grid-row stage-grid-body-row${isNoObjectRow(row) || noObjectControlChecked ? ' no-object-row' : ''}${repeatRow ? ' repeat-object-row' : ''}${stageAttemptRepeatRow ? ' stage-attempt-repeat-row' : ''}${controlRow ? ' control-row' : ''}`}
              role="row"
              key={rowKey}
              style={rowStyle}
            >
              <div className="stage-sticky-cell stage-select-sticky" style={{ left: 0 }} role="cell">
                <input
                  type="checkbox"
                  checked={!controlRow && !blockedNoObjectRow && selectedIds.has(row.object.id)}
                  onChange={() => { if (!controlRow && !blockedNoObjectRow) onToggle(row.object.id) }}
                  disabled={controlRow || blockedNoObjectRow}
                  title={blockedNoObjectRow ? 'Объект помечен как «Нет объекта»' : undefined}
                  aria-label={`Выбрать ${row.object.rcsme_reg_no || row.object.id}`}
                />
              </div>
              {columns.map((column) => {
                const draftValue = draft[column.key]
                const hasDraft = Object.prototype.hasOwnProperty.call(draft, column.key)
                const value = hasDraft ? draftValue : row.values[column.key]
                const editable = !controlRow && !blockedNoObjectRow && canEdit && isStageEditable(activeStage, column)
                const registrationActiveChecked = registrationActiveIds.has(row.object.id)
                return (
                  <div
                    style={stickyCellStyle(column)}
                    className={`${stickyCellClass(column)}${hasDraft ? ' dirty-cell' : ''}${activeStage === 'realtime' && realtimeQuantityKeys.has(column.key) && value === 'n/a' ? ' rt-na-cell' : ''}${activeStage === 'registration' && column.key === 'external_military_no' && registrationActiveChecked ? ' registration-active-number-cell' : ''}`}
                    role="cell"
                    key={column.key}
                  >
                    {activeStage === 'registration' && column.key === 'no_object' ? (
                      <label
                        className="no-object-checkbox"
                        title={externalMilitaryNo ? `Добавить/убрать ${externalMilitaryNo} в контроле партии` : 'Нет значения № в в/ч №522'}
                      >
                        <input
                          type="checkbox"
                          checked={noObjectControlChecked}
                          disabled={!canEdit || !externalMilitaryNo}
                          onChange={(event) => onToggleNoObjectControl(row, event.target.checked)}
                        />
                      </label>
                    ) : activeStage === 'registration' && column.key === 'no_decree' ? (
                      <label
                        className="no-object-checkbox"
                        title={externalMilitaryNo ? `Добавить/убрать ${externalMilitaryNo} в контроле партии` : 'Нет значения № в в/ч №522'}
                      >
                        <input
                          type="checkbox"
                          checked={noDecreeControlChecked}
                          disabled={!canEdit || !externalMilitaryNo}
                          onChange={(event) => onToggleNoDecreeControl(row, event.target.checked)}
                        />
                      </label>
                    ) : activeStage === 'preparation' && column.key === 'burnt_bone' ? (
                      <label
                        className="no-object-checkbox"
                        title="Изменить описание объекта: кость / горелая кость"
                      >
                        <input
                          type="checkbox"
                          checked={value === true}
                          disabled={!canEdit || controlRow || blockedNoObjectRow}
                          onChange={(event) => onToggleBurntBone(row, event.target.checked)}
                        />
                      </label>
                    ) : activeStage === 'preparation' && column.key === 'no_biomaterial' ? (
                      <label
                        className="no-object-checkbox"
                        title="Изменить описание объекта: кость / Нет биоматериала"
                      >
                        <input
                          type="checkbox"
                          checked={value === true}
                          disabled={!canEdit || controlRow || (blockedNoObjectRow && value !== true)}
                          onChange={(event) => onToggleNoBiomaterial(row, event.target.checked)}
                        />
                      </label>
                    ) : activeStage === 'registration' && column.key === registrationActiveColumnKey ? (
                      <label
                        className="no-object-checkbox"
                        title="Отметить номер как проверенный вручную"
                      >
                        <input
                          type="checkbox"
                          checked={registrationActiveChecked}
                          disabled={!canEdit || controlRow}
                          onChange={(event) => onToggleRegistrationActive(row, event.target.checked)}
                        />
                      </label>
                    ) : editable && column.key === 'rcsme_reg_no' ? (
                      <span className={`object-number-cell editable-number${repeatRow ? ' repeat' : ''}`}>
                        <input
                          value={value === null || value === undefined ? '' : String(value)}
                          type="text"
                          onChange={(event) => onDraft(rowKey, column.key, event.target.value)}
                        />
                        {!repeatRow && repeatCount > 0 && <em>повторов: {repeatCount}</em>}
                        {!repeatRow && analysisCount > 1 && <em>анализов: {analysisCount}</em>}
                      </span>
                    ) : editable && column.input === 'employee_multi' ? (
                      <button
                        type="button"
                        className="cell-picker-button"
                        title={listValue(value).join(', ')}
                        onClick={() => setMultiPicker({ rowId: rowKey, column, value: listValue(value) })}
                      >
                        {valueSummary(value)}
                      </button>
                    ) : editable && column.input === 'employee' ? (
                      <select value={value === null || value === undefined ? '' : String(value)} onChange={(event) => onDraft(rowKey, column.key, event.target.value)}>
                        <option value="">—</option>
                        {stageEmployees.map((employee) => <option value={employee.full_name} key={employee.id}>{employeeName(employee)}</option>)}
                      </select>
                    ) : editable && column.input === 'dictionary' ? (
                      <select value={value === null || value === undefined ? '' : String(value)} onChange={(event) => onDraft(rowKey, column.key, event.target.value)}>
                        <option value="">—</option>
                        {dictionaryOptions(referenceItems, column).map((item) => <option value={item.name} key={item.id}>{item.short_name || item.name}</option>)}
                      </select>
                    ) : editable ? (
                      <input
                        value={value === null || value === undefined ? '' : String(value)}
                        type={column.type === 'date' ? 'date' : column.type === 'number' ? 'number' : 'text'}
                        onChange={(event) => onDraft(rowKey, column.key, event.target.value)}
                      />
                    ) : column.key === 'rcsme_reg_no' ? (
                      <span className={`object-number-cell${repeatRow ? ' repeat' : ''}`}>
                        <span>{formatCell(value, column)}</span>
                        {!repeatRow && repeatCount > 0 && <em>повторов: {repeatCount}</em>}
                        {!repeatRow && analysisCount > 1 && <em>анализов: {analysisCount}</em>}
                      </span>
                    ) : column.key === 'analysis_pdf' && row.values.analysis_pdf_file_id ? (
                      <span className="analysis-pdf-actions">
                        <a className="tiny-button" href={api.electrophoresisFileUrl(String(row.values.analysis_pdf_file_id))} target="_blank" rel="noreferrer" title={String(row.values.analysis_pdf_filename || value || 'PDF фореза')}>
                          <Eye size={14} />Открыть
                        </a>
                        <a className="tiny-button" href={api.electrophoresisFileUrl(String(row.values.analysis_pdf_file_id), true)} title="Скачать PDF фореза">
                          <FileDown size={14} />Скачать
                        </a>
                      </span>
                    ) : (
                      <span>{formatCell(value, column)}</span>
                    )}
                  </div>
                )
              })}
              {showActionsColumn && (
                <div className="row-actions" role="cell">
                  {row.repeat_count > 0 && (
                    <button className="tiny-button" onClick={() => onHistory(row)} title="История попыток">
                      <History size={14} />{row.repeat_count + 1}
                    </button>
                  )}
                  {!controlRow && <button className="tiny-button" onClick={() => onOpen(row.object.id)}>Открыть</button>}
                </div>
              )}
            </div>
          )
        })}
      </div>
      {multiPicker && (
        <div className="modal-backdrop" role="presentation" onMouseDown={() => setMultiPicker(null)}>
          <div className="modal compact-modal" role="dialog" aria-modal="true" aria-label="Выбрать сотрудников" onMouseDown={(event) => event.stopPropagation()}>
            <h2>{columnLabel(multiPicker.column)}</h2>
            <div className="check-list compact-check-list">
              {stageEmployees.map((employee) => {
                const checked = multiPicker.value.includes(employee.full_name)
                return (
                  <label key={employee.id}>
                    <input
                      type="checkbox"
                      checked={checked}
                      onChange={(event) => {
                        const next = event.target.checked
                          ? [...multiPicker.value, employee.full_name]
                          : multiPicker.value.filter((item) => item !== employee.full_name)
                        setMultiPicker({ ...multiPicker, value: next })
                        onDraft(multiPicker.rowId, multiPicker.column.key, next)
                      }}
                    />
                    <span>{employeeName(employee)}</span>
                  </label>
                )
              })}
            </div>
            <div className="modal-actions">
              <button className="icon-button" onClick={() => { onDraft(multiPicker.rowId, multiPicker.column.key, []); setMultiPicker({ ...multiPicker, value: [] }) }}>Очистить</button>
              <button className="primary compact" onClick={() => setMultiPicker(null)}>Готово</button>
            </div>
          </div>
        </div>
      )}
      {filterColumn && (
        <div className="modal-backdrop transparent-backdrop" role="presentation" onMouseDown={() => setFilterColumn(null)}>
          <div className="modal compact-modal column-filter-modal" role="dialog" aria-modal="true" aria-label="Фильтр столбца" onMouseDown={(event) => event.stopPropagation()}>
            <h2>{columnLabel(filterColumn)}</h2>
            <div className="searchbox compact-search"><Search size={16} /><input autoFocus value={filterSearch} onChange={(event) => setFilterSearch(event.target.value)} placeholder="Поиск значения" /></div>
            <div className="check-list compact-check-list column-filter-list">
              {visibleFilterValues.map((value) => {
                const checked = filterDraft.includes(value)
                return (
                  <label key={value}>
                    <input
                      type="checkbox"
                      checked={checked}
                      onChange={(event) => {
                        setFilterDraft((prev) => event.target.checked ? [...prev, value] : prev.filter((item) => item !== value))
                      }}
                    />
                    <span>{value}</span>
                  </label>
                )
              })}
              {!visibleFilterValues.length && <div className="empty compact-empty">Значений нет</div>}
            </div>
            <div className="modal-actions">
              <button className="icon-button" onClick={() => setFilterDraft(filterValues)}>Выбрать все</button>
              <button className="icon-button" onClick={() => setFilterDraft([])}>Очистить</button>
              <button className="icon-button" onClick={() => { onColumnFilter(filterColumn.key, null); setFilterColumn(null) }}>Сбросить</button>
              <button
                className="primary compact"
                onClick={() => {
                  onColumnFilter(filterColumn.key, filterDraft.length === filterValues.length ? null : filterDraft)
                  setFilterColumn(null)
                }}
              >
                Применить
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

export function PartiesPage({
  user,
  onObjectOpen,
  onReportsOpen,
  initialPartyNo,
  onInitialPartyHandled
}: {
  user: User
  onObjectOpen: (id: number) => void
  onReportsOpen?: (tab?: string, params?: Record<string, string | number | boolean | null | undefined>) => void
  initialPartyNo?: string | null
  onInitialPartyHandled?: () => void
}) {
  const queryClient = useQueryClient()
  const [q, setQ] = useState('')
  const [objectQuery, setObjectQuery] = useState('')
  const [selectedId, setSelectedId] = useState<number | null>(null)
  const [includeArchived, setIncludeArchived] = useState(false)
  const [selectedYear, setSelectedYear] = useState<number | null>(null)
  const [activeStage, setActiveStage] = useState<(typeof stageTabs)[number][0]>('registration')
  const [quick, setQuick] = useState('')
  const [selectedRows, setSelectedRows] = useState<Set<number>>(new Set())
  const [drafts, setDrafts] = useState<DraftMap>({})
  const [createOpen, setCreateOpen] = useState(false)
  const [newPartyNo, setNewPartyNo] = useState('')
  const [newComment, setNewComment] = useState('')
  const [addObjectOpen, setAddObjectOpen] = useState(false)
  const [newObject, setNewObject] = useState<Partial<RegistryObject>>({})
  const [archiveOpen, setArchiveOpen] = useState(false)
  const [archiveConfirm, setArchiveConfirm] = useState('')
  const [archiveObjectsOpen, setArchiveObjectsOpen] = useState(false)
  const [archiveObjectsConfirm, setArchiveObjectsConfirm] = useState('')
  const [archiveObjectMessage, setArchiveObjectMessage] = useState('')
  const [permanentDeleteOpen, setPermanentDeleteOpen] = useState(false)
  const [permanentDeleteConfirm, setPermanentDeleteConfirm] = useState('')
  const [permanentDeleteMessage, setPermanentDeleteMessage] = useState('')
  const [fillOpen, setFillOpen] = useState(false)
  const [fillValues, setFillValues] = useState<Record<string, DraftValue>>({})
  const [fillComment, setFillComment] = useState('')
  const [fillApplyMode, setFillApplyMode] = useState<'append' | 'update_latest'>('append')
  const [fillObjectList, setFillObjectList] = useState('')
  const [fillListOpen, setFillListOpen] = useState(false)
  const [fillListResult, setFillListResult] = useState<ObjectListMatch | null>(null)
  const [fillEmployeePicker, setFillEmployeePicker] = useState<{ key: string; label: string; value: string[] } | null>(null)
  const [printOpen, setPrintOpen] = useState(false)
  const [printStageKeys, setPrintStageKeys] = useState<string[]>(['registration'])
  const [printTables, setPrintTables] = useState<Record<string, StageTable>>({})
  const [printColumnKeys, setPrintColumnKeys] = useState<Record<string, string[]>>({})
  const [registrationFillOpen, setRegistrationFillOpen] = useState(false)
  const [registrationFillForm, setRegistrationFillForm] = useState<RegistrationFillForm>({
    start_rcsme_reg_no: '',
    count: '100',
    update_existing: false,
    intake_date: '',
    decision_date: '',
    investigator: '',
    incoming_no: '',
    box_no: ''
  })
  const [registrationMilitaryList, setRegistrationMilitaryList] = useState('')
  const [registrationMilitaryListOpen, setRegistrationMilitaryListOpen] = useState(false)
  const registrationPreviewInitialized = useRef(false)
  const [historyRow, setHistoryRow] = useState<StageTableRow | null>(null)
  const [columnSettingsOpen, setColumnSettingsOpen] = useState(false)
  const [columnFilters, setColumnFilters] = useState<ColumnFilterState>({})
  const [copyMessage, setCopyMessage] = useState('')
  const [controlToast, setControlToast] = useState('')
  const controlToastTimer = useRef<number | null>(null)
  const controlDraftRef = useRef<PartyControlDraft>(partyControlDraft(null))
  const controlMutationVersion = useRef(0)
  const [hiddenColumns, setHiddenColumns] = useState<HiddenColumnState>(() => loadHiddenColumns(user.username))
  const [registrationActiveChecks, setRegistrationActiveChecks] = useState<RegistrationActiveState>(() => loadRegistrationActiveChecks(user.username))
  const [controlDraft, setControlDraft] = useState<PartyControlDraft>(() => partyControlDraft(null))
  const [controlCollapsed, setControlCollapsed] = useState(true)
  const canEdit = user.role !== 'viewer'
  const hasDrafts = Object.keys(drafts).length > 0
  const debouncedPartySearch = useDebouncedValue(q.trim(), 250)
  const debouncedObjectQuery = useDebouncedValue(objectQuery.trim(), 250)

  const partyYears = useQuery({ queryKey: ['parties', 'years'], queryFn: api.partyYears, staleTime: 300_000 })
  const parties = useQuery({ queryKey: ['parties', debouncedPartySearch, includeArchived, selectedYear], queryFn: () => api.parties(debouncedPartySearch, includeArchived, selectedYear), staleTime: 30_000 })
  const selected = selectedId ?? parties.data?.items?.[0]?.id ?? null
  const selectedPartyFromList = useMemo(
    () => parties.data?.items?.find((item) => item.id === selected) ?? null,
    [parties.data?.items, selected]
  )
  const party = useQuery({ queryKey: ['party', selected], queryFn: () => api.party(selected!), enabled: Boolean(selected) })
  const progress = useQuery({ queryKey: ['party-progress', selected], queryFn: () => api.partyProgress(selected!), enabled: Boolean(selected) })
  const employees = useQuery({ queryKey: ['employees', 'active-for-stage'], queryFn: () => api.employees(''), staleTime: 60_000 })
  const referenceItems = useQuery({ queryKey: ['reference-items', 'active-for-stage'], queryFn: () => api.referenceItems(), staleTime: 60_000 })
  const stageTable = useQuery({
    queryKey: ['party-stage-table', selected, activeStage, debouncedObjectQuery, quick],
    queryFn: () => api.partyStageTable(selected!, activeStage, debouncedObjectQuery, quick, true),
    enabled: Boolean(selected),
    staleTime: 30_000,
    refetchOnWindowFocus: false,
    placeholderData: (previous) => previous
  })
  const activeParty = party.data ?? selectedPartyFromList
  const apiRows: StageTableRow[] = stageTable.data?.rows ?? []
  const apiColumns: StageTableColumn[] = stageTable.data?.columns ?? []
  const partyItems = parties.data?.items ?? []
  const archivedPartyCount = partyItems.filter((item) => item.status === 'archived').length
  const activePartyCount = includeArchived ? partyItems.length - archivedPartyCount : (parties.data?.total ?? partyItems.length)
  const registrationActiveIds = useMemo(
    () => new Set(registrationActiveChecks[String(selected ?? '')] || []),
    [registrationActiveChecks, selected]
  )
  const rows = useMemo<StageTableRow[]>(() => {
    if (activeStage !== 'registration') return apiRows
    return apiRows.map((row) => ({
      ...row,
      values: {
        ...row.values,
        [registrationActiveColumnKey]: registrationActiveIds.has(row.object.id)
      }
    }))
  }, [activeStage, apiRows, registrationActiveIds])
  const columns = useMemo(() => withRegistrationActiveColumn(activeStage, apiColumns), [activeStage, apiColumns])
  const columnByKey = useMemo(() => Object.fromEntries(columns.map((column) => [column.key, column])), [columns])
  const stageHiddenKeys = useMemo(() => {
    const available = new Set([...columns.map((column) => column.key), actionsColumnKey])
    const configured = Object.prototype.hasOwnProperty.call(hiddenColumns, activeStage)
    const keys = configured ? hiddenColumns[activeStage] || [] : defaultHiddenColumns(activeStage)
    return new Set(keys.filter((key) => available.has(key)))
  }, [activeStage, columns, hiddenColumns])
  const showActionsColumn = !stageHiddenKeys.has(actionsColumnKey)
  const visibleColumns = useMemo(() => {
    const visible = columns.filter((column) => !stageHiddenKeys.has(column.key))
    return orderVisibleColumns(activeStage, visible.length > 0 ? visible : columns.slice(0, 1))
  }, [activeStage, columns, stageHiddenKeys])
  const columnSettingsColumns = useMemo(() => [...columns, actionsColumn], [columns])
  const filteredRows = useMemo(() => applyColumnFilters(rows, visibleColumns, columnFilters), [rows, visibleColumns, columnFilters])
  const partyObjectCount = activeParty?.object_count ?? stageTable.data?.total ?? 0
  const hasColumnFilters = Object.keys(columnFilters).length > 0
  const filteredObjectCount = hasColumnFilters ? filteredRows.length : (stageTable.data?.total ?? partyObjectCount)
  const columnFilterDescriptions = useMemo(() => {
    return Object.entries(columnFilters).map(([key, values]) => {
      const column = columnByKey[key]
      const label = column ? columnLabel(column) : key
      const visibleValues = values.length ? values.slice(0, 4).join(', ') : 'нет выбранных значений'
      const tail = values.length > 4 ? ` и ещё ${values.length - 4}` : ''
      return `${label}: ${visibleValues}${tail}`
    })
  }, [columnByKey, columnFilters])
  const fillVisibleRows = useMemo(
    () => filteredRows.filter((row) => !isControlRow(row) && !isBlockedNoObjectStageRow(activeStage, row)),
    [activeStage, filteredRows]
  )
  const fillVisibleObjectIds = useMemo(() => {
    const seen = new Set<number>()
    const ids: number[] = []
    for (const row of fillVisibleRows) {
      if (seen.has(row.object.id)) continue
      seen.add(row.object.id)
      ids.push(row.object.id)
    }
    return ids
  }, [fillVisibleRows])
  const fillSelectedObjectIds = useMemo(() => fillVisibleObjectIds.filter((id) => selectedRows.has(id)), [fillVisibleObjectIds, selectedRows])
  const fillListObjectIds = useMemo(() => {
    const seen = new Set<number>()
    const ids: number[] = []
    for (const id of fillListResult?.foundIds ?? []) {
      if (seen.has(id)) continue
      seen.add(id)
      ids.push(id)
    }
    return ids
  }, [fillListResult])
  const fillTargetObjectIds = fillListResult ? fillListObjectIds : selectedRows.size ? fillSelectedObjectIds : fillVisibleObjectIds
  const fillHasObjectListInput = Boolean(fillObjectList.trim() || fillListResult)
  const fillSelectedHiddenCount = selectedRows.size ? Math.max(0, selectedRows.size - fillSelectedObjectIds.length) : 0
  const fillTargetSummary = fillListResult
    ? `по списку: ${fillTargetObjectIds.length} ${objectWord(fillTargetObjectIds.length)}`
    : selectedRows.size
      ? `${fillTargetObjectIds.length} выбранных строк`
      : columnFilterDescriptions.length
        ? `по фильтрам столбцов: ${fillTargetObjectIds.length} ${objectWord(fillTargetObjectIds.length)}`
        : `по текущему фильтру: ${fillTargetObjectIds.length} ${objectWord(fillTargetObjectIds.length)}`
  const printTargetRows = useMemo(() => {
    const seen = new Set<number>()
    const result: StageTableRow[] = []
    for (const row of filteredRows) {
      if (isControlRow(row) || !selectedRows.has(row.object.id) || seen.has(row.object.id)) continue
      seen.add(row.object.id)
      result.push(row)
    }
    return result
  }, [filteredRows, selectedRows])
  const printTargetObjectIds = useMemo(() => printTargetRows.map((row) => row.object.id), [printTargetRows])
  const printTargetNumbers = useMemo(
    () => printTargetRows.map((row) => String(row.object.rcsme_reg_no || row.values.rcsme_reg_no || row.object.id)),
    [printTargetRows]
  )
  const printPreparedStages = useMemo(
    () => printStageKeys
      .map((stage) => ({ stage, table: printTables[stage] }))
      .filter((item): item is { stage: string; table: StageTable } => Boolean(item.table)),
    [printStageKeys, printTables]
  )
  const printReady = printPreparedStages.length > 0 && printPreparedStages.every(({ stage }) => (printColumnKeys[stage] || []).length > 0)
  const hasControlDrafts = Boolean(activeParty) && partyControlFields.some(([key]) => String(activeParty?.[key] || '') !== controlDraft[key])
  const filledControlCount = activeParty ? partyControlFields.filter(([key]) => controlDraft[key].trim()).length : 0
  const readinessPercent = useMemo(() => {
    const counts = progress.data?.stage_counts ?? {}
    const trackedStages = printableStageTabs.filter(([stage]) => stage !== 'registration').map(([stage]) => canonicalStageKey(stage))
    const totalSlots = partyObjectCount * trackedStages.length
    if (!totalSlots) return 0
    const done = trackedStages.reduce((sum, stage) => sum + Math.min(counts[stage] ?? 0, partyObjectCount), 0)
    return Math.round((done / totalSlots) * 100)
  }, [partyObjectCount, progress.data?.stage_counts])
  const registrationNoObjectNumbers = useMemo(
    () => new Set(splitControlNumbers(controlDraft.control_decree_without_object).map(normalizeControlNo)),
    [controlDraft.control_decree_without_object]
  )
  const registrationNoDecreeNumbers = useMemo(
    () => new Set(splitControlNumbers(controlDraft.control_object_without_decree).map(normalizeControlNo)),
    [controlDraft.control_object_without_decree]
  )
  const registrationDuplicateExternalNumbers = useMemo(() => {
    const counts = new Map<string, number>()
    for (const row of rows) {
      if (activeStage !== 'registration') continue
      const normalized = normalizeControlNo(rowExternalMilitaryNo(row))
      if (!normalized) continue
      counts.set(normalized, (counts.get(normalized) || 0) + 1)
    }
    return new Set(Array.from(counts.entries()).filter(([, count]) => count > 1).map(([key]) => key))
  }, [activeStage, rows])

  function rowNeedsPreciseControlToken(row: StageTableRow) {
    return registrationDuplicateExternalNumbers.has(normalizeControlNo(rowExternalMilitaryNo(row)))
  }

  const createParty = useMutation({
    mutationFn: () => api.createParty({ party_no: newPartyNo.trim(), case_year: selectedYear ?? partyYears.data?.default_year ?? new Date().getFullYear(), comment: newComment.trim() || null }),
    onSuccess: (created) => {
      setCreateOpen(false)
      setNewPartyNo('')
      setNewComment('')
      setSelectedId(created.id)
      queryClient.invalidateQueries({ queryKey: ['parties'] })
    }
  })
  const archiveParty = useMutation({
    mutationFn: (id: number) => api.archiveParty(id),
    onSuccess: () => {
      setArchiveOpen(false)
      setArchiveConfirm('')
      setSelectedId(null)
      queryClient.invalidateQueries({ queryKey: ['parties'] })
      queryClient.invalidateQueries({ queryKey: ['party'] })
      queryClient.invalidateQueries({ queryKey: ['party-progress'] })
    }
  })
  const archiveObject = useMutation({
    mutationFn: async (ids: number[]) => {
      for (const id of ids) {
        await api.archiveObject(id)
      }
      return ids.length
    },
    onSuccess: (count) => {
      setArchiveObjectsOpen(false)
      setArchiveObjectsConfirm('')
      setArchiveObjectMessage(`Удалено из партии: ${count} ${objectWord(count)}`)
      setSelectedRows(new Set())
      queryClient.invalidateQueries({ queryKey: ['parties'] })
      queryClient.invalidateQueries({ queryKey: ['party'] })
      queryClient.invalidateQueries({ queryKey: ['dashboard'] })
      queryClient.invalidateQueries({ queryKey: ['objects'] })
      queryClient.invalidateQueries({ queryKey: ['party-stage-table'] })
      queryClient.invalidateQueries({ queryKey: ['party-progress'] })
    }
  })
  const permanentDeleteParty = useMutation({
    mutationFn: (id: number) => api.deletePartyPermanent(id),
    onSuccess: (result) => {
      setPermanentDeleteOpen(false)
      setPermanentDeleteConfirm('')
      setPermanentDeleteMessage(`Партия ${result.party_no} удалена окончательно: удалено ${result.objects_deleted} ${objectWord(result.objects_deleted)}`)
      setSelectedId(null)
      queryClient.invalidateQueries({ queryKey: ['parties'] })
      queryClient.invalidateQueries({ queryKey: ['party'] })
      queryClient.invalidateQueries({ queryKey: ['dashboard'] })
      queryClient.invalidateQueries({ queryKey: ['objects'] })
      queryClient.invalidateQueries({ queryKey: ['party-stage-table'] })
      queryClient.invalidateQueries({ queryKey: ['party-progress'] })
    }
  })
  const createObject = useMutation({
    mutationFn: () => api.createObject({
      ...newObject,
      party_id: activeParty?.id ?? null,
      party_no: activeParty?.party_no ?? null,
      case_year: activeParty?.case_year ?? null
    }),
    onSuccess: (created) => {
      setAddObjectOpen(false)
      setNewObject({})
      queryClient.invalidateQueries({ queryKey: ['party-stage-table'] })
      queryClient.invalidateQueries({ queryKey: ['party'] })
      queryClient.invalidateQueries({ queryKey: ['parties'] })
      queryClient.invalidateQueries({ queryKey: ['party-progress'] })
      onObjectOpen(created.id)
    }
  })
  const toggleBurntBone = useMutation({
    mutationFn: ({ row, checked }: { row: StageTableRow; checked: boolean }) => {
      return api.updateObject(row.object.id, {
        object_description: checked ? 'горелая кость' : 'кость'
      })
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['party-stage-table'] })
      queryClient.invalidateQueries({ queryKey: ['objects'] })
      queryClient.invalidateQueries({ queryKey: ['party'] })
      queryClient.invalidateQueries({ queryKey: ['parties'] })
      queryClient.invalidateQueries({ queryKey: ['dashboard'] })
      queryClient.invalidateQueries({ queryKey: ['party-progress'] })
    }
  })
  const toggleNoBiomaterial = useMutation({
    mutationFn: ({ row, checked }: { row: StageTableRow; checked: boolean }) => {
      return api.updateObject(row.object.id, {
        object_description: checked ? 'Нет биоматериала' : 'кость'
      })
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['party-stage-table'] })
      queryClient.invalidateQueries({ queryKey: ['objects'] })
      queryClient.invalidateQueries({ queryKey: ['party'] })
      queryClient.invalidateQueries({ queryKey: ['parties'] })
      queryClient.invalidateQueries({ queryKey: ['dashboard'] })
      queryClient.invalidateQueries({ queryKey: ['party-progress'] })
    }
  })
  const saveDrafts = useMutation({
    mutationFn: async () => {
      for (const [draftKey, patch] of Object.entries(drafts)) {
        const objectId = objectIdFromDraftKey(draftKey)
        if (activeStage === 'registration') {
          await api.updateObject(objectId, patch as Partial<RegistryObject>)
          continue
        }
        const objectPatch = Object.fromEntries(
          Object.entries(patch).filter(([key]) => objectPatchKeys.has(key))
        ) as Partial<RegistryObject>
        const stagePatch = Object.fromEntries(
          Object.entries(patch).filter(([key]) => !objectPatchKeys.has(key))
        ) as Record<string, DraftValue>
        if (Object.keys(objectPatch).length) {
          await api.updateObject(objectId, objectPatch)
        }
        if (Object.keys(stagePatch).length) {
          const commentTouched = Object.prototype.hasOwnProperty.call(stagePatch, 'comment')
          const commentValue = commentTouched ? stagePatch.comment : undefined
          const stageValues = Object.fromEntries(
            Object.entries(stagePatch).filter(([key]) => key !== 'comment')
          ) as Record<string, DraftValue>
          const { detail_data, performers } = stagePayloadFromValues(activeStage, stageValues)
          const payload = {
            stage_type: activeStage,
            object_id: objectId,
            detail_data,
            performers,
            source: 'manual'
          } as Parameters<typeof api.stageEventsApplyInline>[0]
          if (commentTouched) {
            payload.comment = commentValue === null || commentValue === undefined ? null : String(commentValue)
          }
          await api.stageEventsApplyInline(payload)
        }
      }
    },
    onSuccess: () => {
      setDrafts({})
      queryClient.invalidateQueries({ queryKey: ['party-stage-table'] })
      queryClient.invalidateQueries({ queryKey: ['objects'] })
      queryClient.invalidateQueries({ queryKey: ['party-progress'] })
    }
  })
  const savePartyControl = useMutation({
    mutationFn: () => {
      if (!activeParty) throw new Error('Партия не выбрана')
      const payload = Object.fromEntries(
        partyControlFields.map(([key]) => {
          const value = controlDraft[key].trim()
          return [key, value || null]
        })
      ) as Partial<Party>
      return api.updateParty(activeParty.id, payload)
    },
    onSuccess: (updated) => {
      const next = partyControlDraft(updated)
      controlDraftRef.current = next
      setControlDraft(next)
      queryClient.invalidateQueries({ queryKey: ['parties'] })
      queryClient.invalidateQueries({ queryKey: ['party'] })
      queryClient.invalidateQueries({ queryKey: ['dashboard'] })
      queryClient.invalidateQueries({ queryKey: ['party-progress'] })
    }
  })
  const toggleNoObjectControl = useMutation({
    mutationFn: ({ partyId, payload }: ControlToggleVariables) => {
      return api.updateParty(partyId, payload)
    },
    onMutate: (variables) => {
      const version = controlMutationVersion.current + 1
      controlMutationVersion.current = version
      controlDraftRef.current = variables.nextDraft
      setControlDraft(variables.nextDraft)
      return { version, previousDraft: variables.previousDraft }
    },
    onError: (_error, _variables, context) => {
      if (context?.version !== controlMutationVersion.current) return
      controlDraftRef.current = context.previousDraft
      setControlDraft(context.previousDraft)
    },
    onSuccess: (updated, _variables, context) => {
      if (context?.version === controlMutationVersion.current) {
        const next = {
          ...controlDraftRef.current,
          control_decree_without_object: updated.control_decree_without_object || ''
        }
        controlDraftRef.current = next
        setControlDraft(next)
      }
      queryClient.setQueryData(['party', updated.id], updated)
    }
  })
  const toggleNoDecreeControl = useMutation({
    mutationFn: ({ partyId, payload }: ControlToggleVariables) => {
      return api.updateParty(partyId, payload)
    },
    onMutate: (variables) => {
      const version = controlMutationVersion.current + 1
      controlMutationVersion.current = version
      controlDraftRef.current = variables.nextDraft
      setControlDraft(variables.nextDraft)
      return { version, previousDraft: variables.previousDraft }
    },
    onError: (_error, _variables, context) => {
      if (context?.version !== controlMutationVersion.current) return
      controlDraftRef.current = context.previousDraft
      setControlDraft(context.previousDraft)
    },
    onSuccess: (updated, _variables, context) => {
      if (context?.version === controlMutationVersion.current) {
        const next = {
          ...controlDraftRef.current,
          control_object_without_decree: updated.control_object_without_decree || ''
        }
        controlDraftRef.current = next
        setControlDraft(next)
      }
      queryClient.setQueryData(['party', updated.id], updated)
    }
  })

  function showControlConflictToast() {
    setControlToast('Нельзя одновременно отметить «Нет объекта» и «Нет постановления» для одного номера')
    if (controlToastTimer.current !== null) {
      window.clearTimeout(controlToastTimer.current)
    }
    controlToastTimer.current = window.setTimeout(() => setControlToast(''), 3000)
  }

  function handleToggleNoObjectControl(row: StageTableRow, checked: boolean) {
    if (!activeParty) return
    const precise = rowNeedsPreciseControlToken(row)
    const externalMilitaryNo = rowExternalMilitaryNo(row)
    if (!externalMilitaryNo) return
    const currentNoDecree = new Set(splitControlNumbers(controlDraftRef.current.control_object_without_decree).map(normalizeControlNo))
    if (checked && controlSetHasRow(currentNoDecree, row)) {
      showControlConflictToast()
      return
    }
    const previousDraft = controlDraftRef.current
    const nextDraft = controlDraftWithToggle(previousDraft, 'control_decree_without_object', row, checked, precise)
    toggleNoObjectControl.mutate({
      partyId: activeParty.id,
      previousDraft,
      nextDraft,
      payload: { control_decree_without_object: nextDraft.control_decree_without_object || null }
    })
  }

  function handleToggleNoDecreeControl(row: StageTableRow, checked: boolean) {
    if (!activeParty) return
    const precise = rowNeedsPreciseControlToken(row)
    const externalMilitaryNo = rowExternalMilitaryNo(row)
    if (!externalMilitaryNo) return
    const currentNoObject = new Set(splitControlNumbers(controlDraftRef.current.control_decree_without_object).map(normalizeControlNo))
    if (checked && controlSetHasRow(currentNoObject, row)) {
      showControlConflictToast()
      return
    }
    const previousDraft = controlDraftRef.current
    const nextDraft = controlDraftWithToggle(previousDraft, 'control_object_without_decree', row, checked, precise)
    toggleNoDecreeControl.mutate({
      partyId: activeParty.id,
      previousDraft,
      nextDraft,
      payload: { control_object_without_decree: nextDraft.control_object_without_decree || null }
    })
  }

  function handleToggleRegistrationActive(row: StageTableRow, checked: boolean) {
    const partyKey = String(activeParty?.id ?? row.object.party_id ?? selected ?? '')
    if (!partyKey) return
    setRegistrationActiveChecks((prev) => {
      const current = new Set(prev[partyKey] || [])
      if (checked) current.add(row.object.id)
      else current.delete(row.object.id)
      const next = { ...prev }
      if (current.size) next[partyKey] = Array.from(current)
      else delete next[partyKey]
      return next
    })
  }

  const fillPayload = useMemo(() => {
    const fields = stageFieldConfigs[activeStage] || []
    const rawValues: Record<string, DraftValue> = {}
    for (const field of fields) {
      const value = fillValues[field.key]
      if (value === null || value === undefined || value === '' || (Array.isArray(value) && !value.length)) continue
      rawValues[field.key] = field.type === 'number' && typeof value === 'string' ? Number(value) : value
    }
    const { detail_data, performers } = stagePayloadFromValues(activeStage, rawValues)
    return {
      stage_type: activeStage,
      party_ids: [],
      object_ids: fillTargetObjectIds,
      q: null,
      filters: {},
      title: `Массовое заполнение: ${stageLabels[activeStage] || activeStage}`,
      comment: fillComment || null,
      apply_mode: fillApplyMode,
      detail_data,
      performers
    }
  }, [activeStage, fillApplyMode, fillComment, fillTargetObjectIds, fillValues])

  const hasFillData = useMemo(() => {
    if (fillComment.trim()) return true
    return Object.values(fillValues).some((value) => {
      if (Array.isArray(value)) return value.length > 0
      if (typeof value === 'string') return value.trim() !== ''
      return value !== null && value !== undefined
    })
  }, [fillComment, fillValues])
  const hasFillTargets = Boolean(
    selected && (
      fillHasObjectListInput
        ? Boolean(fillListResult && fillTargetObjectIds.length > 0)
        : fillTargetObjectIds.length > 0
    )
  )

  const previewFill = useMutation({ mutationFn: () => api.stageEventsPreview(fillPayload) })
  const applyFill = useMutation({
    mutationFn: () => api.stageEventsApply({ ...fillPayload, source: 'manual' }),
    onSuccess: () => {
      setFillOpen(false)
      setFillValues({})
      setFillComment('')
      setFillObjectList('')
      setFillListResult(null)
      setSelectedRows(new Set())
      queryClient.invalidateQueries({ queryKey: ['party-stage-table'] })
      queryClient.invalidateQueries({ queryKey: ['party-progress'] })
      queryClient.invalidateQueries({ queryKey: ['objects'] })
    }
  })

  function defaultPrintColumnsForStage(stage: string, table: StageTable) {
    if (stage === activeStage) {
      const visible = visibleColumns
        .filter((column) => table.columns.some((available) => available.key === column.key))
        .map((column) => column.key)
      if (visible.length) return visible
    }
    const available = printableColumns(stage, table.columns)
    const configured = Object.prototype.hasOwnProperty.call(hiddenColumns, stage)
    const hidden = new Set(configured ? hiddenColumns[stage] || [] : defaultHiddenColumns(stage))
    const visible = available.filter((column) => !hidden.has(column.key)).map((column) => column.key)
    return visible.length ? visible : available.slice(0, 6).map((column) => column.key)
  }

  const preparePrint = useMutation({
    mutationFn: async () => {
      if (!activeParty || !selected || !printTargetObjectIds.length) throw new Error('Выберите объекты для печати')
      const stages = printStageKeys.length ? printStageKeys : [activeStage === 'all' ? 'registration' : activeStage]
      const loaded: Record<string, StageTable> = {}
      for (const stage of stages) {
        loaded[stage] = await api.partyStageTable(activeParty.id, stage, '', '', true)
      }
      return loaded
    },
    onSuccess: (loaded) => {
      setPrintTables(loaded)
      setPrintColumnKeys((prev) => {
        const next: Record<string, string[]> = {}
        for (const [stage, table] of Object.entries(loaded)) {
          const available = new Set(printableColumns(stage, table.columns).map((column) => column.key))
          const existing = (prev[stage] || []).filter((key) => available.has(key))
          next[stage] = existing.length ? existing : defaultPrintColumnsForStage(stage, table)
        }
        return next
      })
    }
  })

  function registrationBulkPayload(override?: Partial<RegistrationFillForm>): RegistrationBulkRequest {
    const form = { ...registrationFillForm, ...override }
    return {
      start_rcsme_reg_no: form.start_rcsme_reg_no.trim() || null,
      count: Number(form.count) || 0,
      update_existing: form.update_existing,
      intake_date: form.intake_date || null,
      decision_date: form.decision_date || null,
      investigator: form.investigator.trim() || null,
      incoming_no: form.incoming_no.trim() || null,
      box_no: form.box_no.trim() || null,
      external_military_numbers: parseObjectNoList(registrationMilitaryList)
    }
  }

  function resetRegistrationFillResults() {
    applyRegistrationFill.reset()
  }

  function setRegistrationField(key: keyof RegistrationFillForm, value: string) {
    resetRegistrationFillResults()
    setRegistrationFillForm((prev) => ({ ...prev, [key]: value }))
  }

  function setRegistrationMilitaryNumbers(value: string) {
    resetRegistrationFillResults()
    setRegistrationMilitaryList(value)
  }

  function setRegistrationUpdateExisting(value: boolean) {
    resetRegistrationFillResults()
    setRegistrationFillForm((prev) => ({
      ...prev,
      update_existing: value,
      count: value ? String(activeParty?.object_count || prev.count || '1') : prev.count
    }))
  }

  const previewRegistrationFill = useMutation({
    mutationFn: (payload?: RegistrationBulkRequest) => {
      if (!selected) throw new Error('Партия не выбрана')
      return api.registrationBulkPreview(selected, payload ?? registrationBulkPayload())
    },
    onSuccess: (data) => {
      setRegistrationFillForm((prev) => prev.update_existing || prev.start_rcsme_reg_no.trim()
        ? prev
        : { ...prev, start_rcsme_reg_no: data.suggested_start_rcsme_reg_no })
    }
  })

  const applyRegistrationFill = useMutation({
    mutationFn: () => {
      if (!selected) throw new Error('Партия не выбрана')
      return api.registrationBulkApply(selected, registrationBulkPayload())
    },
    onSuccess: () => {
      setRegistrationFillOpen(false)
      setRegistrationMilitaryList('')
      previewRegistrationFill.reset()
      queryClient.invalidateQueries({ queryKey: ['party-stage-table'] })
      queryClient.invalidateQueries({ queryKey: ['party'] })
      queryClient.invalidateQueries({ queryKey: ['parties'] })
      queryClient.invalidateQueries({ queryKey: ['dashboard'] })
      queryClient.invalidateQueries({ queryKey: ['objects'] })
      queryClient.invalidateQueries({ queryKey: ['party-progress'] })
    }
  })

  const registrationPreviewRows = useMemo<RegistrationBulkRow[]>(() => {
    const data = previewRegistrationFill.data
    if (!data) return []
    const militaryNumbers = parseObjectNoList(registrationMilitaryList)
    return data.rows.map((row, index) => ({
      ...row,
      external_military_no: militaryNumbers[index] || row.external_military_no,
      intake_date: registrationFillForm.intake_date || row.intake_date,
      decision_date: registrationFillForm.decision_date || row.decision_date,
      investigator: registrationFillForm.investigator.trim() || row.investigator,
      incoming_no: registrationFillForm.incoming_no.trim() || row.incoming_no,
      box_no: registrationFillForm.box_no.trim() || row.box_no
    }))
  }, [previewRegistrationFill.data, registrationFillForm, registrationMilitaryList])

  useEffect(() => {
    if (selectedYear === null && partyYears.data?.default_year) {
      setSelectedYear(partyYears.data.default_year)
    }
  }, [partyYears.data?.default_year, selectedYear])

  useEffect(() => {
    if (!parties.data) return
    if (initialPartyNo) {
      const target = parties.data.items.find((item) => item.party_no === initialPartyNo)
      if (target) {
        setSelectedId(target.id)
        onInitialPartyHandled?.()
        return
      }
      if (selectedYear !== null) {
        setSelectedYear(null)
        return
      }
    }
    if (!selectedId && parties.data.items[0]) {
      setSelectedId(parties.data.items[0].id)
      return
    }
    if (selectedId && !parties.data.items.some((item) => item.id === selectedId)) {
      setSelectedId(parties.data.items[0]?.id ?? null)
    }
  }, [initialPartyNo, onInitialPartyHandled, parties.data, selectedId, selectedYear])

  useEffect(() => {
    setObjectQuery('')
    setSelectedRows(new Set())
    setDrafts({})
    setQuick('')
    setColumnFilters({})
    setFillObjectList('')
    setFillListResult(null)
    setPrintOpen(false)
    setPrintTables({})
    setPrintColumnKeys({})
  }, [selected])

  useEffect(() => {
    setControlDraft(partyControlDraft(activeParty))
    controlDraftRef.current = partyControlDraft(activeParty)
    setControlCollapsed(true)
    savePartyControl.reset()
  }, [activeParty?.id])

  useEffect(() => {
    controlDraftRef.current = controlDraft
  }, [controlDraft])

  useEffect(() => {
    setSelectedRows(new Set())
    setColumnFilters({})
    setFillObjectList('')
    setFillListResult(null)
    setPrintTables({})
    setPrintColumnKeys({})
  }, [activeStage, debouncedObjectQuery, quick])

  useEffect(() => {
    saveHiddenColumns(user.username, hiddenColumns)
  }, [hiddenColumns, user.username])

  useEffect(() => {
    saveRegistrationActiveChecks(user.username, registrationActiveChecks)
  }, [registrationActiveChecks, user.username])

  useEffect(() => {
    return () => {
      if (controlToastTimer.current !== null) {
        window.clearTimeout(controlToastTimer.current)
      }
    }
  }, [])

  useEffect(() => {
    const handler = (event: BeforeUnloadEvent) => {
      if (!hasDrafts) return
      event.preventDefault()
      event.returnValue = ''
    }
    window.addEventListener('beforeunload', handler)
    return () => window.removeEventListener('beforeunload', handler)
  }, [hasDrafts])

  function toggleRow(id: number) {
    setSelectedRows((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  function toggleAllRows() {
    setSelectedRows((prev) => {
      const visible = filteredRows
        .filter((row) => !isControlRow(row) && !isBlockedNoObjectStageRow(activeStage, row))
        .map((row) => row.object.id)
      if (visible.every((id) => prev.has(id))) return new Set()
      return new Set(visible)
    })
  }

  function setColumnFilter(key: string, values: string[] | null) {
    setColumnFilters((prev) => {
      const next = { ...prev }
      if (!values) delete next[key]
      else next[key] = values
      return next
    })
    setSelectedRows(new Set())
  }

  async function matchObjectList() {
    const source = parseObjectNoList(fillObjectList)
    const seen = new Set<string>()
    const duplicates: string[] = []
    const missing: string[] = []
    const blocked: string[] = []
    const foundIds: number[] = []
    const byNumber = new Map<string, StageTableRow>()
    const searchRows = selected
      ? await api.partyStageTable(selected, activeStage, '', '', false).then((table) => table.rows).catch(() => rows)
      : rows
    searchRows.forEach((row) => {
      const keys = [
        row.object.rcsme_reg_no,
        row.object.decree_no,
        row.values.rcsme_reg_no,
        row.values.decree_no
      ]
      keys.forEach((value) => {
        if (value) byNumber.set(normalizeObjectNo(String(value)), row)
      })
    })
    source.forEach((raw) => {
      const normalized = normalizeObjectNo(raw)
      if (!normalized) return
      if (seen.has(normalized)) {
        duplicates.push(raw)
        return
      }
      seen.add(normalized)
      const row = byNumber.get(normalized)
      if (row && isBlockedNoObjectStageRow(activeStage, row)) blocked.push(raw)
      else if (row) foundIds.push(row.object.id)
      else missing.push(raw)
    })
    const result = { foundIds, missing, duplicates, blocked, sourceCount: source.length }
    setFillListResult(result)
    setSelectedRows(new Set(foundIds))
    previewFill.reset()
    applyFill.reset()
  }

  function clearObjectListSelection() {
    setFillObjectList('')
    setFillListResult(null)
    setSelectedRows(new Set())
    previewFill.reset()
    applyFill.reset()
  }

  async function copyVisibleNumbers() {
    const copySelected = selectedRows.size > 0
    const sourceRows = copySelected
      ? filteredRows.filter((row) => !isControlRow(row) && selectedRows.has(row.object.id))
      : filteredRows.filter((row) => !isControlRow(row))
    const numbers = sourceRows
      .map((row) => row.object.rcsme_reg_no || row.values.rcsme_reg_no)
      .filter(Boolean)
    const text = numbers.join('\n')
    if (!text) {
      setCopyMessage('Нет номеров для копирования')
      window.setTimeout(() => setCopyMessage(''), 3000)
      return
    }
    const copied = await copyTextToClipboard(text)
    setCopyMessage(copied
      ? `${copySelected ? 'Скопировано выбранных' : 'Скопировано видимых'}: ${numbers.length}`
      : 'Браузер запретил копирование. Откройте сервис через http://127.0.0.1:4001 или выделите номера вручную.'
    )
    window.setTimeout(() => setCopyMessage(''), 3000)
  }

  async function copyMissingNumbers() {
    const text = fillListResult?.missing.join('\n') || ''
    if (!text) return
    const copied = await copyTextToClipboard(text)
    setCopyMessage(copied
      ? `Скопировано не найденных: ${fillListResult?.missing.length ?? 0}`
      : 'Браузер запретил копирование. Откройте сервис через http://127.0.0.1:4001 или выделите номера вручную.'
    )
    window.setTimeout(() => setCopyMessage(''), 3000)
  }

  function setDraft(id: string, key: string, value: DraftValue) {
    const column = columnByKey[key]
    const nextValue = typeof value === 'string'
      ? patchValue(value, column || { key, label: key, type: 'text', editable: true, width: 120, input: 'text', dictionary_category: null })
      : value
    setDrafts((prev) => ({
      ...prev,
      [id]: {
        ...(prev[id] || {}),
        [key]: nextValue
      }
    }))
  }

  function setStageHidden(nextHidden: string[]) {
    const available = new Set([...columns.map((column) => column.key), actionsColumnKey])
    const sanitized = nextHidden.filter((key) => available.has(key))
    setHiddenColumns((prev) => {
      const next = { ...prev }
      next[activeStage] = sanitized
      return next
    })
  }

  function resetStageHidden() {
    setHiddenColumns((prev) => {
      const next = { ...prev }
      delete next[activeStage]
      return next
    })
  }

  function toggleColumnVisibility(key: string) {
    const hidden = new Set(stageHiddenKeys)
    if (hidden.has(key)) {
      hidden.delete(key)
    } else {
      const visibleDataCount = columns.filter((column) => !hidden.has(column.key)).length
      if (key !== actionsColumnKey && visibleDataCount <= 1) return
      hidden.add(key)
    }
    setStageHidden(Array.from(hidden))
  }

  const archiveDisabled = !canEdit || !activeParty || activeParty.status === 'archived'
  const archiveMatches = Boolean(activeParty && archiveConfirm.trim() === activeParty.party_no)
  const canDeletePermanently = user.role === 'admin' && includeArchived && activeParty?.status === 'archived'
  const permanentDeleteMatches = Boolean(activeParty && permanentDeleteConfirm.trim() === activeParty.party_no)
  const selectedArchiveRows = useMemo(() => {
    const seen = new Set<number>()
    return rows.filter((row) => {
      if (isControlRow(row) || !selectedRows.has(row.object.id) || seen.has(row.object.id)) return false
      seen.add(row.object.id)
      return true
    })
  }, [rows, selectedRows])
  const selectedArchiveNumbers = selectedArchiveRows.map((row) => String(row.object.rcsme_reg_no || row.values.rcsme_reg_no || row.object.id))
  const selectedArchiveRepeatCount = selectedArchiveRows.reduce((total, row) => total + (isRepeatObjectRow(row) ? 0 : objectRepeatCount(row)), 0)
  const archiveObjectsMatches = archiveObjectsConfirm.trim().toUpperCase() === 'УДАЛИТЬ'
  const stageCanFill = canEdit && activeStage !== 'all'
  const fillFields = stageFieldConfigs[activeStage] || []
  const fillStageEmployees = employeesForStage(employees.data ?? [], activeStage)

  function resetFillResults() {
    previewFill.reset()
    applyFill.reset()
  }

  function setFillField(key: string, value: DraftValue) {
    applyFill.reset()
    setFillValues((prev) => ({ ...prev, [key]: value }))
  }

  function setFillCommentValue(value: string) {
    applyFill.reset()
    setFillComment(value)
  }

  function openPrintDialog() {
    const initialStage = activeStage === 'all' ? 'registration' : activeStage
    setPrintStageKeys([initialStage])
    setPrintTables({})
    setPrintColumnKeys({})
    preparePrint.reset()
    setPrintOpen(true)
  }

  function togglePrintStage(stage: string, checked: boolean) {
    setPrintStageKeys((prev) => {
      if (checked) return prev.includes(stage) ? prev : [...prev, stage]
      return prev.filter((item) => item !== stage)
    })
    setPrintTables({})
    setPrintColumnKeys({})
    preparePrint.reset()
  }

  function togglePrintColumn(stage: string, key: string, checked: boolean) {
    setPrintColumnKeys((prev) => {
      const current = prev[stage] || []
      const next = checked
        ? current.includes(key) ? current : [...current, key]
        : current.filter((item) => item !== key)
      return { ...prev, [stage]: next }
    })
  }

  function setAllPrintColumns(stage: string, table: StageTable, checked: boolean) {
    setPrintColumnKeys((prev) => ({
      ...prev,
      [stage]: checked ? printableColumns(stage, table.columns).map((column) => column.key) : []
    }))
  }

  function runPrint() {
    if (!printPreparedStages.length) return
    window.setTimeout(() => window.print(), 50)
  }

  async function applyMassFill() {
    if (!hasFillTargets || !hasFillData || previewFill.isPending || applyFill.isPending) return
    const preview = await previewFill.mutateAsync().catch(() => null)
    if (!preview) return
    if (!preview.object_count || preview.warnings.length > 0) return
    await applyFill.mutateAsync().catch(() => null)
  }

  function openMassFill() {
    if (activeStage === 'registration') {
      const existingObjects = activeParty?.object_count || 0
      const defaults: RegistrationFillForm = {
        start_rcsme_reg_no: '',
        count: String(existingObjects || 100),
        update_existing: existingObjects > 0,
        intake_date: '',
        decision_date: '',
        investigator: '',
        incoming_no: '',
        box_no: ''
      }
      setRegistrationFillForm(defaults)
      setRegistrationMilitaryList('')
      setRegistrationMilitaryListOpen(false)
      registrationPreviewInitialized.current = false
      previewRegistrationFill.reset()
      applyRegistrationFill.reset()
      setRegistrationFillOpen(true)
      return
    }
    setFillApplyMode('append')
    setFillOpen(true)
  }

  useEffect(() => {
    if (!registrationFillOpen || !selected) return
    if (registrationPreviewInitialized.current) return
    const count = Number(registrationFillForm.count)
    if (!Number.isFinite(count) || count < 1 || count > 500) return
    registrationPreviewInitialized.current = true
    previewRegistrationFill.mutate(registrationBulkPayload())
  }, [registrationFillOpen, selected])

  useEffect(() => {
    previewFill.reset()
    applyFill.reset()
    setPrintTables({})
    setPrintColumnKeys({})
  }, [activeStage, columnFilters, objectQuery, quick, selected, selectedRows])

  return (
    <div className="page parties-page">
      {permanentDeleteMessage && <div className="alert success">{permanentDeleteMessage}</div>}
      {archiveObjectMessage && <div className="alert success">{archiveObjectMessage}</div>}
      <div className="party-layout">
        <aside className="section party-sidebar">
          <div className="party-sidebar-head">
            <h2>Партии</h2>
            {canEdit && (
              <button className="icon-button party-create-button" title="Создать партию" aria-label="Создать партию" onClick={() => setCreateOpen(true)}>
                <Plus size={18} />
              </button>
            )}
          </div>
          <div className="party-year-filter">
            <span>Год</span>
            <select value={selectedYear ?? 'all'} onChange={(event) => setSelectedYear(event.target.value === 'all' ? null : Number(event.target.value))}>
              <option value="all">Все годы</option>
              {(partyYears.data?.years ?? []).map((year) => <option key={year} value={year}>{year}</option>)}
            </select>
          </div>
          <div className="searchbox compact-search"><Search size={16} /><input value={q} onChange={(event) => setQ(event.target.value)} placeholder="Поиск" /></div>
          <div className="party-sidebar-count">
            {includeArchived ? `Всего: ${parties.data?.total ?? partyItems.length}, архив: ${archivedPartyCount}` : `Активные: ${activePartyCount}`}
          </div>
          <label className="check-toggle">
            <input type="checkbox" checked={includeArchived} onChange={(event) => setIncludeArchived(event.target.checked)} />
            <span>Показать архивные <em>скрыты по умолчанию</em></span>
          </label>
          <div className="party-list">
            {partyItems.map((item) => (
              <button key={item.id} className={`party-list-button ${selected === item.id ? 'active' : ''}`} onClick={() => setSelectedId(item.id)}>
                <span>{item.party_no}</span>
                <em>{item.status === 'archived' ? 'архив' : (selectedYear === null ? item.case_year || '' : '')}</em>
                <strong>{item.object_count}</strong>
              </button>
            ))}
            {!partyItems.length && <div className="empty">{q ? 'Партии не найдены' : 'Нет партий'}</div>}
          </div>
        </aside>
        <section className="section party-main">
          {!activeParty ? (
            <div className="empty party-empty">Выберите партию слева</div>
          ) : (
            <>
              <div className="party-main-head">
                <div>
                  <h2>Партия {activeParty.party_no} — {partyObjectCount} {objectWord(partyObjectCount)}</h2>
                  <div className="party-head-summary">
                    <span>{statusLabels[activeParty.status] || activeParty.status}{stageTable.isFetching ? ' · обновление...' : ''}</span>
                    <strong>Готовность: {readinessPercent}%</strong>
                    <strong>Контроль: {filledControlCount}/{partyControlFields.length}</strong>
                  </div>
                </div>
                <div className="toolbar-actions party-main-actions">
                  {canEdit && <button className="icon-button danger" disabled={archiveDisabled} onClick={() => setArchiveOpen(true)}><Archive size={18} />Удалить партию</button>}
                  {canDeletePermanently && <button className="icon-button danger" onClick={() => setPermanentDeleteOpen(true)}><Archive size={18} />Удалить окончательно</button>}
                  <button className="icon-button" disabled={!printTargetObjectIds.length} onClick={() => openPrintDialog()}><Printer size={18} />Печать</button>
                  <button className="icon-button" disabled={!onReportsOpen} onClick={() => onReportsOpen?.('overview', { party_ids: activeParty.id, case_year: activeParty.case_year })}><BarChart3 size={18} />Отчёт по партии</button>
                  <a className="icon-button" href={api.exportRegistryUrl(objectQuery, activeParty.party_no, activeParty.case_year)} title="Экспорт"><FileDown size={18} />Экспорт</a>
                  {stageCanFill && <button className="primary compact" onClick={() => openMassFill()}><ClipboardList size={18} />Массовое заполнение</button>}
                  {canEdit && <button className="icon-button" onClick={() => setAddObjectOpen(true)}><Plus size={18} />Добавить объект</button>}
                  {hasDrafts && (
                    <>
                      <button className="icon-button" onClick={() => setDrafts({})}><X size={18} />Отменить правки</button>
                      <button className="primary compact" disabled={saveDrafts.isPending} onClick={() => saveDrafts.mutate()}><Save size={18} />Сохранить изменения</button>
                    </>
                  )}
                </div>
              </div>
              <div className={`party-control-panel ${controlCollapsed ? 'collapsed' : ''}`}>
                <div className="party-control-panel-head">
                  <div className="party-control-title">
                    <h3>Контроль партии</h3>
                    <div className="party-control-summary">
                      <span>Заполнено {filledControlCount}/{partyControlFields.length}</span>
                      {hasControlDrafts && <strong>есть несохранённые изменения</strong>}
                    </div>
                  </div>
                  <button
                    className="icon-button party-control-toggle"
                    type="button"
                    aria-expanded={!controlCollapsed}
                    onClick={() => setControlCollapsed((value) => !value)}
                  >
                    {controlCollapsed ? <ChevronRight size={18} /> : <ChevronDown size={18} />}
                    {controlCollapsed ? 'Развернуть' : 'Свернуть'}
                  </button>
                </div>
                {!controlCollapsed && (
                  <>
                    {canEdit && (
                      <div className="toolbar-actions party-control-actions">
                        <button className="icon-button" disabled={!hasControlDrafts || savePartyControl.isPending} onClick={() => setControlDraft(partyControlDraft(activeParty))}><X size={18} />Отменить</button>
                        <button className="primary compact" disabled={!hasControlDrafts || savePartyControl.isPending} onClick={() => savePartyControl.mutate()}><Save size={18} />Сохранить контроль</button>
                      </div>
                    )}
                    <div className="party-control-form">
                      {partyControlFields.map(([key, label]) => (
                        <label key={key}>{label}
                          {canEdit ? (
                            <textarea value={controlDraft[key]} onChange={(event) => setControlDraft((prev) => ({ ...prev, [key]: event.target.value }))} />
                          ) : (
                            <strong>{activeParty[key] || '—'}</strong>
                          )}
                        </label>
                      ))}
                    </div>
                    {savePartyControl.error && <div className="alert error">{savePartyControl.error.message}</div>}
                    {savePartyControl.isSuccess && <div className="alert success">Контроль партии сохранён</div>}
                  </>
                )}
              </div>
              <div className="tabs stage-tabs">
                {stageTabs.map(([key, label]) => <button key={key} className={activeStage === key ? 'active' : ''} onClick={() => setActiveStage(key)}>{label}</button>)}
              </div>
              <div className="chips party-progress">
                {orderedStageCounts(progress.data?.stage_counts ?? {}).map(([stage, count]) => <span key={stage}>{stageLabels[stage] || stage}: {count}</span>)}
                {!Object.keys(progress.data?.stage_counts ?? {}).length && <span>Этапов нет</span>}
              </div>
              <div className="toolbar stage-toolbar">
                <div className="searchbox"><Search size={18} /><input value={objectQuery} onChange={(event) => setObjectQuery(event.target.value)} placeholder="Поиск внутри партии по номеру, в/ч, следователю, типу, этапам..." /></div>
                <div className="segmented">
                  {quickFilters.map(([key, label]) => <button key={key || 'all'} className={quick === key ? 'active' : ''} onClick={() => setQuick(key)}>{label}</button>)}
                </div>
                <button className="icon-button" disabled={!columns.length} onClick={() => setColumnSettingsOpen(true)}><Columns3 size={18} />Столбцы</button>
                {canEdit && (
                  <button
                    className="icon-button danger"
                    disabled={!selectedRows.size || archiveObject.isPending}
                    onClick={() => { setArchiveObjectsOpen(true); setArchiveObjectsConfirm(''); setArchiveObjectMessage('') }}
                  >
                    <Archive size={18} />Удалить объект
                  </button>
                )}
                <button className="icon-button" disabled={!filteredRows.length} onClick={() => copyVisibleNumbers()}><Copy size={18} />Скопировать номера</button>
                <span>{stageTable.isFetching ? 'Обновление...' : `${filteredObjectCount} ${objectWord(filteredObjectCount)}`}</span>
                {selectedRows.size > 0 && <strong>{selectedRows.size} выбрано</strong>}
                {copyMessage && <strong>{copyMessage}</strong>}
              </div>
              {controlToast && <div className="alert warning stage-toast">{controlToast}</div>}
              {(toggleNoObjectControl.error || toggleNoDecreeControl.error) && <div className="alert error">{(toggleNoObjectControl.error || toggleNoDecreeControl.error)?.message}</div>}
              {toggleBurntBone.error && <div className="alert error">{toggleBurntBone.error.message}</div>}
              {toggleNoBiomaterial.error && <div className="alert error">{toggleNoBiomaterial.error.message}</div>}
              {Object.keys(columnFilters).length > 0 && (
                <div className="chips filter-chips">
                  {Object.entries(columnFilters).map(([key, values]) => {
                    const column = columns.find((item) => item.key === key)
                    return (
                      <span key={key}>
                        {column ? columnLabel(column) : key}: {values.length}
                        <button type="button" onClick={() => setColumnFilter(key, null)} aria-label="Сбросить фильтр">×</button>
                      </span>
                    )
                  })}
                  <button className="tiny-button" onClick={() => { setColumnFilters({}); setSelectedRows(new Set()) }}>Сбросить фильтры</button>
                </div>
              )}
              <StageGrid
                columns={visibleColumns}
                rows={filteredRows}
                allRows={rows}
                columnFilters={columnFilters}
                selectedIds={selectedRows}
                drafts={drafts}
                employees={employees.data ?? []}
                referenceItems={referenceItems.data ?? []}
                canEdit={canEdit}
                activeStage={activeStage}
                showActionsColumn={showActionsColumn}
                registrationNoObjectNumbers={registrationNoObjectNumbers}
                registrationNoDecreeNumbers={registrationNoDecreeNumbers}
                onToggle={toggleRow}
                onToggleAll={toggleAllRows}
                onDraft={setDraft}
                onOpen={onObjectOpen}
                onHistory={setHistoryRow}
                onColumnFilter={setColumnFilter}
                onToggleNoObjectControl={handleToggleNoObjectControl}
                onToggleNoDecreeControl={handleToggleNoDecreeControl}
                onToggleBurntBone={(row, checked) => toggleBurntBone.mutate({ row, checked })}
                onToggleNoBiomaterial={(row, checked) => toggleNoBiomaterial.mutate({ row, checked })}
                registrationActiveIds={registrationActiveIds}
                onToggleRegistrationActive={handleToggleRegistrationActive}
              />
            </>
          )}
        </section>
      </div>
      {createOpen && (
        <div className="modal-backdrop" role="presentation" onMouseDown={() => setCreateOpen(false)}>
          <div className="modal" role="dialog" aria-modal="true" aria-label="Создать партию" onMouseDown={(event) => event.stopPropagation()}>
            <h2>Создать партию</h2>
            <div className="modal-summary"><span>Год: {selectedYear ?? partyYears.data?.default_year ?? new Date().getFullYear()}</span></div>
            <label>Номер партии<input autoFocus value={newPartyNo} onChange={(event) => setNewPartyNo(event.target.value)} /></label>
            <label>Комментарий<textarea value={newComment} onChange={(event) => setNewComment(event.target.value)} /></label>
            {createParty.error && <div className="alert error">{createParty.error.message}</div>}
            <div className="modal-actions">
              <button className="icon-button" onClick={() => setCreateOpen(false)}>Отмена</button>
              <button className="primary compact" disabled={!newPartyNo.trim() || createParty.isPending} onClick={() => createParty.mutate()}><Plus size={18} />Создать</button>
            </div>
          </div>
        </div>
      )}
      {archiveOpen && activeParty && (
        <div className="modal-backdrop" role="presentation" onMouseDown={() => setArchiveOpen(false)}>
          <div className="modal" role="dialog" aria-modal="true" aria-label="Удалить партию" onMouseDown={(event) => event.stopPropagation()}>
            <h2>Удалить партию</h2>
            <div className="alert error">Вы действительно хотите удалить партию {activeParty.party_no}? В партии {activeParty.object_count} {objectWord(activeParty.object_count)}. Это действие нельзя выполнить случайно.</div>
            <label>Введите номер партии для подтверждения<input autoFocus value={archiveConfirm} onChange={(event) => setArchiveConfirm(event.target.value)} /></label>
            {archiveParty.error && <div className="alert error">{archiveParty.error.message}</div>}
            <div className="modal-actions">
              <button className="icon-button" onClick={() => setArchiveOpen(false)}>Отмена</button>
              <button className="icon-button danger" disabled={!archiveMatches || archiveParty.isPending} onClick={() => archiveParty.mutate(activeParty.id)}><Archive size={18} />Удалить партию</button>
            </div>
          </div>
        </div>
      )}
      {permanentDeleteOpen && activeParty && (
        <div className="modal-backdrop" role="presentation" onMouseDown={() => setPermanentDeleteOpen(false)}>
          <div className="modal" role="dialog" aria-modal="true" aria-label="Удалить окончательно" onMouseDown={(event) => event.stopPropagation()}>
            <h2>Удалить окончательно</h2>
            <div className="alert error">Партия {activeParty.party_no} уже в архиве. Окончательное удаление удалит партию, объекты и связанные этапы.</div>
            <label>Введите номер партии для подтверждения<input autoFocus value={permanentDeleteConfirm} onChange={(event) => setPermanentDeleteConfirm(event.target.value)} /></label>
            {permanentDeleteParty.error && <div className="alert error">{permanentDeleteParty.error.message}</div>}
            <div className="modal-actions">
              <button className="icon-button" onClick={() => setPermanentDeleteOpen(false)}>Отмена</button>
              <button className="icon-button danger" disabled={!permanentDeleteMatches || permanentDeleteParty.isPending} onClick={() => permanentDeleteParty.mutate(activeParty.id)}><Archive size={18} />Удалить окончательно</button>
            </div>
          </div>
        </div>
      )}
      {archiveObjectsOpen && (
        <div className="modal-backdrop" role="presentation" onMouseDown={() => setArchiveObjectsOpen(false)}>
          <div className="modal" role="dialog" aria-modal="true" aria-label="Удалить объект" onMouseDown={(event) => event.stopPropagation()}>
            <h2>Удалить объекты из партии</h2>
            <div className="alert error">
              Выбранные объекты будут перемещены в архив и скрыты из рабочих таблиц партии.
              {selectedArchiveRepeatCount > 0 ? ` У выбранных оригиналов есть повторы: ${selectedArchiveRepeatCount}; они тоже будут архивированы.` : ''}
            </div>
            <div className="archive-object-list">
              {selectedArchiveNumbers.slice(0, 24).map((number) => <span key={number}>{number}</span>)}
              {selectedArchiveNumbers.length > 24 && <span>+{selectedArchiveNumbers.length - 24}</span>}
            </div>
            <label>Введите УДАЛИТЬ для подтверждения
              <input autoFocus value={archiveObjectsConfirm} onChange={(event) => setArchiveObjectsConfirm(event.target.value)} />
            </label>
            {archiveObject.error && <div className="alert error">{archiveObject.error.message}</div>}
            <div className="modal-actions">
              <button className="icon-button" onClick={() => setArchiveObjectsOpen(false)}>Отмена</button>
              <button
                className="icon-button danger"
                disabled={!archiveObjectsMatches || archiveObject.isPending || !selectedArchiveRows.length}
                onClick={() => archiveObject.mutate(selectedArchiveRows.map((row) => row.object.id))}
              >
                <Archive size={18} />Удалить объект
              </button>
            </div>
          </div>
        </div>
      )}
      {addObjectOpen && activeParty && (
        <div className="modal-backdrop" role="presentation" onMouseDown={() => setAddObjectOpen(false)}>
          <div className="modal wide-modal object-create-modal" role="dialog" aria-modal="true" aria-label="Добавить объект" onMouseDown={(event) => event.stopPropagation()}>
            <h2>Добавить объект в партию {activeParty.party_no}</h2>
            <div className="form-grid flat object-create-grid">
              <label>№ постановления<input autoFocus value={newObject.decree_no || ''} onChange={(event) => setNewObject((prev) => ({ ...prev, decree_no: event.target.value }))} /></label>
              <label>№ рег РЦСМЭ<input value={newObject.rcsme_reg_no || ''} onChange={(event) => setNewObject((prev) => ({ ...prev, rcsme_reg_no: event.target.value }))} placeholder="Автоматически, если пусто" /></label>
              <label>№ в/ч<input value={newObject.external_military_no || ''} onChange={(event) => setNewObject((prev) => ({ ...prev, external_military_no: event.target.value }))} /></label>
              <label>Дата поступления<input type="date" value={newObject.intake_date || ''} onChange={(event) => setNewObject((prev) => ({ ...prev, intake_date: event.target.value }))} /></label>
              <label>Следователь<input value={newObject.investigator || ''} onChange={(event) => setNewObject((prev) => ({ ...prev, investigator: event.target.value }))} /></label>
              <label>Коробка<input value={newObject.box_no || ''} onChange={(event) => setNewObject((prev) => ({ ...prev, box_no: event.target.value }))} /></label>
              <label>Тип объекта<input value={newObject.object_type || ''} onChange={(event) => setNewObject((prev) => ({ ...prev, object_type: event.target.value }))} /></label>
              <label className="wide">Описание<textarea value={newObject.object_description || ''} onChange={(event) => setNewObject((prev) => ({ ...prev, object_description: event.target.value }))} /></label>
            </div>
            {createObject.error && <div className="alert error">{createObject.error.message}</div>}
            <div className="modal-actions">
              <button className="icon-button" onClick={() => setAddObjectOpen(false)}>Отмена</button>
              <button className="primary compact" disabled={createObject.isPending || (!newObject.decree_no && !newObject.rcsme_reg_no)} onClick={() => createObject.mutate()}><Plus size={18} />Добавить</button>
            </div>
          </div>
        </div>
      )}
      {registrationFillOpen && activeParty && (
        <div className="modal-backdrop" role="presentation" onMouseDown={() => setRegistrationFillOpen(false)}>
          <div className="modal mass-fill-modal registration-bulk-modal" role="dialog" aria-modal="true" aria-label="Массовое заполнение регистрации" onMouseDown={(event) => event.stopPropagation()}>
            <h2>Массовое заполнение: Регистрация</h2>
            <div className="summary-line">
              <span>Партия {activeParty.party_no}</span>
              <span>Год: {previewRegistrationFill.data?.case_year || activeParty.case_year || '—'}</span>
              <span>{registrationFillForm.update_existing ? 'Режим: обновление существующих' : `Старт: ${previewRegistrationFill.data?.suggested_start_rcsme_reg_no || registrationFillForm.start_rcsme_reg_no || '—'}`}</span>
              {previewRegistrationFill.data?.previous_party_no && (
                <span>После партии {previewRegistrationFill.data.previous_party_no}: {previewRegistrationFill.data.previous_last_rcsme_reg_no || '—'}</span>
              )}
            </div>
            {activeParty.object_count > 0 && (
              <label className="registration-bulk-mode">
                <input
                  type="checkbox"
                  checked={registrationFillForm.update_existing}
                  onChange={(event) => setRegistrationUpdateExisting(event.target.checked)}
                />
                <span>
                  <strong>Обновить существующие объекты партии</strong>
                  <small>Текущие строки будут загружены в preview; введённые поля дозаполнят выбранные столбцы, например Коробка.</small>
                </span>
              </label>
            )}
            <div className="form-grid flat mass-fill-grid registration-bulk-grid">
              <label>Начальный № рег РЦСМЭ
                <input
                  autoFocus
                  value={registrationFillForm.start_rcsme_reg_no}
                  disabled={registrationFillForm.update_existing}
                  onChange={(event) => setRegistrationField('start_rcsme_reg_no', event.target.value)}
                  placeholder={registrationFillForm.update_existing ? 'Не требуется' : 'Например 6000-1'}
                />
              </label>
              <label>{registrationFillForm.update_existing ? 'Обновить строк' : 'Количество объектов'}
                <input type="number" min={1} max={500} value={registrationFillForm.count} onChange={(event) => setRegistrationField('count', event.target.value)} />
              </label>
              <label>Дата поступления в РЦСМЭ
                <input type="date" value={registrationFillForm.intake_date} onChange={(event) => setRegistrationField('intake_date', event.target.value)} />
              </label>
              <label>Дата постановления
                <input type="date" value={registrationFillForm.decision_date} onChange={(event) => setRegistrationField('decision_date', event.target.value)} />
              </label>
              <label>Следователь
                <input value={registrationFillForm.investigator} onChange={(event) => setRegistrationField('investigator', event.target.value)} />
              </label>
              <label>№ вх.
                <input value={registrationFillForm.incoming_no} onChange={(event) => setRegistrationField('incoming_no', event.target.value)} />
              </label>
              <label>Коробка
                <input value={registrationFillForm.box_no} onChange={(event) => setRegistrationField('box_no', event.target.value)} />
              </label>
            </div>
            <div className="mass-object-list">
              <button type="button" className="icon-button mass-object-list-toggle" onClick={() => setRegistrationMilitaryListOpen((value) => !value)}>
                {registrationMilitaryListOpen ? <ChevronDown size={18} /> : <ChevronRight size={18} />}
                Список № в в/ч №522
              </button>
              {registrationMilitaryListOpen && (
                <div className="mass-object-list-body">
                  <label className="wide">Номера по строкам
                    <textarea
                      value={registrationMilitaryList}
                      onChange={(event) => setRegistrationMilitaryNumbers(event.target.value)}
                      placeholder={'522/1\n522/2\n522/3'}
                    />
                  </label>
                </div>
              )}
            </div>
            <div className="modal-actions sticky-actions">
              <button className="icon-button" onClick={() => setRegistrationFillOpen(false)}>Отмена</button>
              <button className="icon-button" disabled={previewRegistrationFill.isPending} onClick={() => previewRegistrationFill.mutate(registrationBulkPayload())}><History size={18} />Предпросмотр</button>
              <button
                className="primary compact"
                disabled={!previewRegistrationFill.data || previewRegistrationFill.data.conflicts.length > 0 || previewRegistrationFill.isPending || applyRegistrationFill.isPending}
                onClick={() => applyRegistrationFill.mutate()}
              >
                <Check size={18} />Применить
              </button>
            </div>
            {previewRegistrationFill.error && <div className="alert error">{previewRegistrationFill.error.message}</div>}
            {applyRegistrationFill.error && <div className="alert error">{applyRegistrationFill.error.message}</div>}
            {previewRegistrationFill.data?.warnings.map((warning) => <div className="alert warning" key={warning}>{warning}</div>)}
            {previewRegistrationFill.data?.conflicts.length ? (
              <div className="alert error">
                <strong>Конфликты номеров:</strong> {previewRegistrationFill.data.conflicts.slice(0, 10).join('; ')}
                {previewRegistrationFill.data.conflicts.length > 10 ? ` и ещё ${previewRegistrationFill.data.conflicts.length - 10}` : ''}
              </div>
            ) : null}
            {previewRegistrationFill.data?.extra_external_military_numbers.length ? (
              <div className="alert">Лишние значения № в в/ч №522: {previewRegistrationFill.data.extra_external_military_numbers.join(', ')}</div>
            ) : null}
            {applyRegistrationFill.data && (
              <div className="alert success">
                {applyRegistrationFill.data.objects_updated
                  ? `Обновлено объектов: ${applyRegistrationFill.data.objects_updated}`
                  : `Создано объектов: ${applyRegistrationFill.data.objects_created}`}
              </div>
            )}
            {previewRegistrationFill.data && (
              <>
                <div className="overview-grid compact-overview">
                  <div><span>{registrationFillForm.update_existing ? 'Будет обновлено' : 'Будет создано'}</span><strong>{registrationPreviewRows.length}</strong></div>
                  <div><span>В партии сейчас</span><strong>{previewRegistrationFill.data.existing_party_object_count}</strong></div>
                  <div><span>Конфликты</span><strong>{previewRegistrationFill.data.conflicts.length}</strong></div>
                  <div><span>Лишние № в/ч</span><strong>{previewRegistrationFill.data.extra_external_military_numbers.length}</strong></div>
                </div>
                <div className="registration-preview-table">
                  <div className="registration-preview-row registration-preview-head">
                    <div>№ п/п</div>
                    <div>№ рег РЦСМЭ</div>
                    <div>№ постановления</div>
                    <div>№ в в/ч №522</div>
                    <div>Дата поступления</div>
                    <div>Дата постановления</div>
                    <div>Следователь</div>
                    <div>№ вх.</div>
                    <div>Коробка</div>
                    <div>Проблемы</div>
                  </div>
                  {registrationPreviewRows.map((row) => (
                    <div className={`registration-preview-row ${row.conflicts.length ? 'has-conflict' : ''}`} key={`${row.index}-${row.rcsme_reg_no}`}>
                      <div>{row.registry_row_no}</div>
                      <div>{row.rcsme_reg_no}</div>
                      <div>{row.decree_no}</div>
                      <div>{row.external_military_no || '—'}</div>
                      <div>{row.intake_date || '—'}</div>
                      <div>{row.decision_date || '—'}</div>
                      <div title={row.investigator || ''}>{row.investigator || '—'}</div>
                      <div>{row.incoming_no || '—'}</div>
                      <div>{row.box_no || '—'}</div>
                      <div>{row.conflicts.length ? row.conflicts.join(', ') : '—'}</div>
                    </div>
                  ))}
                </div>
              </>
            )}
          </div>
        </div>
      )}
      {fillOpen && activeParty && (
        <div className="modal-backdrop" role="presentation" onMouseDown={() => setFillOpen(false)}>
          <div className="modal mass-fill-modal" role="dialog" aria-modal="true" aria-label="Массовое заполнение" onMouseDown={(event) => event.stopPropagation()}>
            <h2>Массовое заполнение: {stageLabels[activeStage]}</h2>
            <div className="summary-line">
              <span>Партия {activeParty.party_no}</span>
              <span>{fillTargetSummary}</span>
            </div>
            {!fillListResult && columnFilterDescriptions.length > 0 && (
              <div className="alert warning mass-fill-target-alert">
                Учитываются фильтры столбцов: {columnFilterDescriptions.join('; ')}.
              </div>
            )}
            {fillSelectedHiddenCount > 0 && (
              <div className="alert warning mass-fill-target-alert">
                {fillSelectedHiddenCount} выбранных строк скрыто текущими фильтрами и не будет заполнено.
              </div>
            )}
            <div className="form-grid flat mass-fill-mode-grid">
              <label>Режим заполнения
                <select value={fillApplyMode} onChange={(event) => setFillApplyMode(event.target.value as 'append' | 'update_latest')}>
                  <option value="append">Добавить новую попытку</option>
                  <option value="update_latest">Обновить текущие данные</option>
                </select>
              </label>
            </div>
            <div className="mass-object-list">
              <button type="button" className="icon-button mass-object-list-toggle" onClick={() => setFillListOpen((value) => !value)}>
                {fillListOpen ? <ChevronDown size={18} /> : <ChevronRight size={18} />}
                Список объектов
              </button>
              {fillListOpen && (
                <div className="mass-object-list-body">
                  <label className="wide">Номера объектов
                    <textarea
                      value={fillObjectList}
                      onChange={(event) => { setFillObjectList(event.target.value); setFillListResult(null); setSelectedRows(new Set()); resetFillResults() }}
                      placeholder={'310-1\n311-1\n312-1'}
                    />
                  </label>
                  <div className="modal-actions">
                    <button className="icon-button" disabled={!fillObjectList.trim()} onClick={() => matchObjectList()}><Search size={18} />Найти в партии</button>
                    <button className="icon-button" disabled={!fillListResult && !fillObjectList.trim()} onClick={() => clearObjectListSelection()}><X size={18} />Очистить список</button>
                  </div>
                  {fillListResult && (
                    <>
                      <div className="overview-grid compact-overview">
                        <div><span>Найдено</span><strong>{fillListResult.foundIds.length}</strong></div>
                        <div><span>Не найдено</span><strong>{fillListResult.missing.length}</strong></div>
                        <div><span>Дубликаты</span><strong>{fillListResult.duplicates.length}</strong></div>
                        <div><span>Вставлено</span><strong>{fillListResult.sourceCount}</strong></div>
                      </div>
                      {fillListResult.blocked.length > 0 && <div className="alert">Пропущены объекты с отметкой «Нет объекта»: {fillListResult.blocked.join(', ')}</div>}
                      {fillListResult.missing.length > 0 && (
                        <div className="alert">
                          <strong>Не найдены:</strong> {fillListResult.missing.join(', ')}
                          <button className="tiny-button" onClick={() => copyMissingNumbers()}>Скопировать</button>
                        </div>
                      )}
                      {fillListResult.duplicates.length > 0 && <div className="alert">Повторы в списке: {fillListResult.duplicates.join(', ')}</div>}
                    </>
                  )}
                </div>
              )}
            </div>
            <div className="form-grid flat mass-fill-grid">
              {fillFields.map((field) => {
                const column = columnByKey[field.key] as StageTableColumn | undefined
                const value = fillValues[field.key]
                const inputKind = column?.input || (field.performerRole ? 'employee' : 'text')
                return (
                  <label key={field.key}>{field.label}
                    {inputKind === 'employee_multi' ? (
                      <button
                        type="button"
                        className="cell-picker-button"
                        onClick={() => setFillEmployeePicker({ key: field.key, label: field.label, value: listValue(value) })}
                        title={listValue(value).join(', ')}
                      >
                        {valueSummary(value)}
                      </button>
                    ) : inputKind === 'employee' ? (
                      <select value={value === null || value === undefined ? '' : String(value)} onChange={(event) => setFillField(field.key, event.target.value)}>
                        <option value="">—</option>
                        {fillStageEmployees.map((employee) => <option value={employee.full_name} key={employee.id}>{employeeName(employee)}</option>)}
                      </select>
                    ) : inputKind === 'dictionary' && column ? (
                      <select value={value === null || value === undefined ? '' : String(value)} onChange={(event) => setFillField(field.key, event.target.value)}>
                        <option value="">—</option>
                        {dictionaryOptions(referenceItems.data ?? [], column).map((item) => <option value={item.name} key={item.id}>{item.short_name || item.name}</option>)}
                      </select>
                    ) : (
                      <input
                        type={field.type || column?.type || 'text'}
                        value={value === null || value === undefined || Array.isArray(value) ? '' : String(value)}
                        onChange={(event) => setFillField(field.key, event.target.value)}
                      />
                    )}
                  </label>
                )
              })}
              <label className="wide">Комментарий<textarea value={fillComment} onChange={(event) => setFillCommentValue(event.target.value)} /></label>
            </div>
            <div className="modal-actions sticky-actions">
              <button className="icon-button" onClick={() => setFillOpen(false)}>Отмена</button>
              <button className="primary compact" disabled={!hasFillTargets || !hasFillData || previewFill.isPending || applyFill.isPending} onClick={() => applyMassFill()}><Check size={18} />Применить</button>
            </div>
            {previewFill.data?.warnings.map((warning) => <div className="alert" key={warning}>{warning}</div>)}
            {applyFill.data && <div className="alert success">Создано событий: {applyFill.data.stage_events_created}; обновлено: {applyFill.data.stage_events_updated}</div>}
          </div>
        </div>
      )}
      {fillEmployeePicker && (
        <div className="modal-backdrop" role="presentation" onMouseDown={() => setFillEmployeePicker(null)}>
          <div className="modal compact-modal" role="dialog" aria-modal="true" aria-label="Выбрать сотрудников" onMouseDown={(event) => event.stopPropagation()}>
            <h2>{fillEmployeePicker.label}</h2>
            <div className="check-list compact-check-list">
              {fillStageEmployees.map((employee) => {
                const checked = fillEmployeePicker.value.includes(employee.full_name)
                return (
                  <label key={employee.id}>
                    <input
                      type="checkbox"
                      checked={checked}
                      onChange={(event) => {
                        const next = event.target.checked
                          ? [...fillEmployeePicker.value, employee.full_name]
                          : fillEmployeePicker.value.filter((item) => item !== employee.full_name)
                        applyFill.reset()
                        setFillEmployeePicker({ ...fillEmployeePicker, value: next })
                        setFillValues((prev) => ({ ...prev, [fillEmployeePicker.key]: next }))
                      }}
                    />
                    <span>{employeeName(employee)}</span>
                  </label>
                )
              })}
            </div>
            <div className="modal-actions">
              <button className="icon-button" onClick={() => { applyFill.reset(); setFillValues((prev) => ({ ...prev, [fillEmployeePicker.key]: [] })); setFillEmployeePicker({ ...fillEmployeePicker, value: [] }) }}>Очистить</button>
              <button className="primary compact" onClick={() => setFillEmployeePicker(null)}>Готово</button>
            </div>
          </div>
        </div>
      )}
      {printOpen && activeParty && (
        <div className="modal-backdrop" role="presentation" onMouseDown={() => setPrintOpen(false)}>
          <div className="modal print-modal" role="dialog" aria-modal="true" aria-label="Печать объектов" onMouseDown={(event) => event.stopPropagation()}>
            <h2>Печать объектов</h2>
            <div className="summary-line">
              <span>Партия {activeParty.party_no}</span>
              <span>{activeParty.case_year ? `Год: ${activeParty.case_year}` : 'Год не указан'}</span>
              <span>Выбрано: {printTargetObjectIds.length} {objectWord(printTargetObjectIds.length)}</span>
            </div>
            <div className="print-selected-list">
              {printTargetNumbers.slice(0, 24).join(', ')}
              {printTargetNumbers.length > 24 ? ` и ещё ${printTargetNumbers.length - 24}` : ''}
            </div>
            <div className="alert print-future-panel">
              Массовая печать заложена как следующий режим: несколько партий, сохранённые фильтры и пакетная печать. Сейчас печать работает по выбранным объектам одной текущей партии.
            </div>
            <div className="print-stage-picker">
              <strong>Этапы</strong>
              <div className="print-stage-list">
                {printableStageTabs.map(([stage, label]) => (
                  <label key={stage}>
                    <input
                      type="checkbox"
                      checked={printStageKeys.includes(stage)}
                      onChange={(event) => togglePrintStage(stage, event.target.checked)}
                    />
                    <span>{label}</span>
                  </label>
                ))}
              </div>
            </div>
            <div className="modal-actions">
              <button className="icon-button" onClick={() => setPrintOpen(false)}>Отмена</button>
              <button
                className="icon-button"
                disabled={!printStageKeys.length || !printTargetObjectIds.length || preparePrint.isPending}
                onClick={() => preparePrint.mutate()}
              >
                <Eye size={18} />Подготовить
              </button>
              <button className="primary compact" disabled={!printReady || preparePrint.isPending} onClick={() => runPrint()}>
                <Printer size={18} />Печать
              </button>
            </div>
            {preparePrint.error && <div className="alert error">{preparePrint.error.message}</div>}
            {preparePrint.isPending && <div className="alert">Подготовка печатных таблиц...</div>}
            {printPreparedStages.length > 0 && (
              <div className="print-columns-area">
                {printPreparedStages.map(({ stage, table }) => {
                  const availableColumns = printableColumns(stage, table.columns)
                  const selectedColumnKeys = new Set(printColumnKeys[stage] || [])
                  const targetRows = printRowsForObjects(table.rows, printTargetObjectIds)
                  return (
                    <div className="print-stage-card" key={stage}>
                      <div className="print-stage-card-head">
                        <strong>{stageLabels[stage] || stage}</strong>
                        <span>{targetRows.length} строк</span>
                        <button type="button" className="tiny-button" onClick={() => setAllPrintColumns(stage, table, true)}>Все</button>
                        <button type="button" className="tiny-button" onClick={() => setAllPrintColumns(stage, table, false)}>Очистить</button>
                      </div>
                      <div className="print-column-list">
                        {availableColumns.map((column) => (
                          <label key={column.key}>
                            <input
                              type="checkbox"
                              checked={selectedColumnKeys.has(column.key)}
                              onChange={(event) => togglePrintColumn(stage, column.key, event.target.checked)}
                            />
                            <span>{columnLabel(column)}</span>
                          </label>
                        ))}
                      </div>
                    </div>
                  )
                })}
              </div>
            )}
          </div>
        </div>
      )}
      {printOpen && activeParty && printPreparedStages.length > 0 && (
        <div className="print-document" aria-hidden="true">
          {printPreparedStages.map(({ stage, table }) => {
            const selectedColumnKeys = new Set(printColumnKeys[stage] || [])
            const stageColumns = printableColumns(stage, table.columns).filter((column) => selectedColumnKeys.has(column.key))
            const targetRows = printRowsForObjects(table.rows, printTargetObjectIds)
            if (!stageColumns.length) return null
            return (
              <section className="print-stage-section" key={stage}>
                <h2>Партия {activeParty.party_no}{activeParty.case_year ? `, ${activeParty.case_year}` : ''} — {stageLabels[stage] || stage}</h2>
                <table>
                  <thead>
                    <tr>
                      <th>№</th>
                      {stageColumns.map((column) => <th key={column.key}>{columnLabel(column)}</th>)}
                    </tr>
                  </thead>
                  <tbody>
                    {targetRows.map((row, index) => (
                      <tr key={`${stage}-${stageRowKey(row)}`}>
                        <td>{index + 1}</td>
                        {stageColumns.map((column) => (
                          <td key={column.key}>{formatCell(row.values[column.key], column)}</td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
                {!targetRows.length && <p>Нет строк для выбранных объектов.</p>}
              </section>
            )
          })}
        </div>
      )}
      {columnSettingsOpen && (
        <div className="modal-backdrop" role="presentation" onMouseDown={() => setColumnSettingsOpen(false)}>
          <div className="modal column-settings-modal" role="dialog" aria-modal="true" aria-label="Настроить столбцы" onMouseDown={(event) => event.stopPropagation()}>
            <h2>Столбцы: {stageLabels[activeStage] || activeStage}</h2>
            <div className="column-settings-list">
              {columnSettingsColumns.map((column) => {
                const checked = !stageHiddenKeys.has(column.key)
                const disabled = column.key !== actionsColumnKey && checked && visibleColumns.length <= 1
                return (
                  <label key={column.key} className="column-settings-row">
                    <input
                      type="checkbox"
                      checked={checked}
                      disabled={disabled}
                      onChange={() => toggleColumnVisibility(column.key)}
                    />
                    <span>{columnLabel(column)}</span>
                  </label>
                )
              })}
            </div>
            <div className="modal-actions">
              <button className="icon-button" onClick={() => setStageHidden([])}>Показать все</button>
              <button className="icon-button" onClick={resetStageHidden}>Сбросить для этапа</button>
              <button className="primary compact" onClick={() => setColumnSettingsOpen(false)}>Готово</button>
            </div>
          </div>
        </div>
      )}
      {historyRow && (
        <div className="modal-backdrop" role="presentation" onMouseDown={() => setHistoryRow(null)}>
          <div className="modal" role="dialog" aria-modal="true" aria-label="История попыток" onMouseDown={(event) => event.stopPropagation()}>
            <h2>История попыток</h2>
            <div className="timeline">
              {(historyRow.history.length ? historyRow.history : historyRow.latest_event ? [historyRow.latest_event] : []).map((event: StageTableEvent) => (
                <div className="timeline-row" key={event.id}>
                  <span>{formatDate(event.event_date)}</span>
                  <strong>{stageLabels[event.stage_type] || event.stage_type} #{event.attempt_no}</strong>
                  <em>{sourceLabels[event.source] || event.source}</em>
                </div>
              ))}
            </div>
            <div className="modal-actions">
              <button className="primary compact" onClick={() => setHistoryRow(null)}>Закрыть</button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
