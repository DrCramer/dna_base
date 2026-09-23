import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ArrowLeft, Check, Download, Eye, FilePenLine, Printer, Save } from 'lucide-react'
import { useEffect, useMemo, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { api } from '../api/client'
import type { Protocol, ProtocolPayload, ProtocolPlateRules, ProtocolPreview, ProtocolStageSettings, ProtocolStageType, User } from '../api/types'
import { ProtocolObjectSelector } from '../components/protocols/ProtocolObjectSelector'
import { ProtocolPrintDocument } from '../components/protocols/ProtocolPrintDocument'
import { ProtocolSheet } from '../components/protocols/ProtocolSheet'
import { ErrorState, LoadingState, PageHeader } from '../components/ui'

const today = () => new Date().toISOString().slice(0, 10)
const stageTypes: ProtocolStageSettings['stage_type'][] = ['dna_extraction', 'realtime', 'pcr', 'electrophoresis']
const defaultRules: ProtocolPlateRules = { rows: 8, columns: 12, fill_order: 'column', ladder_enabled: false, ladder_wells: ['A1', 'A3', 'A5', 'A7', 'A9', 'A11'], pc_enabled: false, nc_enabled: true }

function initialStages(protocolDate: string): ProtocolStageSettings[] {
  return stageTypes.map((stage_type) => ({ stage_type, enabled: true, work_date: protocolDate, profile_id: null, kit_name: null, sequencer_name: null, comment: null, performer_ids: [], settings: {} }))
}

function snapshotPreview(protocol: Protocol): ProtocolPreview | null {
  const snapshot = protocol.snapshot as {
    objects?: Array<Record<string, unknown>>
    stages?: Array<Record<string, unknown>>
    layouts?: ProtocolPreview['layouts']
    calculations?: ProtocolPreview['calculations']
    dilutions?: Array<Record<string, unknown>>
    warnings?: string[]
    plate_rules?: ProtocolPlateRules
  }
  if (!snapshot.layouts?.source || !snapshot.layouts?.pcr) return null
  return {
    selected_count: snapshot.objects?.length || 0,
    capacity: snapshot.layouts.source.capacity,
    max_capacity: 96,
    objects: snapshot.objects || [],
    stages: snapshot.stages || [],
    layouts: snapshot.layouts,
    calculations: snapshot.calculations || { pcr: [], electrophoresis: {} },
    dilutions: snapshot.dilutions || [],
    warnings: snapshot.warnings || [],
    snapshot: protocol.snapshot
  }
}

export function ProtocolsCreatePage({ user, protocolId, printOnOpen, onPrintHandled, onBack, onProtocolId, onDirtyChange }: { user: User; protocolId: number | null; printOnOpen: boolean; onPrintHandled: () => void; onBack: () => void; onProtocolId: (id: number | null) => void; onDirtyChange: (dirty: boolean) => void }) {
  const queryClient = useQueryClient()
  const [currentId, setCurrentId] = useState<number | null>(protocolId)
  const [protocolDate, setProtocolDate] = useState(today)
  const [protocolNo, setProtocolNo] = useState(1)
  const [name, setName] = useState('')
  const [comment, setComment] = useState('')
  const [partyIds, setPartyIds] = useState<number[]>([])
  const [selectedIds, setSelectedIds] = useState<number[]>([])
  const [stages, setStages] = useState<ProtocolStageSettings[]>(() => initialStages(today()))
  const [plateRules, setPlateRules] = useState<ProtocolPlateRules>(defaultRules)
  const [selectionOpen, setSelectionOpen] = useState(true)
  const [preview, setPreview] = useState<ProtocolPreview | null>(null)
  const [dirty, setDirty] = useState(false)
  const [showPrintPreview, setShowPrintPreview] = useState(false)
  const [printSelectionOpen, setPrintSelectionOpen] = useState(false)
  const [printIntent, setPrintIntent] = useState<'preview' | 'print'>('preview')
  const [printStageTypes, setPrintStageTypes] = useState<ProtocolStageType[]>(stageTypes)
  const [autoPrint, setAutoPrint] = useState(false)
  const hydratedId = useRef<number | null>(null)
  const protocol = useQuery({ queryKey: ['protocol', currentId], queryFn: () => api.protocol(currentId as number), enabled: currentId !== null })
  const meta = useQuery({ queryKey: ['protocol-meta', protocolDate], queryFn: () => api.protocolMeta(protocolDate), enabled: currentId === null })
  const years = useQuery({ queryKey: ['party-years'], queryFn: api.partyYears })
  const [year, setYear] = useState(new Date().getFullYear())
  useEffect(() => { if (years.data?.default_year) setYear(years.data.default_year) }, [years.data?.default_year])
  const parties = useQuery({ queryKey: ['parties', 'protocol', year], queryFn: () => api.parties('', false, year), staleTime: 30_000 })
  const employees = useQuery({ queryKey: ['employees', 'protocol'], queryFn: () => api.employees('', undefined, undefined, undefined, false), staleTime: 30_000 })
  const profiles = useQuery({ queryKey: ['protocol-profiles'], queryFn: () => api.protocolProfiles(), staleTime: 30_000 })
  const sequencers = useQuery({ queryKey: ['reference-items', 'sequencer'], queryFn: () => api.referenceItems('sequencer'), staleTime: 30_000 })
  const readOnly = protocol.data?.status === 'final' || protocol.data?.status === 'archived' || user.role === 'viewer'

  useEffect(() => {
    if (!meta.data || currentId !== null || dirty) return
    setProtocolNo(meta.data.suggested_no)
    setName(meta.data.suggested_name)
  }, [currentId, dirty, meta.data])

  useEffect(() => {
    const data = protocol.data
    if (!data || hydratedId.current === data.id) return
    hydratedId.current = data.id
    const snapshot = data.snapshot as {
      objects?: Array<{ id?: number; party_id?: number | null }>
      stages?: Array<Record<string, unknown>>
      plate_rules?: ProtocolPlateRules
    }
    setProtocolDate(data.protocol_date)
    setProtocolNo(data.protocol_no)
    setName(data.name)
    setComment(data.comment || '')
    setSelectedIds((snapshot.objects || []).flatMap((item) => typeof item.id === 'number' ? [item.id] : []))
    setPartyIds(Array.from(new Set((snapshot.objects || []).flatMap((item) => typeof item.party_id === 'number' ? [item.party_id] : []))))
    setStages(stageTypes.map((stageType) => {
      const item = (snapshot.stages || []).find((candidate) => candidate.stage_type === stageType)
      const performers = Array.isArray(item?.performers) ? item.performers as Array<{ employee_id?: number | null }> : []
      return {
        stage_type: stageType,
        enabled: item?.enabled !== false,
        work_date: typeof item?.work_date === 'string' ? item.work_date : null,
        profile_id: typeof item?.profile_id === 'number' ? item.profile_id : null,
        kit_name: typeof item?.kit_name === 'string' ? item.kit_name : null,
        sequencer_name: typeof item?.sequencer_name === 'string' ? item.sequencer_name : null,
        comment: typeof item?.comment === 'string' ? item.comment : null,
        performer_ids: performers.flatMap((performer) => typeof performer.employee_id === 'number' ? [performer.employee_id] : []),
        settings: item?.settings && typeof item.settings === 'object' ? item.settings as Record<string, unknown> : {}
      }
    }))
    setPlateRules(snapshot.plate_rules || defaultRules)
    setPreview(snapshotPreview(data))
    setSelectionOpen(!(snapshot.objects?.length))
    setDirty(false)
  }, [protocol.data])

  useEffect(() => {
    if (!dirty) return
    const handler = (event: BeforeUnloadEvent) => { event.preventDefault(); event.returnValue = '' }
    window.addEventListener('beforeunload', handler)
    return () => window.removeEventListener('beforeunload', handler)
  }, [dirty])
  useEffect(() => onDirtyChange(dirty), [dirty, onDirtyChange])
  useEffect(() => () => onDirtyChange(false), [onDirtyChange])
  useEffect(() => {
    if (!printOnOpen || !preview) return
    setPrintIntent('print')
    setPrintSelectionOpen(true)
    onPrintHandled()
  }, [onPrintHandled, preview, printOnOpen])
  useEffect(() => {
    if (!showPrintPreview || !autoPrint) return
    const timer = window.setTimeout(() => {
      setAutoPrint(false)
      printProtocol()
    }, 120)
    return () => window.clearTimeout(timer)
  }, [autoPrint, showPrintPreview])

  const payload = useMemo<ProtocolPayload>(() => ({
    protocol_date: protocolDate,
    protocol_no: protocolNo,
    name: name || `${protocolDate}_${protocolNo}`,
    comment: comment || null,
    object_ids: selectedIds,
    stages,
    plate_rules: plateRules,
    dilution: { enabled: true, target_concentration: 0.1, source_dna_volume: 3, dilution_one_volume: 10, threshold: 100 }
  }), [comment, name, plateRules, protocolDate, protocolNo, selectedIds, stages])
  const previewMutation = useMutation({ mutationFn: api.previewProtocol, onSuccess: setPreview })
  useEffect(() => {
    if (readOnly || !selectedIds.length || !name.trim()) return
    const timer = window.setTimeout(() => previewMutation.mutate(payload), 350)
    return () => window.clearTimeout(timer)
  }, [payload, readOnly, selectedIds.length])
  const save = useMutation({
    mutationFn: () => currentId ? api.updateProtocol(currentId, payload) : api.createProtocol(payload),
    onSuccess: (saved) => {
      setCurrentId(saved.id)
      onProtocolId(saved.id)
      hydratedId.current = null
      setDirty(false)
      queryClient.setQueryData(['protocol', saved.id], saved)
      queryClient.invalidateQueries({ queryKey: ['protocols'] })
    }
  })
  const finalize = useMutation({ mutationFn: () => api.finalizeProtocol(currentId as number), onSuccess: (saved) => { queryClient.setQueryData(['protocol', saved.id], saved); queryClient.invalidateQueries({ queryKey: ['protocols'] }) } })
  const revise = useMutation({ mutationFn: () => api.reviseProtocol(currentId as number), onSuccess: (saved) => { setCurrentId(saved.id); onProtocolId(saved.id); hydratedId.current = null; queryClient.setQueryData(['protocol', saved.id], saved) } })

  function markDirty() { if (!readOnly) setDirty(true) }
  function updateStage(stageType: ProtocolStageSettings['stage_type'], patch: Partial<ProtocolStageSettings>) {
    setStages((items) => items.map((item) => item.stage_type === stageType ? { ...item, ...patch } : item)); markDirty()
  }
  function requestBack() {
    if (dirty && !window.confirm('Есть несохранённые изменения. Выйти без сохранения?')) return
    onBack()
  }
  function printProtocol() {
    document.body.classList.add('protocol-printing')
    const cleanup = () => document.body.classList.remove('protocol-printing')
    window.addEventListener('afterprint', cleanup, { once: true })
    window.print()
    window.setTimeout(cleanup, 1000)
  }
  function openPrintSelection(intent: 'preview' | 'print') {
    setPrintIntent(intent)
    setPrintSelectionOpen(true)
  }
  function confirmPrintSelection() {
    if (!printStageTypes.length) return
    setPrintSelectionOpen(false)
    setShowPrintPreview(true)
    setAutoPrint(printIntent === 'print')
  }
  function togglePrintStage(stageType: ProtocolStageType) {
    setPrintStageTypes((items) => items.includes(stageType) ? items.filter((item) => item !== stageType) : [...items, stageType])
  }
  if (currentId && protocol.isLoading) return <div className="page"><LoadingState title="Загрузка протокола..." rows={8} /></div>
  if (currentId && protocol.isError) return <div className="page"><ErrorState error={protocol.error} onRetry={() => protocol.refetch()} /></div>
  return (
    <div className="page protocol-page">
      <PageHeader title={currentId ? `${name} · версия ${protocol.data?.revision_no || 1}` : 'Создать протокол'} description={protocol.data?.status === 'final' ? 'Сохранённый протокол открыт только для чтения.' : 'Выберите объекты и заполните поля прямо в рабочем документе.'} actions={<div className="protocol-toolbar">
        <button type="button" className="icon-button" onClick={requestBack}><ArrowLeft size={17} />Назад</button>
        {currentId && (protocol.data?.revisions.length || 0) > 1 ? <select aria-label="История версий" value={currentId} onChange={(event) => { if (dirty && !window.confirm('Есть несохранённые изменения. Выйти без сохранения?')) return; const id = Number(event.target.value); setDirty(false); setCurrentId(id); onProtocolId(id); hydratedId.current = null }}><option value={currentId} disabled>Версия {protocol.data?.revision_no}</option>{protocol.data?.revisions.filter((item) => item.id !== currentId).map((item) => <option value={item.id} key={item.id}>Версия {item.revision_no} · {item.status === 'final' ? 'сохранён' : item.status === 'archived' ? 'архив' : 'черновик'}</option>)}</select> : null}
        {readOnly && protocol.data?.status === 'final' && user.role !== 'viewer' ? <button type="button" className="icon-button" disabled={revise.isPending} onClick={() => revise.mutate()}><FilePenLine size={17} />Редактировать протокол</button> : null}
        {!readOnly ? <button type="button" className="primary compact" disabled={!selectedIds.length || save.isPending || previewMutation.isPending} onClick={() => save.mutate()}><Save size={17} />Сохранить черновик</button> : null}
        {currentId && protocol.data?.status === 'draft' ? <button type="button" className="icon-button" disabled={dirty || finalize.isPending} title={dirty ? 'Сначала сохраните изменения' : ''} onClick={() => finalize.mutate()}><Check size={17} />Сохранён</button> : null}
        <button type="button" className="icon-button" disabled={!preview} onClick={() => openPrintSelection('preview')}><Eye size={17} />Предпросмотр печати</button>
        <button type="button" className="icon-button" disabled={!preview} onClick={() => openPrintSelection('print')}><Printer size={17} />Печать</button>
        {currentId ? <a className="icon-button" href={api.protocolExcelUrl(currentId)}><Download size={17} />Скачать Excel</a> : null}
      </div>} />
      {save.error || finalize.error || revise.error || previewMutation.error ? <div className="alert danger">{String((save.error || finalize.error || revise.error || previewMutation.error) instanceof Error ? (save.error || finalize.error || revise.error || previewMutation.error)?.message : 'Не удалось выполнить действие')}</div> : null}
      {!readOnly ? <section className={`protocol-selection-panel${selectionOpen ? ' is-open' : ''}`}>
        <button type="button" className="protocol-selection-summary" onClick={() => setSelectionOpen((value) => !value)}><strong>Партии и объекты</strong><span>{partyIds.length} партий · {selectedIds.length} объектов</span><em>{selectionOpen ? 'Свернуть' : 'Изменить'}</em></button>
        {selectionOpen ? <div className="protocol-selection-body"><label className="protocol-year">Год <select value={year} onChange={(event) => { setYear(Number(event.target.value)); setPartyIds([]); setSelectedIds([]); markDirty() }}>{(years.data?.years || [year]).map((item) => <option key={item}>{item}</option>)}</select></label><ProtocolObjectSelector parties={parties.data?.items || []} partyIds={partyIds} selectedIds={selectedIds} onPartyIds={(ids) => { setPartyIds(ids); markDirty() }} onSelectedIds={(ids) => { setSelectedIds(ids); markDirty() }} /></div> : null}
      </section> : null}
      {selectedIds.length > 96 ? <div className="protocol-info-line">Выбрано: {selectedIds.length} объектов. Будет создано несколько плашек.</div> : null}
      {preview?.warnings.map((warning) => <div className="alert warning" key={warning}>{warning}</div>)}
      <div className="protocol-sheet-wrap">
        <ProtocolSheet protocolDate={protocolDate} protocolNo={protocolNo} name={name} selectedCount={selectedIds.length} stages={stages} plateRules={plateRules} preview={preview} profiles={profiles.data || []} employees={employees.data || []} sequencers={sequencers.data || []} readOnly={readOnly} onHeader={(patch) => { if (patch.protocolDate !== undefined) setProtocolDate(patch.protocolDate); if (patch.protocolNo !== undefined) setProtocolNo(patch.protocolNo); if (patch.name !== undefined) setName(patch.name); markDirty() }} onStage={updateStage} onRules={(patch) => { setPlateRules((rules) => ({ ...rules, ...patch })); markDirty() }} />
      </div>
      {printSelectionOpen ? <div className="modal-backdrop" onMouseDown={() => setPrintSelectionOpen(false)}><div className="modal protocol-print-selection" role="dialog" aria-modal="true" aria-label="Что печатать" onMouseDown={(event) => event.stopPropagation()}>
        <h2>Что печатать</h2>
        <div className="protocol-print-stage-options">{([
          ['dna_extraction', 'Выделение'], ['realtime', 'RT'], ['pcr', 'PCR'], ['electrophoresis', 'Форез']
        ] as Array<[ProtocolStageType, string]>).map(([stageType, label]) => <label key={stageType}><input type="checkbox" checked={printStageTypes.includes(stageType)} onChange={() => togglePrintStage(stageType)} />{label}</label>)}</div>
        <div className="modal-actions"><button type="button" className="icon-button" onClick={() => setPrintSelectionOpen(false)}>Отмена</button><button type="button" className="primary compact" disabled={!printStageTypes.length} onClick={confirmPrintSelection}>{printIntent === 'print' ? <Printer size={17} /> : <Eye size={17} />}{printIntent === 'print' ? 'Печать' : 'Предпросмотр'}</button></div>
      </div></div> : null}
      {showPrintPreview && preview ? createPortal(<div className="modal-backdrop protocol-preview-backdrop" onMouseDown={() => setShowPrintPreview(false)}><div className="protocol-preview-modal" role="dialog" aria-modal="true" aria-label="Предпросмотр печати" onMouseDown={(event) => event.stopPropagation()}><div className="protocol-preview-toolbar"><strong>Предпросмотр A4 landscape · страниц: {printStageTypes.reduce((total, stageType) => total + (stageType === 'pcr' ? preview.layouts.pcr.plates.length : preview.layouts.source.plates.length), 0)}</strong><button type="button" className="primary compact" onClick={printProtocol}><Printer size={17} />Печать</button><button type="button" className="icon-button" onClick={() => setShowPrintPreview(false)}>Закрыть</button></div><div className="protocol-print-root"><ProtocolPrintDocument protocolDate={protocolDate} protocolNo={protocolNo} name={name} stages={stages} selectedStageTypes={printStageTypes} plateRules={plateRules} preview={preview} employees={employees.data || []} /></div></div></div>, document.body) : null}
    </div>
  )
}
