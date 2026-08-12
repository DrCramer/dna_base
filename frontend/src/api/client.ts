import type {
  CommitResponse,
  Dashboard,
  Employee,
  ElectrophoresisPdfCommitResponse,
  ElectrophoresisPdfPreview,
  ObjectList,
  Party,
  PartyList,
  PartyPermanentDeleteResponse,
  PartyYears,
  PartyProgress,
  PartyControlReport,
  PerformerStatisticsReport,
  PeriodStatisticsReport,
  RcsmeFixApplyResponse,
  RcsmeFixPreview,
  RegistrationBulkApplyResponse,
  RegistrationBulkPreview,
  RegistrationBulkRequest,
  RegistrationListCommitResponse,
  RegistrationListPreview,
  RegistryObject,
  RegistryExportPreview,
  RegistryPreview,
  ReferenceItem,
  RtCommitResponse,
  RtPreview,
  ReportOverview,
  StageEventsApplyResponse,
  StageEventsInlineApplyRequest,
  StageEventsInlineApplyResponse,
  StageEventsPreview,
  StageEventsPreviewRequest,
  StageTable,
  StageTableQueryRequest,
  User,
  WorkSessionCommitResponse,
  WorkSessionPreview,
  WorkSessionPreviewRequest,
  WorkProtocolPreview
} from './types'

const API = '/api'

function apiBases(): string[] {
  const { protocol, hostname, port, pathname } = window.location
  const bases = [API]
  const prefix = pathname.endsWith('/') ? pathname.slice(0, -1) : pathname.replace(/\/[^/]*$/, '')
  if (prefix) {
    bases.unshift(`${prefix}/api`)
  }
  const isViteDevServer = port === '5173'
  if (isViteDevServer) {
    for (const candidatePort of ['4001', '4000']) {
      if (port !== candidatePort && hostname) {
        bases.push(`${protocol}//${hostname}:${candidatePort}/api`)
        if (protocol !== 'http:') {
          bases.push(`http://${hostname}:${candidatePort}/api`)
        }
      }
    }
  }
  return Array.from(new Set(bases))
}

function requestUrl(base: string, path: string): string {
  return `${base.replace(/\/$/, '')}${path}`
}

function firstApiBase(): string {
  return apiBases()[0]
}

function reportParams(filters: Record<string, string | number | boolean | null | undefined>) {
  const params = new URLSearchParams()
  Object.entries(filters).forEach(([key, value]) => {
    if (value === undefined || value === null || value === '') return
    params.set(key, String(value))
  })
  return params
}

export type RegistryExportOptions = {
  q?: string
  partyNo?: string | null
  partyIds?: number[]
  objectIds?: number[]
  objectNos?: string
  year?: number | null
  stageType?: string | null
  includeArchived?: boolean
  onlyProblematic?: boolean
}

function registryExportParams(options: RegistryExportOptions) {
  const params = new URLSearchParams()
  if (options.q) params.set('q', options.q)
  if (options.partyNo) params.set('party_no', options.partyNo)
  if (options.partyIds) params.set('party_ids', options.partyIds.join(','))
  if (options.objectIds) params.set('object_ids', options.objectIds.join(','))
  if (options.objectNos !== undefined) params.set('object_nos', options.objectNos)
  if (options.year) params.set('year', String(options.year))
  if (options.stageType) params.set('stage_type', options.stageType)
  if (options.includeArchived) params.set('include_archived', 'true')
  if (options.onlyProblematic) params.set('only_problematic', 'true')
  return params
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const attempted: string[] = []
  let lastMessage = 'Ошибка запроса'

  for (const base of apiBases()) {
    const url = requestUrl(base, path)
    attempted.push(url)
    let response: Response
    try {
      response = await fetch(url, {
        ...init,
        credentials: 'include',
        headers: init?.body instanceof FormData ? init.headers : { 'Content-Type': 'application/json', ...init?.headers }
      })
    } catch (error) {
      lastMessage = error instanceof Error ? error.message : 'Не удалось подключиться к API'
      continue
    }

    const contentType = response.headers.get('content-type') || ''
    const body = await response.text()
    const parseJson = () => {
      if (!body.trim()) return null
      if (!contentType.includes('application/json')) return null
      try {
        return JSON.parse(body)
      } catch {
        return null
      }
    }
    const payload = parseJson()

    if (!response.ok) {
      const detail = payload?.detail || payload?.error
      if (detail) throw new Error(detail)
      const message = !body.trim()
        ? "Сервер вернул пустой ответ (" + response.status + ")"
        : "Сервер вернул не JSON (" + response.status + ")"
      throw new Error(message)
    }

    if (response.status === 204) return undefined as T
    if (payload !== null) return payload as T

    lastMessage = 'Сервер вернул пустой или не JSON ответ'
  }

  throw new Error(`${lastMessage}. API не найден: ${attempted.join(', ')}`)
}

export const api = {
  me: () => request<User>('/auth/me'),
  login: (username: string, password: string) =>
    request<{ user: User }>('/auth/login', { method: 'POST', body: JSON.stringify({ username, password }) }),
  logout: () => request('/auth/logout', { method: 'POST' }),
  dashboard: () => request<Dashboard>('/dashboard'),
  reportOverview: (filters: Record<string, string | number | boolean | null | undefined>) =>
    request<ReportOverview>(`/reports/overview?${reportParams(filters).toString()}`),
  reportPartyControl: (filters: Record<string, string | number | boolean | null | undefined>) =>
    request<PartyControlReport>(`/reports/party-control?${reportParams(filters).toString()}`),
  reportWorkProgress: (filters: Record<string, string | number | boolean | null | undefined>) =>
    request<ReportOverview>(`/reports/work-progress?${reportParams(filters).toString()}`),
  reportStatistics: (period: 'weekly' | 'monthly' | 'yearly', filters: Record<string, string | number | boolean | null | undefined>) =>
    request<PeriodStatisticsReport>(`/reports/statistics/${period}?${reportParams(filters).toString()}`),
  reportPerformers: (filters: Record<string, string | number | boolean | null | undefined>) =>
    request<PerformerStatisticsReport>(`/reports/performers?${reportParams(filters).toString()}`),
  reportExportUrl: (report: string, filters: Record<string, string | number | boolean | null | undefined>) =>
    `${API}/reports/export?${reportParams({ ...filters, report }).toString()}`,
  objects: (q: string, partyNo?: string | null, year?: number | null) => {
    const params = new URLSearchParams()
    if (q) params.set('q', q)
    if (partyNo) params.set('party_no', partyNo)
    if (year) params.set('year', String(year))
    return request<ObjectList>(`/objects?${params.toString()}`)
  },
  object: (id: number) => request<RegistryObject>(`/objects/${id}`),
  createObject: (payload: Partial<RegistryObject>) =>
    request<RegistryObject>('/objects', { method: 'POST', body: JSON.stringify(payload) }),
  updateObject: (id: number, patch: Partial<RegistryObject>) =>
    request<RegistryObject>(`/objects/${id}`, { method: 'PATCH', body: JSON.stringify(patch) }),
  archiveObject: (id: number) =>
    request<RegistryObject>(`/objects/${id}/archive`, { method: 'POST' }),
  partyYears: () => request<PartyYears>('/parties/years'),
  parties: (q = '', includeArchived = false, year?: number | null) => {
    const params = new URLSearchParams()
    if (q) params.set('q', q)
    if (includeArchived) params.set('include_archived', 'true')
    if (year) params.set('year', String(year))
    return request<PartyList>(`/parties?${params.toString()}`)
  },
  party: (id: number) => request<Party>(`/parties/${id}`),
  partyObjects: (id: number, q = '') => {
    const params = new URLSearchParams()
    if (q) params.set('q', q)
    return request<ObjectList>(`/parties/${id}/objects?${params.toString()}`)
  },
  partyStageTable: (id: number, stageType: string, q = '', quick = '', showHistory = false) => {
    const params = new URLSearchParams()
    if (q) params.set('q', q)
    if (quick) params.set('quick', quick)
    if (showHistory) params.set('show_history', 'true')
    return request<StageTable>(`/parties/${id}/stage-table/${stageType}?${params.toString()}`)
  },
  stageTableQuery: (payload: StageTableQueryRequest) =>
    request<StageTable>('/stage-table/query', { method: 'POST', body: JSON.stringify(payload) }),
  partyProgress: (id: number) => request<PartyProgress>(`/parties/${id}/progress`),
  createParty: (payload: { party_no: string; case_year?: number | null; title?: string | null; comment?: string | null; status?: string }) =>
    request<Party>('/parties', { method: 'POST', body: JSON.stringify(payload) }),
  updateParty: (id: number, payload: Partial<Party>) =>
    request<Party>(`/parties/${id}`, { method: 'PATCH', body: JSON.stringify(payload) }),
  archiveParty: (id: number) =>
    request<Party>(`/parties/${id}`, { method: 'PATCH', body: JSON.stringify({ status: 'archived' }) }),
  deletePartyPermanent: (id: number) =>
    request<PartyPermanentDeleteResponse>(`/parties/${id}`, { method: 'DELETE' }),
  registrationBulkPreview: (partyId: number, payload: RegistrationBulkRequest) =>
    request<RegistrationBulkPreview>(`/parties/${partyId}/registration-bulk/preview`, { method: 'POST', body: JSON.stringify(payload) }),
  registrationBulkApply: (partyId: number, payload: RegistrationBulkRequest) =>
    request<RegistrationBulkApplyResponse>(`/parties/${partyId}/registration-bulk/apply`, { method: 'POST', body: JSON.stringify(payload) }),
  previewRegistrationList: (file: File, payload: {
    start_party_no: string
    case_year: number
    intake_date?: string | null
    decision_date?: string | null
    investigator?: string | null
    incoming_no?: string | null
    box_no?: string | null
    duplicate_mode?: 'block' | 'update_empty_or_existing'
  }) => {
    const data = new FormData()
    data.append('file', file)
    data.append('start_party_no', payload.start_party_no)
    data.append('case_year', String(payload.case_year))
    if (payload.intake_date) data.append('intake_date', payload.intake_date)
    if (payload.decision_date) data.append('decision_date', payload.decision_date)
    if (payload.investigator) data.append('investigator', payload.investigator)
    if (payload.incoming_no) data.append('incoming_no', payload.incoming_no)
    if (payload.box_no) data.append('box_no', payload.box_no)
    if (payload.duplicate_mode) data.append('duplicate_mode', payload.duplicate_mode)
    return request<RegistrationListPreview>('/imports/registration-list/preview', { method: 'POST', body: data })
  },
  commitRegistrationList: (payload: {
    upload_id: string
    start_party_no: string
    case_year: number
    intake_date?: string | null
    decision_date?: string | null
    investigator?: string | null
    incoming_no?: string | null
    box_no?: string | null
    duplicate_mode?: 'block' | 'update_empty_or_existing'
  }) =>
    request<RegistrationListCommitResponse>('/imports/registration-list/commit', { method: 'POST', body: JSON.stringify(payload) }),
  workSessionPreview: (payload: WorkSessionPreviewRequest) =>
    request<WorkSessionPreview>('/work-sessions/preview', { method: 'POST', body: JSON.stringify(payload) }),
  workSessionCommit: (payload: WorkSessionPreviewRequest & { source?: string }) =>
    request<WorkSessionCommitResponse>('/work-sessions/commit', { method: 'POST', body: JSON.stringify(payload) }),
  stageEventsPreview: (payload: StageEventsPreviewRequest) =>
    request<StageEventsPreview>('/stage-events/preview', { method: 'POST', body: JSON.stringify(payload) }),
  stageEventsApply: (payload: StageEventsPreviewRequest & { source?: string }) =>
    request<StageEventsApplyResponse>('/stage-events/apply', { method: 'POST', body: JSON.stringify(payload) }),
  stageEventsApplyInline: (payload: StageEventsInlineApplyRequest) =>
    request<StageEventsInlineApplyResponse>('/stage-events/apply-inline', { method: 'POST', body: JSON.stringify(payload) }),
  employees: (q = '', verified?: boolean | null, stageType?: string | null, role?: string | null, includeInactive = false) => {
    const params = new URLSearchParams()
    if (q) params.set('q', q)
    if (verified !== undefined && verified !== null) params.set('verified', String(verified))
    if (stageType) params.set('stage_type', stageType)
    if (role) params.set('role', role)
    if (includeInactive) params.set('include_inactive', 'true')
    return request<Employee[]>(`/employees?${params.toString()}`)
  },
  createEmployee: (payload: Partial<Omit<Employee, 'stage_roles'>> & { full_name: string; stage_roles?: string[] }) =>
    request<Employee>('/employees', { method: 'POST', body: JSON.stringify(payload) }),
  updateEmployee: (id: number, payload: Partial<Omit<Employee, 'stage_roles'>> & { stage_roles?: string[] }) =>
    request<Employee>(`/employees/${id}`, { method: 'PATCH', body: JSON.stringify(payload) }),
  referenceItems: (category = '', q = '', includeInactive = false) => {
    const params = new URLSearchParams()
    if (category) params.set('category', category)
    if (q) params.set('q', q)
    if (includeInactive) params.set('include_inactive', 'true')
    return request<ReferenceItem[]>(`/reference-items?${params.toString()}`)
  },
  createReferenceItem: (payload: Partial<ReferenceItem> & { category: string; name: string }) =>
    request<ReferenceItem>('/reference-items', { method: 'POST', body: JSON.stringify(payload) }),
  updateReferenceItem: (id: number, payload: Partial<ReferenceItem>) =>
    request<ReferenceItem>(`/reference-items/${id}`, { method: 'PATCH', body: JSON.stringify(payload) }),
  previewRegistry: (file: File) => {
    const data = new FormData()
    data.append('file', file)
    return request<RegistryPreview>('/imports/registry/preview', { method: 'POST', body: data })
  },
  commitRegistry: (upload_id: string, duplicate_mode: 'block' | 'replace' = 'block') =>
    request<CommitResponse>('/imports/registry/commit', { method: 'POST', body: JSON.stringify({ upload_id, duplicate_mode }) }),
  previewRt: (file: File) => {
    const data = new FormData()
    data.append('file', file)
    return request<RtPreview>('/imports/rt/preview', { method: 'POST', body: data })
  },
  commitRt: (payload: { upload_id: string; quant_performer?: string | null; employee_id?: number | null; duplicate_mode?: 'block' | 'replace' | 'append' }) =>
    request<RtCommitResponse>('/imports/rt/commit', { method: 'POST', body: JSON.stringify(payload) }),
  previewElectrophoresisPdf: (files: File[], caseYear?: number | null, controlPartyIds: number[] = []) => {
    const data = new FormData()
    files.forEach((file) => data.append('files', file))
    if (caseYear) data.append('case_year', String(caseYear))
    controlPartyIds.forEach((partyId) => data.append('control_party_ids', String(partyId)))
    return request<ElectrophoresisPdfPreview>('/imports/electrophoresis-pdf/preview', { method: 'POST', body: data })
  },
  commitElectrophoresisPdf: (payload: {
    upload_ids: string[]
    case_year?: number | null
    party_id?: number | null
    control_party_ids?: number[] | null
    duplicate_mode?: 'block' | 'replace' | 'append'
    file_modes?: Record<string, 'block' | 'replace' | 'append'>
    analysis_date?: string | null
    analysis_performer?: string | null
    employee_id?: number | null
  }) =>
    request<ElectrophoresisPdfCommitResponse>('/imports/electrophoresis-pdf/commit', { method: 'POST', body: JSON.stringify(payload) }),
  previewWorkProtocol: (file: File) => {
    const data = new FormData()
    data.append('file', file)
    return request<WorkProtocolPreview>('/imports/work-protocol/preview', { method: 'POST', body: data })
  },
  rcsmeFixPreview: () => request<RcsmeFixPreview>('/imports/registry/rcsme-fix/preview'),
  rcsmeFixApply: () => request<RcsmeFixApplyResponse>('/imports/registry/rcsme-fix/apply', { method: 'POST' }),
  electrophoresisFileUrl: (id: number | string, download = false) =>
    requestUrl(firstApiBase(), `/electrophoresis-files/${id}${download ? '?download=true' : ''}`),
  exportRegistryPreview: (options: RegistryExportOptions) =>
    request<RegistryExportPreview>(`/exports/registry/preview?${registryExportParams(options).toString()}`),
  exportRegistryUrl: (optionsOrQuery: RegistryExportOptions | string, partyNo?: string | null, year?: number | null) => {
    const options = typeof optionsOrQuery === 'string'
      ? { q: optionsOrQuery, partyNo, year }
      : optionsOrQuery
    return `${API}/exports/registry.xlsx?${registryExportParams(options).toString()}`
  }
}
