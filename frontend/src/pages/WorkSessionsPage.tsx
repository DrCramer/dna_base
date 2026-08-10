import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Check, Eye, Search, X } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { api } from '../api/client'
import type { Employee, ReferenceItem, RegistrationListPreview, StageEventsPreviewRequest, StageTableRow, User, WorkProtocolObjectRow, WorkProtocolPlateCell, WorkProtocolPreview, WorkProtocolStageBlock } from '../api/types'
import { FileDropzone, PageHeader } from '../components/ui'

type DraftValue = string | number | string[] | null
type StageFieldConfig = { key: string; label: string; type?: string; performerRole?: string }
type ProtocolBlockDraft = WorkProtocolStageBlock & { enabled: boolean; performerText: string }
type RegistrationListDuplicateMode = 'block' | 'update_empty_or_existing'
type WorkSessionsMode = 'manual' | 'registration-list' | 'protocol'

const stages = [
  ['preparation', 'Пробоподготовка'],
  ['milling', 'Измельчение'],
  ['extraction', 'Выделение'],
  ['realtime', 'RealTime'],
  ['pcr', 'ПЦР'],
  ['electrophoresis', 'Электрофорез'],
  ['analysis', 'Анализ']
]

const stageLabels = Object.fromEntries(stages)

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

const dictionaryCategoryByKey: Record<string, string> = {
  extraction_method: 'extraction_method',
  quant_method: 'quant_method',
  locus_panel: 'pcr_panel',
  sequencer: 'sequencer',
  pipetting_method: 'pipetting_method',
  analysis_status: 'analysis_status'
}

function errorMessage(error: unknown) {
  return error instanceof Error ? error.message : 'Не удалось выполнить операцию'
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
  return value.split(/[\s,;]+/).map((item) => item.trim()).filter(Boolean)
}

function employeeName(employee: Employee) {
  return employee.short_name || employee.initials || employee.full_name
}

function employeesForStage(employees: Employee[], activeStage: string) {
  const active = employees.filter((employee) => employee.is_active)
  const matched = active.filter((employee) => {
    const roles = employee.stage_roles || []
    if (!roles.length) return true
    return roles.some((item) => item.is_active && (item.stage_type === activeStage || item.stage_type === canonicalStage(activeStage)))
  })
  return matched.length ? matched : active
}

function canonicalStage(stage: string) {
  if (stage === 'preparation') return 'sample_prep'
  if (stage === 'extraction') return 'dna_extraction'
  return stage
}

function listValue(value: unknown) {
  if (Array.isArray(value)) return value.map(String)
  if (typeof value === 'string') return value.split(/[,/]/).map((item) => item.trim()).filter(Boolean)
  return []
}

function stagePayloadFromValues(activeStage: string, values: Record<string, DraftValue>) {
  const detail_data: Record<string, unknown> = {}
  const performers: Array<{ raw_name?: string | null; role?: string | null; employee_id?: number | null }> = []
  const electrophoresisPerformers: string[] = []
  for (const [key, value] of Object.entries(values)) {
    const config = (stageFieldConfigs[activeStage] || []).find((item) => item.key === key)
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
  if (activeStage === 'electrophoresis' && Object.keys(values).some((key) => (stageFieldConfigs[activeStage] || []).find((item) => item.key === key)?.performerRole)) {
    detail_data.performers = electrophoresisPerformers
  }
  return { detail_data, performers }
}

function hasDraftData(values: Record<string, DraftValue>, comment: string) {
  if (comment.trim()) return true
  return Object.values(values).some((value) => {
    if (Array.isArray(value)) return value.length > 0
    if (typeof value === 'string') return value.trim() !== ''
    return value !== null && value !== undefined
  })
}

function isNoObjectRow(row: StageTableRow) {
  return row.values.no_object === true
}

function protocolBlockDraft(block: WorkProtocolStageBlock): ProtocolBlockDraft {
  return {
    ...block,
    enabled: true,
    performerText: (block.performers || []).map((item) => item.raw_name).filter(Boolean).join(', ')
  }
}

function protocolBlockPerformers(block: ProtocolBlockDraft) {
  const role = block.performers?.[0]?.role || (
    block.stage_type === 'extraction' ? 'dna_extraction'
      : block.stage_type === 'realtime' ? 'quant'
        : block.stage_type === 'pcr' ? 'pcr'
          : block.stage_type === 'electrophoresis' ? 'performer_1'
            : 'performer'
  )
  return block.performerText
    .split(/[,;/]+/)
    .map((item) => item.trim())
    .filter(Boolean)
    .map((raw_name) => ({ raw_name, role }))
}

function protocolPerformerNames(block: ProtocolBlockDraft) {
  return block.performerText
    .split(/[,;/]+/)
    .map((item) => item.trim())
    .filter(Boolean)
}

function setProtocolPerformerName(block: ProtocolBlockDraft, index: number, value: string) {
  const names = protocolPerformerNames(block)
  while (names.length <= index) names.push('')
  names[index] = value
  return names.map((item) => item.trim()).filter(Boolean).join(', ')
}

function objectWord(count: number) {
  const mod10 = count % 10
  const mod100 = count % 100
  if (mod10 === 1 && mod100 !== 11) return 'объект'
  if (mod10 >= 2 && mod10 <= 4 && (mod100 < 12 || mod100 > 14)) return 'объекта'
  return 'объектов'
}

const plateRowLabels = ['A', 'B', 'C', 'D', 'E', 'F', 'G', 'H']
const plateColumnLabels = Array.from({ length: 12 }, (_, index) => String(index + 1))

function protocolWellKey(well: string | null | undefined) {
  const match = String(well || '').trim().match(/^([A-HА-Н])\s*0?([1-9]|1[0-2])$/i)
  if (!match) return null
  const row = match[1].toUpperCase().replace('А', 'A').replace('В', 'B').replace('С', 'C').replace('Е', 'E').replace('Н', 'H')
  return `${row}${Number(match[2])}`
}

function ProtocolPlatePreview({ cells, objects }: { cells: WorkProtocolPlateCell[]; objects: WorkProtocolObjectRow[] }) {
  const matchedByWell = new Map<string, WorkProtocolObjectRow>()
  const byWell = new Map<string, WorkProtocolPlateCell | WorkProtocolObjectRow>()
  const partyCounts = new Map<string, number>()
  for (const row of objects) {
    const key = protocolWellKey(row.well)
    if (key) matchedByWell.set(key, row)
    if (row.matched && row.party_no) {
      partyCounts.set(row.party_no, (partyCounts.get(row.party_no) || 0) + 1)
    }
  }
  const sourceCells = cells.length ? cells : objects
  for (const row of sourceCells) {
    const key = protocolWellKey(row.well)
    if (key && !byWell.has(key)) byWell.set(key, row)
  }
  if (!byWell.size) return null
  const partySummary = Array.from(partyCounts.entries()).sort((left, right) => {
    const leftNo = Number(left[0])
    const rightNo = Number(right[0])
    if (Number.isFinite(leftNo) && Number.isFinite(rightNo) && leftNo !== rightNo) return rightNo - leftNo
    if (Number.isFinite(leftNo) !== Number.isFinite(rightNo)) return Number.isFinite(rightNo) ? 1 : -1
    return right[0].localeCompare(left[0], 'ru')
  })

  return (
    <div className="protocol-plate-preview">
      <div className="protocol-plate-headline">
        <div className="protocol-plate-title">Плашка объектов</div>
        <div className="protocol-plate-party-summary" aria-label="Партии назначения">
          <span className="protocol-plate-party-caption">Партии назначения</span>
          {partySummary.length ? partySummary.map(([partyNo, count]) => (
            <span className="protocol-plate-party-chip" key={partyNo}>
              № {partyNo}: {count} {objectWord(count)}
            </span>
          )) : (
            <span className="protocol-plate-party-chip is-empty">не определены</span>
          )}
        </div>
      </div>
      <div className="protocol-plate-scroll">
        <div className="protocol-plate-grid">
          <div className="protocol-plate-cell protocol-plate-head"></div>
          {plateColumnLabels.map((column) => <div className="protocol-plate-cell protocol-plate-head" key={column}>{column}</div>)}
          {plateRowLabels.map((rowLabel, rowIndex) => (
            <div className="protocol-plate-row-fragment" key={rowLabel}>
              <div className={['protocol-plate-cell', 'protocol-plate-row-head', rowIndex % 2 ? 'is-even-row' : ''].filter(Boolean).join(' ')}>{rowLabel}</div>
              {plateColumnLabels.map((column) => {
                const row = byWell.get(`${rowLabel}${column}`)
                const matchedRow = matchedByWell.get(`${rowLabel}${column}`)
                const sampleName = row?.normalized_sample_name || row?.sample_name_raw || ''
                const isService = Boolean(row && 'is_service' in row && row.is_service)
                const serviceName = isService ? String(row?.sample_name_raw || '').toLowerCase() : ''
                const title = row
                  ? [
                    row.well || `${rowLabel}${column}`,
                    sampleName,
                    isService ? 'служебная ячейка' : null,
                    matchedRow?.matched ? `объект: ${matchedRow.object_rcsme_reg_no || matchedRow.sample_object_no || '—'}` : (!isService ? 'не найден в БД' : null),
                    matchedRow?.party_no ? `партия: ${matchedRow.party_no}` : null,
                    matchedRow?.is_repeat_sample && matchedRow.parent_rcsme_reg_no ? `повтор к ${matchedRow.parent_rcsme_reg_no}` : null
                  ].filter(Boolean).join('\n')
                  : `${rowLabel}${column}`
                return (
                  <div
                    className={[
                      'protocol-plate-cell',
                      row ? 'has-sample' : '',
                      isService ? 'is-service' : '',
                      serviceName === 'ladder' ? 'is-ladder' : '',
                      serviceName === 'pc' ? 'is-pc' : '',
                      serviceName === 'nc' ? 'is-nc' : '',
                      !isService && matchedRow?.matched ? 'is-matched' : '',
                      row && !isService && !matchedRow?.matched ? 'is-unmatched' : '',
                      matchedRow?.is_repeat_sample ? 'is-repeat' : '',
                      rowIndex % 2 ? 'is-even-row' : ''
                    ].filter(Boolean).join(' ')}
                    title={title}
                    key={`${rowLabel}${column}`}
                  >
                    {sampleName ? (
                      <>
                        <span className="protocol-plate-sample">{sampleName}</span>
                        {!isService && matchedRow?.party_no ? (
                          <span className="protocol-plate-party">п. {matchedRow.party_no}</span>
                        ) : null}
                        {row && !isService && !matchedRow?.matched ? (
                          <span className="protocol-plate-party is-unmatched-label">не найден</span>
                        ) : null}
                      </>
                    ) : null}
                  </div>
                )
              })}
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}

export function WorkSessionsPage({ user }: { user: User }) {
  const queryClient = useQueryClient()
  const canEdit = user.role !== 'viewer'
  const [mode, setMode] = useState<WorkSessionsMode>('manual')
  const [partySearch, setPartySearch] = useState('')
  const [partyIds, setPartyIds] = useState<number[]>([])
  const [stageType, setStageType] = useState('extraction')
  const [objectQuery, setObjectQuery] = useState('')
  const [objectList, setObjectList] = useState('')
  const [missingList, setMissingList] = useState<string[]>([])
  const [duplicatesList, setDuplicatesList] = useState<string[]>([])
  const [selectedRows, setSelectedRows] = useState<Set<number>>(new Set())
  const [workDate, setWorkDate] = useState('')
  const [title, setTitle] = useState('')
  const [comment, setComment] = useState('')
  const [stageApplyMode, setStageApplyMode] = useState<'append' | 'update_latest'>('append')
  const [values, setValues] = useState<Record<string, DraftValue>>({})
  const [message, setMessage] = useState('')
  const [protocolPreview, setProtocolPreview] = useState<WorkProtocolPreview | null>(null)
  const [protocolBlocks, setProtocolBlocks] = useState<ProtocolBlockDraft[]>([])
  const [protocolMessage, setProtocolMessage] = useState('')
  const [registrationListFile, setRegistrationListFile] = useState<File | null>(null)
  const [registrationListPreview, setRegistrationListPreview] = useState<RegistrationListPreview | null>(null)
  const [registrationListSelectedParty, setRegistrationListSelectedParty] = useState('')
  const [registrationListMessage, setRegistrationListMessage] = useState('')
  const [registrationListMode, setRegistrationListMode] = useState<RegistrationListDuplicateMode>('block')
  const [registrationListForm, setRegistrationListForm] = useState({
    start_party_no: '',
    case_year: String(new Date().getFullYear()),
    intake_date: '',
    decision_date: '',
    investigator: '',
    incoming_no: '',
    box_no: ''
  })

  const parties = useQuery({ queryKey: ['parties', partySearch], queryFn: () => api.parties(partySearch), staleTime: 30_000 })
  const partyYears = useQuery({ queryKey: ['parties', 'years'], queryFn: api.partyYears, staleTime: 60_000 })
  const stageTable = useQuery({
    queryKey: ['mass-stage-table', partyIds, stageType, objectQuery],
    queryFn: () => api.stageTableQuery({ party_ids: partyIds, stage_type: stageType, q: objectQuery || null, filters: {}, limit: 500 }),
    enabled: partyIds.length > 0,
    staleTime: 20_000
  })
  const employees = useQuery({ queryKey: ['employees', 'active-for-stage', stageType], queryFn: () => api.employees('', null, stageType), staleTime: 60_000 })
  const protocolEmployees = useQuery({ queryKey: ['employees', 'protocol-active'], queryFn: () => api.employees('', null, null), staleTime: 60_000 })
  const referenceItems = useQuery({ queryKey: ['reference-items', 'mass-fill'], queryFn: () => api.referenceItems(), staleTime: 60_000 })
  const stageEmployees = employeesForStage(employees.data ?? [], stageType)
  const rows = stageTable.data?.rows ?? []
  const fields = stageFieldConfigs[stageType] || []
  const rowsByObjectId = useMemo(() => new Map(rows.map((row) => [row.object.id, row])), [rows])
  const selectedObjectIds = Array.from(selectedRows).filter((id) => {
    const row = rowsByObjectId.get(id)
    return !row || !isNoObjectRow(row)
  })

  const payload = useMemo<StageEventsPreviewRequest>(() => {
    const rawValues: Record<string, DraftValue> = {}
    for (const field of fields) {
      const value = values[field.key]
      if (value === null || value === undefined || value === '' || (Array.isArray(value) && !value.length)) continue
      rawValues[field.key] = field.type === 'number' && typeof value === 'string' ? Number(value) : value
    }
    const converted = stagePayloadFromValues(stageType, rawValues)
    return {
      stage_type: stageType,
      party_ids: selectedObjectIds.length ? [] : partyIds,
      object_ids: selectedObjectIds,
      q: selectedObjectIds.length ? null : objectQuery || null,
      filters: {},
      title: title || `Массовое заполнение: ${stageLabels[stageType] || stageType}`,
      work_date: workDate || null,
      comment: comment || null,
      apply_mode: stageApplyMode,
      ...converted
    }
  }, [comment, fields, objectQuery, partyIds, selectedObjectIds, stageApplyMode, stageType, title, values, workDate])

  const preview = useMutation({ mutationFn: () => api.stageEventsPreview(payload) })
  const apply = useMutation({
    mutationFn: () => api.stageEventsApply({ ...payload, source: 'manual' }),
    onSuccess: (result) => {
      setMessage(`Обработано объектов: ${result.object_count}; создано событий: ${result.stage_events_created}; обновлено: ${result.stage_events_updated}`)
      setSelectedRows(new Set())
      queryClient.invalidateQueries({ queryKey: ['party-stage-table'] })
      queryClient.invalidateQueries({ queryKey: ['mass-stage-table'] })
      queryClient.invalidateQueries({ queryKey: ['objects'] })
      queryClient.invalidateQueries({ queryKey: ['dashboard'] })
      queryClient.invalidateQueries({ queryKey: ['party-progress'] })
    }
  })
  const uploadProtocol = useMutation({
    mutationFn: api.previewWorkProtocol,
    onSuccess: (result) => {
      setProtocolPreview(result)
      setProtocolBlocks(result.stage_blocks.map(protocolBlockDraft))
      const ids = result.objects.filter((row) => row.matched && row.object_id).map((row) => row.object_id!)
      setSelectedRows(new Set(ids))
      setProtocolMessage(`Протокол прочитан: найдено ${result.matched_count}, не найдено ${result.unmatched_count}`)
    }
  })
  const applyProtocol = useMutation({
    mutationFn: async () => {
      if (!protocolPreview) return []
      const objectIds = Array.from(new Set(protocolPreview.objects.filter((row) => row.matched && row.object_id).map((row) => row.object_id!)))
      const enabledBlocks = protocolBlocks.filter((block) => block.enabled)
      const results = []
      for (const block of enabledBlocks) {
        results.push(await api.stageEventsApply({
          stage_type: block.stage_type,
          party_ids: [],
          object_ids: objectIds,
          q: null,
          filters: {},
          title: block.title || `Протокол: ${stageLabels[block.stage_type] || block.stage_type}`,
          work_date: null,
          comment: null,
          detail_data: block.detail_data,
          performers: protocolBlockPerformers(block),
          source: 'protocol_import'
        }))
      }
      return results
    },
    onSuccess: (results) => {
      const created = results.reduce((total, item) => total + item.stage_events_created, 0)
      setProtocolMessage(`Протокол применён: создано событий ${created}`)
      queryClient.invalidateQueries({ queryKey: ['party-stage-table'] })
      queryClient.invalidateQueries({ queryKey: ['mass-stage-table'] })
      queryClient.invalidateQueries({ queryKey: ['objects'] })
      queryClient.invalidateQueries({ queryKey: ['dashboard'] })
      queryClient.invalidateQueries({ queryKey: ['party-progress'] })
    }
  })
  const previewRegistrationList = useMutation({
    mutationFn: (mode: RegistrationListDuplicateMode = registrationListMode) => {
      if (!registrationListFile) throw new Error('Выберите Excel-файл общего списка')
      if (!registrationListForm.start_party_no.trim()) throw new Error('Укажите стартовую партию')
      const caseYear = Number(registrationListForm.case_year)
      if (!Number.isFinite(caseYear)) throw new Error('Укажите год')
      return api.previewRegistrationList(registrationListFile, {
        start_party_no: registrationListForm.start_party_no.trim(),
        case_year: caseYear,
        intake_date: registrationListForm.intake_date || null,
        decision_date: registrationListForm.decision_date || null,
        investigator: registrationListForm.investigator || null,
        incoming_no: registrationListForm.incoming_no || null,
        box_no: registrationListForm.box_no || null,
        duplicate_mode: mode
      })
    },
    onSuccess: (result) => {
      setRegistrationListPreview(result)
      setRegistrationListSelectedParty(result.parties[0]?.party_no || '')
      setRegistrationListMessage(`Список прочитан: ${result.party_count} партий, ${result.total_objects} объектов`)
    }
  })
  const commitRegistrationList = useMutation({
    mutationFn: () => {
      if (!registrationListPreview) throw new Error('Сначала выполните предпросмотр')
      return api.commitRegistrationList({
        upload_id: registrationListPreview.upload_id,
        start_party_no: registrationListForm.start_party_no.trim(),
        case_year: Number(registrationListForm.case_year),
        intake_date: registrationListForm.intake_date || null,
        decision_date: registrationListForm.decision_date || null,
        investigator: registrationListForm.investigator || null,
        incoming_no: registrationListForm.incoming_no || null,
        box_no: registrationListForm.box_no || null,
        duplicate_mode: registrationListMode
      })
    },
    onSuccess: (result) => {
      setRegistrationListMessage(`Импортировано: создано партий ${result.parties_created}, объектов ${result.objects_created}; обновлено объектов ${result.objects_updated}`)
      queryClient.invalidateQueries({ queryKey: ['parties'] })
      queryClient.invalidateQueries({ queryKey: ['party'] })
      queryClient.invalidateQueries({ queryKey: ['party-stage-table'] })
      queryClient.invalidateQueries({ queryKey: ['mass-stage-table'] })
      queryClient.invalidateQueries({ queryKey: ['objects'] })
      queryClient.invalidateQueries({ queryKey: ['dashboard'] })
      queryClient.invalidateQueries({ queryKey: ['party-progress'] })
    }
  })

  useEffect(() => {
    const defaultYear = partyYears.data?.default_year
    if (defaultYear && !registrationListForm.case_year) {
      setRegistrationListForm((prev) => ({ ...prev, case_year: String(defaultYear) }))
    }
  }, [partyYears.data?.default_year, registrationListForm.case_year])

  function toggleParty(id: number) {
    setPartyIds((prev) => prev.includes(id) ? prev.filter((item) => item !== id) : [...prev, id])
    setSelectedRows(new Set())
  }

  function toggleRow(row: StageTableRow) {
    if (isNoObjectRow(row)) return
    const id = row.object.id
    setSelectedRows((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  function setField(key: string, value: DraftValue) {
    setValues((prev) => ({ ...prev, [key]: value }))
    preview.reset()
    setMessage('')
  }

  function matchObjectList() {
    const source = parseObjectNoList(objectList)
    const byNumber = new Map<string, StageTableRow>()
    for (const row of rows) {
      for (const value of [row.object.rcsme_reg_no, row.values.rcsme_reg_no, row.object.decree_no]) {
        if (value) byNumber.set(normalizeObjectNo(String(value)), row)
      }
    }
    const found = new Set<number>()
    const missing: string[] = []
    const duplicates: string[] = []
    const seen = new Set<string>()
    for (const raw of source) {
      const normalized = normalizeObjectNo(raw)
      if (seen.has(normalized)) {
        duplicates.push(raw)
        continue
      }
      seen.add(normalized)
      const row = byNumber.get(normalized)
      if (row && !isNoObjectRow(row)) found.add(row.object.id)
      else missing.push(raw)
    }
    setSelectedRows(found)
    setMissingList(missing)
    setDuplicatesList(duplicates)
  }

  function dictionaryOptions(field: StageFieldConfig) {
    const category = dictionaryCategoryByKey[field.key]
    if (!category) return []
    return (referenceItems.data ?? []).filter((item) => item.category === category && item.is_active)
  }

  function dictionaryOptionNames(field: StageFieldConfig, currentValue: string) {
    const names = dictionaryOptions(field).map((item) => item.name)
    if (currentValue && !names.includes(currentValue)) return [currentValue, ...names]
    return names
  }

  function employeeOptionNames(block: ProtocolBlockDraft, currentValue: string) {
    const names = employeesForStage(protocolEmployees.data ?? [], block.stage_type).map((employee) => employee.full_name)
    if (currentValue && !names.includes(currentValue)) return [currentValue, ...names]
    return names
  }

  function renderProtocolDetailField(block: ProtocolBlockDraft, index: number, field: StageFieldConfig) {
    const rawValue = block.detail_data[field.key]
    const value = rawValue === null || rawValue === undefined ? '' : String(rawValue)
    const dict = dictionaryOptionNames(field, value)
    return (
      <label key={field.key}>{field.label}
        {dict.length ? (
          <select value={value} onChange={(event) => updateProtocolDetail(index, field.key, event.target.value)}>
            <option value="">—</option>
            {dict.map((name) => <option value={name} key={name}>{name}</option>)}
          </select>
        ) : (
          <input
            type={field.type || 'text'}
            value={value}
            onChange={(event) => updateProtocolDetail(index, field.key, event.target.value)}
          />
        )}
      </label>
    )
  }

  function renderProtocolPerformers(block: ProtocolBlockDraft, index: number) {
    const names = protocolPerformerNames(block)
    const slots = Math.max(1, names.length, block.performers?.length || 0)
    return Array.from({ length: slots }, (_, slotIndex) => {
      const value = names[slotIndex] || ''
      const options = employeeOptionNames(block, value)
      return (
        <label key={`performer-${slotIndex}`}>{slots > 1 ? `Исполнитель ${slotIndex + 1}` : 'Исполнитель'}
          <select
            value={value}
            onChange={(event) => updateProtocolBlock(index, { performerText: setProtocolPerformerName(block, slotIndex, event.target.value) })}
          >
            <option value="">—</option>
            {options.map((name) => <option value={name} key={name}>{name}</option>)}
          </select>
        </label>
      )
    })
  }

  function updateProtocolBlock(index: number, patch: Partial<ProtocolBlockDraft>) {
    setProtocolBlocks((prev) => prev.map((block, i) => i === index ? { ...block, ...patch } : block))
  }

  function updateProtocolDetail(index: number, key: string, value: string) {
    setProtocolBlocks((prev) => prev.map((block, i) => i === index ? { ...block, detail_data: { ...block.detail_data, [key]: value || null } } : block))
  }

  function setRegistrationListField(key: keyof typeof registrationListForm, value: string) {
    setRegistrationListForm((prev) => ({ ...prev, [key]: value }))
    setRegistrationListPreview(null)
    setRegistrationListMessage('')
  }

  function chooseRegistrationListMode(mode: RegistrationListDuplicateMode) {
    setRegistrationListMode(mode)
    if (registrationListFile && registrationListForm.start_party_no.trim()) {
      previewRegistrationList.mutate(mode)
    }
  }

  const canApply = canEdit && partyIds.length > 0 && hasDraftData(values, comment)
  const canApplyProtocol = canEdit && protocolPreview && protocolPreview.matched_count > 0 && protocolBlocks.some((block) => block.enabled)
  const selectedRegistrationPreviewParty = registrationListPreview?.parties.find((party) => party.party_no === registrationListSelectedParty) || registrationListPreview?.parties[0]
  const canCommitRegistrationList = canEdit && Boolean(registrationListPreview) && !registrationListPreview?.conflicts.length && !commitRegistrationList.isPending

  return (
    <div className="page">
      <PageHeader
        title="Массовое заполнение"
        description="Заполняйте выбранные этапы по нескольким партиям, импортируйте общий список или применяйте протокол плашки после проверки."
      />
      <div className="tabs mode-tabs">
        <button className={mode === 'manual' ? 'active' : ''} onClick={() => setMode('manual')}>Заполнить этап вручную</button>
        <button className={mode === 'registration-list' ? 'active' : ''} onClick={() => setMode('registration-list')}>Импорт общего списка</button>
        <button className={mode === 'protocol' ? 'active' : ''} onClick={() => setMode('protocol')}>Импорт протокола плашки</button>
      </div>

      {mode === 'registration-list' && <section className="section registration-list-import">
        <h2>Импорт общего списка</h2>
        <div className="registration-list-layout">
          <FileDropzone
            title={registrationListFile ? registrationListFile.name : 'Перетащите общий список сюда'}
            description="или нажмите для выбора Excel-файла"
            formats=".xlsx"
            accept=".xlsx"
            disabled={!canEdit}
            className="registration-list-drop"
            onFiles={(files) => {
              setRegistrationListFile(files[0] || null)
              setRegistrationListPreview(null)
              setRegistrationListMessage('')
              setRegistrationListMode('block')
            }}
          />
          <div className="form-grid flat registration-list-form">
            <label>Стартовая партия
              <input value={registrationListForm.start_party_no} onChange={(event) => setRegistrationListField('start_party_no', event.target.value)} placeholder="181" />
            </label>
            <label>Год
              <select value={registrationListForm.case_year} onChange={(event) => setRegistrationListField('case_year', event.target.value)}>
                {Array.from(new Set([...(partyYears.data?.years ?? []), Number(registrationListForm.case_year) || new Date().getFullYear()]))
                  .filter(Boolean)
                  .sort((left, right) => right - left)
                  .map((year) => <option value={year} key={year}>{year}</option>)}
              </select>
            </label>
            <label>Дата поступления в РЦСМЭ
              <input type="date" value={registrationListForm.intake_date} onChange={(event) => setRegistrationListField('intake_date', event.target.value)} />
            </label>
            <label>Дата постановления
              <input type="date" value={registrationListForm.decision_date} onChange={(event) => setRegistrationListField('decision_date', event.target.value)} />
            </label>
            <label>Следователь
              <input value={registrationListForm.investigator} onChange={(event) => setRegistrationListField('investigator', event.target.value)} />
            </label>
            <label>№ вх.
              <input value={registrationListForm.incoming_no} onChange={(event) => setRegistrationListField('incoming_no', event.target.value)} />
            </label>
            <label>Коробка
              <input value={registrationListForm.box_no} onChange={(event) => setRegistrationListField('box_no', event.target.value)} />
            </label>
          </div>
        </div>
        <div className="toolbar-actions">
          <button
            className="icon-button"
            disabled={!canEdit || !registrationListFile || !registrationListForm.start_party_no.trim() || previewRegistrationList.isPending}
            onClick={() => previewRegistrationList.mutate(registrationListMode)}
          >
            <Eye size={18} />Предпросмотр списка
          </button>
          <button
            className="primary compact"
            disabled={!canCommitRegistrationList}
            onClick={() => commitRegistrationList.mutate()}
          >
            <Check size={18} />Импортировать доступные
          </button>
          {registrationListMessage && <span className="alert success">{registrationListMessage}</span>}
        </div>
        {(previewRegistrationList.error || commitRegistrationList.error) && (
          <div className="alert error">{errorMessage(previewRegistrationList.error || commitRegistrationList.error)}</div>
        )}
        {registrationListPreview && (
          <div className="registration-list-preview">
            <div className="overview-grid">
              <div><span>Партий</span><strong>{registrationListPreview.party_count}</strong></div>
              <div><span>Объектов</span><strong>{registrationListPreview.total_objects}</strong></div>
              <div><span>Будет создано партий</span><strong>{registrationListPreview.parties_to_create}</strong></div>
              <div><span>Существующих партий</span><strong>{registrationListPreview.existing_parties}</strong></div>
              <div><span>Старт № РЦСМЭ</span><strong>{registrationListPreview.suggested_start_rcsme_reg_no}</strong></div>
            </div>
            {registrationListPreview.previous_party_no && (
              <div className="inline-summary">
                После партии {registrationListPreview.previous_party_no}: {registrationListPreview.previous_last_rcsme_reg_no || '—'}
              </div>
            )}
            {registrationListPreview.conflicts.length > 0 && (
              <div className="registry-replace-panel">
                <div>
                  <strong>Существующие партии</strong>
                  <span>Найдены партии с объектами. Для обновлённого общего списка выберите явное обновление.</span>
                </div>
                <button className="primary compact" onClick={() => chooseRegistrationListMode('update_empty_or_existing')}>
                  Обновить существующие партии
                </button>
              </div>
            )}
            {registrationListMode === 'update_empty_or_existing' && !registrationListPreview.conflicts.length && (
              <div className="registry-replace-panel selected">
                <div>
                  <strong>Обновление выбрано</strong>
                  <span>Существующие объекты будут обновлены по порядку, недостающие строки будут созданы.</span>
                </div>
                <button className="icon-button" onClick={() => chooseRegistrationListMode('block')}>Отменить обновление</button>
              </div>
            )}
            {registrationListPreview.warnings.map((warning) => <div className="alert" key={warning}>{warning}</div>)}
            <div className="registration-list-table-wrap">
              <table className="registration-list-table">
                <thead>
                  <tr>
                    <th>Партия</th>
                    <th>Колонка</th>
                    <th>Объектов</th>
                    <th>Первый № рег РЦСМЭ</th>
                    <th>Последний № рег РЦСМЭ</th>
                    <th>№ в в/ч №522</th>
                    <th>Статус</th>
                  </tr>
                </thead>
                <tbody>
                  {registrationListPreview.parties.map((party) => (
                    <tr
                      className={party.party_no === selectedRegistrationPreviewParty?.party_no ? 'is-selected' : ''}
                      key={party.party_no}
                      onClick={() => setRegistrationListSelectedParty(party.party_no)}
                    >
                      <td>№ {party.party_no}</td>
                      <td>{party.column_letter}</td>
                      <td>{party.object_count}</td>
                      <td>{party.first_rcsme_reg_no || '—'}</td>
                      <td>{party.last_rcsme_reg_no || '—'}</td>
                      <td>{party.first_external_military_no || '—'} → {party.last_external_military_no || '—'}</td>
                      <td>{party.status}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {selectedRegistrationPreviewParty && (
              <div className="registration-list-sample">
                <div className="summary-line">
                  <strong>Партия {selectedRegistrationPreviewParty.party_no}</strong>
                  <span>{selectedRegistrationPreviewParty.object_count} {objectWord(selectedRegistrationPreviewParty.object_count)}</span>
                  {selectedRegistrationPreviewParty.warnings.map((warning) => <span className="alert" key={warning}>{warning}</span>)}
                </div>
                <div className="registration-list-table-wrap compact">
                  <table className="registration-list-table">
                    <thead>
                      <tr>
                        <th>№ п/п</th>
                        <th>№ рег РЦСМЭ</th>
                        <th>№ постановления</th>
                        <th>№ в в/ч №522</th>
                        <th>Дата поступления</th>
                        <th>Дата постановления</th>
                        <th>Следователь</th>
                        <th>№ вх.</th>
                        <th>Коробка</th>
                      </tr>
                    </thead>
                    <tbody>
                      {selectedRegistrationPreviewParty.sample_rows.map((row) => (
                        <tr key={`${selectedRegistrationPreviewParty.party_no}-${row.index}`}>
                          <td>{row.index}</td>
                          <td>{row.rcsme_reg_no}</td>
                          <td>{row.decree_no}</td>
                          <td>{row.external_military_no || '—'}</td>
                          <td>{row.intake_date || '—'}</td>
                          <td>{row.decision_date || '—'}</td>
                          <td>{row.investigator || '—'}</td>
                          <td>{row.incoming_no || '—'}</td>
                          <td>{row.box_no || '—'}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}
          </div>
        )}
      </section>}

      {mode === 'protocol' && <section className="section">
        <h2>Импорт протокола плашки</h2>
        <FileDropzone
          title="Перетащите Excel-протокол сюда"
          description="или нажмите для выбора протокола плашки"
          formats=".xlsx"
          accept=".xlsx"
          disabled={!canEdit}
          onFiles={(files) => files[0] && uploadProtocol.mutate(files[0])}
        />
        {uploadProtocol.error && <div className="alert error">{errorMessage(uploadProtocol.error)}</div>}
        {protocolPreview && (
          <div className="protocol-preview">
            <div className="summary-line">
              <strong>{protocolPreview.protocol_name || protocolPreview.filename}</strong>
              <span>№ {protocolPreview.protocol_no || '—'}</span>
              <span>{protocolPreview.matched_count} найдено</span>
              <span>{protocolPreview.unmatched_count} не найдено</span>
              <span>{protocolPreview.repeat_count} повторов</span>
            </div>
            {protocolPreview.warnings.map((warning) => <div className="alert" key={warning}>{warning}</div>)}
            <div className="protocol-blocks">
              {protocolBlocks.map((block, index) => (
                <div className="protocol-block" key={`${block.stage_type}-${index}`}>
                  <label className="inline-check">
                    <input type="checkbox" checked={block.enabled} onChange={(event) => updateProtocolBlock(index, { enabled: event.target.checked })} />
                    <strong>{stageLabels[block.stage_type] || block.stage_type}</strong>
                  </label>
                  <input value={block.title} onChange={(event) => updateProtocolBlock(index, { title: event.target.value })} />
                  <div className="form-grid flat">
                    {(stageFieldConfigs[block.stage_type] || []).filter((field) => !field.performerRole).map((field) => renderProtocolDetailField(block, index, field))}
                    {renderProtocolPerformers(block, index)}
                  </div>
                </div>
              ))}
            </div>
            <ProtocolPlatePreview cells={protocolPreview.plate_cells || []} objects={protocolPreview.objects} />
            {protocolPreview.unmatched_count > 0 && (
              <div className="alert error">
                Не найдены: {protocolPreview.objects.filter((row) => !row.matched).slice(0, 30).map((row) => row.normalized_sample_name || row.sample_name_raw).join(', ')}
              </div>
            )}
            <div className="modal-actions">
              <button className="primary compact" disabled={!canApplyProtocol || applyProtocol.isPending} onClick={() => applyProtocol.mutate()}><Check size={18} />Применить выбранные этапы</button>
              {protocolMessage && <span className="alert success">{protocolMessage}</span>}
            </div>
            {applyProtocol.error && <div className="alert error">{errorMessage(applyProtocol.error)}</div>}
          </div>
        )}
      </section>}

      {mode === 'manual' && <div className="split-layout">
        <section className="section">
          <h2>Партии и объекты</h2>
          <div className="searchbox"><Search size={18} /><input value={partySearch} onChange={(event) => setPartySearch(event.target.value)} placeholder="Поиск партии" /></div>
          <div className="check-list compact-check-list">
            {(parties.data?.items ?? []).map((party) => (
              <label key={party.id}>
                <input type="checkbox" checked={partyIds.includes(party.id)} onChange={() => toggleParty(party.id)} />
                <span>{party.party_no}</span>
                <em>{party.object_count}</em>
              </label>
            ))}
          </div>
          <label className="wide">Список объектов
            <textarea value={objectList} onChange={(event) => setObjectList(event.target.value)} placeholder={'310-1\n311-1\n312-1'} />
          </label>
          <div className="toolbar-actions">
            <button className="icon-button" disabled={!rows.length || !objectList.trim()} onClick={matchObjectList}><Search size={18} />Найти в выбранных партиях</button>
            <button className="icon-button" onClick={() => { setObjectList(''); setMissingList([]); setDuplicatesList([]); setSelectedRows(new Set()) }}><X size={18} />Очистить</button>
          </div>
          {(missingList.length > 0 || duplicatesList.length > 0) && (
            <div className="alert">
              {missingList.length > 0 && <span>Не найдены: {missingList.join(', ')}. </span>}
              {duplicatesList.length > 0 && <span>Дубликаты: {duplicatesList.join(', ')}</span>}
            </div>
          )}
        </section>

        <section className="section">
          <h2>Поля этапа</h2>
          <div className="form-grid flat">
            <label>Этап
              <select value={stageType} onChange={(event) => { setStageType(event.target.value); setValues({}); setSelectedRows(new Set()) }}>
                {stages.map(([value, label]) => <option value={value} key={value}>{label}</option>)}
              </select>
            </label>
            <label>Режим
              <select value={stageApplyMode} onChange={(event) => setStageApplyMode(event.target.value as 'append' | 'update_latest')}>
                <option value="append">Добавить новую попытку</option>
                <option value="update_latest">Обновить текущие данные</option>
              </select>
            </label>
            <label>Поиск по таблице<input value={objectQuery} onChange={(event) => setObjectQuery(event.target.value)} placeholder="номер, тип, исполнитель..." /></label>
            <label>Дата работы<input type="date" value={workDate} onChange={(event) => setWorkDate(event.target.value)} /></label>
            <label>Название<input value={title} onChange={(event) => setTitle(event.target.value)} placeholder="Массовое заполнение этапа" /></label>
            {fields.map((field) => {
              const value = values[field.key]
              const dict = dictionaryOptions(field)
              return (
                <label key={field.key}>{field.label}
                  {field.performerRole ? (
                    <select value={Array.isArray(value) ? value[0] || '' : String(value || '')} onChange={(event) => setField(field.key, event.target.value)}>
                      <option value="">—</option>
                      {stageEmployees.map((employee) => <option value={employee.full_name} key={employee.id}>{employeeName(employee)}</option>)}
                    </select>
                  ) : dict.length ? (
                    <select value={String(value || '')} onChange={(event) => setField(field.key, event.target.value)}>
                      <option value="">—</option>
                      {dict.map((item: ReferenceItem) => <option value={item.name} key={item.id}>{item.short_name || item.name}</option>)}
                    </select>
                  ) : (
                    <input type={field.type || 'text'} value={Array.isArray(value) ? value.join(', ') : String(value || '')} onChange={(event) => setField(field.key, event.target.value)} />
                  )}
                </label>
              )
            })}
            <label className="wide">Комментарий<textarea value={comment} onChange={(event) => setComment(event.target.value)} /></label>
          </div>
          <div className="summary-line">
            <button className="icon-button" disabled={!partyIds.length || preview.isPending} onClick={() => preview.mutate()}><Eye size={18} />Предпросмотр</button>
            <button className="primary compact" disabled={!canApply || apply.isPending} onClick={() => apply.mutate()}><Check size={18} />Применить</button>
            <span>{selectedRows.size ? `${selectedRows.size} выбранных` : partyIds.length ? `по фильтру: ${stageTable.data?.total ?? 0} ${objectWord(stageTable.data?.total ?? 0)}` : 'выберите партии'}</span>
          </div>
          {preview.data && (
            <div className="overview-grid">
              <div><span>Объектов</span><strong>{preview.data.object_count}</strong></div>
              <div><span>Первая попытка</span><strong>{preview.data.objects_without_stage}</strong></div>
              <div><span>Повтор</span><strong>{preview.data.objects_with_existing_stage}</strong></div>
              <div><span>Будущие попытки</span><strong>{preview.data.next_attempt_min}-{preview.data.next_attempt_max}</strong></div>
            </div>
          )}
          {preview.data?.warnings.map((warning) => <div className="alert" key={warning}>{warning}</div>)}
          {message && <div className="alert success">{message}</div>}
          {(preview.error || apply.error) && <div className="alert error">{errorMessage(preview.error || apply.error)}</div>}
        </section>
      </div>}

      {mode === 'manual' && <section className="section">
        <h2>Объекты выбранных партий</h2>
        <div className="mass-object-table">
          <div className="mass-object-row mass-object-head">
            <div></div><div>№ рег РЦСМЭ</div><div>Партия</div><div>Нет объекта</div><div>Нет постановления</div><div>Горелая кость</div><div>Тип</div><div>Попытка</div>
          </div>
          {rows.slice(0, 300).map((row) => (
            <div className={`mass-object-row ${isNoObjectRow(row) ? 'no-object-row' : ''}`} key={row.object.id}>
              <div><input type="checkbox" checked={!isNoObjectRow(row) && selectedRows.has(row.object.id)} disabled={isNoObjectRow(row)} onChange={() => toggleRow(row)} /></div>
              <div>{String(row.values.rcsme_reg_no || row.object.rcsme_reg_no || '—')}</div>
              <div>{row.object.party_no || '—'}</div>
              <div>{isNoObjectRow(row) ? 'Да' : '—'}</div>
              <div>{row.values.no_decree === true ? 'Да' : '—'}</div>
              <div>{row.values.burnt_bone === true ? 'Да' : '—'}</div>
              <div>{String(row.values.object_type || row.object.object_type || '—')}</div>
              <div>{row.attempt_no || '—'}</div>
            </div>
          ))}
          {!rows.length && <div className="empty">{partyIds.length ? 'Объекты не найдены' : 'Выберите партии'}</div>}
        </div>
      </section>}
    </div>
  )
}
