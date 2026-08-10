import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Check, Search, X } from 'lucide-react'
import { Fragment, useEffect, useState } from 'react'
import { api } from '../api/client'
import type { CommitResponse, ElectrophoresisPdfPreview, RegistryPreview, RtCommitResponse, RtPreview } from '../api/types'
import { FileDropzone, MultiPartyPicker, PageHeader } from '../components/ui'

type RegistryImportStatus = 'pending' | 'previewing' | 'ready' | 'blocked' | 'committing' | 'done' | 'error'
type RegistryImportPhase = 'idle' | 'previewing' | 'committing' | 'done'
type DuplicateMode = '' | 'replace' | 'append'

type RegistryImportItem = {
  id: string
  fingerprint: string
  file: File
  filename: string
  status: RegistryImportStatus
  preview?: RegistryPreview
  result?: CommitResponse
  error?: string
  blockedReason?: string
  duplicateMode: '' | 'replace'
}

type RegistryImportRun = {
  phase: RegistryImportPhase
  currentIndex: number
  totalToCommit: number
  currentFilename: string
  startedAt: number | null
  imported: number
  failed: number
  rowsImported: number
  rowsUpdated: number
  stages: number
  skipped: number
  log: string[]
}

type RtImportItem = {
  id: string
  fingerprint: string
  file: File
  filename: string
  status: RegistryImportStatus
  preview?: RtPreview
  result?: RtCommitResponse
  error?: string
  duplicateMode: DuplicateMode
}

type RtImportRun = {
  phase: RegistryImportPhase
  currentIndex: number
  totalToCommit: number
  currentFilename: string
  startedAt: number | null
  imported: number
  failed: number
  stageEvents: number
  unmatched: number
  replacedResults: number
  replacedStageEvents: number
  log: string[]
}

const emptyRun: RegistryImportRun = {
  phase: 'idle',
  currentIndex: 0,
  totalToCommit: 0,
  currentFilename: '',
  startedAt: null,
  imported: 0,
  failed: 0,
  rowsImported: 0,
  rowsUpdated: 0,
  stages: 0,
  skipped: 0,
  log: []
}

const emptyRtRun: RtImportRun = {
  phase: 'idle',
  currentIndex: 0,
  totalToCommit: 0,
  currentFilename: '',
  startedAt: null,
  imported: 0,
  failed: 0,
  stageEvents: 0,
  unmatched: 0,
  replacedResults: 0,
  replacedStageEvents: 0,
  log: []
}

function errorMessage(error: unknown) {
  return error instanceof Error ? error.message : 'Не удалось выполнить операцию'
}

function ImportIntro({
  title,
  description,
  formats,
  steps,
  warnings
}: {
  title: string
  description: string
  formats: string[]
  steps: string[]
  warnings: string[]
}) {
  return (
    <section className="section import-intro">
      <div className="section-head">
        <div>
          <h2>{title}</h2>
          <p>{description}</p>
        </div>
      </div>
      <div className="import-help-grid">
        <div className="import-help-card">
          <strong>Форматы</strong>
          <p>{formats.join(', ')}</p>
        </div>
        <div className="import-help-card">
          <strong>После загрузки</strong>
          <ul>{steps.map((item) => <li key={item}>{item}</li>)}</ul>
        </div>
        <div className="import-help-card">
          <strong>Частые проверки</strong>
          <ul>{warnings.map((item) => <li key={item}>{item}</li>)}</ul>
        </div>
      </div>
    </section>
  )
}

function formatImportDate(value: string | null | undefined) {
  if (!value) return '—'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return date.toLocaleString('ru-RU', { day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit' })
}

function RecentImports() {
  const latest = useQuery({ queryKey: ['dashboard', 'latest-imports'], queryFn: api.dashboard, staleTime: 60_000 })
  const rows = latest.data?.latest_imports ?? []
  return (
    <section className="section recent-imports-section">
      <div className="section-head">
        <div>
          <h2>Последние импорты</h2>
          <p>Короткая история последних загруженных файлов.</p>
        </div>
      </div>
      {latest.isLoading ? (
        <div className="mini-table">
          {Array.from({ length: 3 }, (_, index) => <div key={index}><span>Загрузка...</span><span>—</span><span>—</span></div>)}
        </div>
      ) : rows.length ? (
        <div className="recent-imports-table">
          <div className="recent-imports-row recent-imports-head">
            <span>Дата</span>
            <span>Файл</span>
            <span>Партия</span>
            <span>Найдено</span>
            <span>Статус</span>
          </div>
          {rows.slice(0, 6).map((row) => (
            <div className="recent-imports-row" key={row.id}>
              <span>{formatImportDate(row.imported_at)}</span>
              <strong title={row.filename}>{row.filename}</strong>
              <span>{row.party_no || '—'}</span>
              <span>{row.rows_imported}</span>
              <span className="status-pill success">импортирован</span>
            </div>
          ))}
        </div>
      ) : (
        <div className="empty">Истории импортов пока нет</div>
      )}
    </section>
  )
}

function fileFingerprint(file: File) {
  return `${file.name}:${file.size}:${file.lastModified}`
}

function stageCount(preview?: RegistryPreview) {
  return preview ? Object.values(preview.stage_event_counts || {}).reduce((total, count) => total + count, 0) : 0
}

function fileDuplicateCount(preview?: RegistryPreview) {
  return preview?.duplicates.filter((item) => item.scope === 'file').length ?? 0
}

function duplicateScopeLabel(duplicate: RegistryPreview['duplicates'][number]) {
  if (duplicate.scope === 'file') return 'в файле'
  if (duplicate.scope === 'database_other_party') {
    return `в другой партии ${duplicate.current_party_no || duplicate.party_no || '—'}`
  }
  return duplicate.party_no ? `в базе, партия ${duplicate.party_no}` : 'в базе'
}

function statusLabel(status: RegistryImportStatus) {
  const labels: Record<RegistryImportStatus, string> = {
    pending: 'ожидает',
    previewing: 'предпросмотр',
    ready: 'готов',
    blocked: 'заблокирован',
    committing: 'импорт',
    done: 'импортирован',
    error: 'ошибка'
  }
  return labels[status]
}

function itemStatusLabel(item: RegistryImportItem) {
  if (item.status === 'done' && item.result) {
    if (item.result.rows_imported > 0 && item.result.rows_updated > 0) return 'импортирован и обновил существующие'
    if (item.result.rows_imported > 0) return 'импортирован'
    if (item.result.rows_updated > 0) return 'обновил существующие'
  }
  if (item.blockedReason === 'missing-party') return 'без номера партии'
  if (item.status === 'ready' && item.preview?.replace_required_count && item.duplicateMode !== 'replace') {
    return 'нужна замена'
  }
  return statusLabel(item.status)
}

function RegistryReplacePanel({
  count,
  selected,
  disabled,
  compact,
  onChange
}: {
  count: number
  selected: boolean
  disabled: boolean
  compact?: boolean
  onChange: (selected: boolean) => void
}) {
  return (
    <div className={`registry-replace-panel${selected ? ' selected' : ''}${compact ? ' compact' : ''}`}>
      <div>
        <strong>{selected ? 'Замена выбрана' : 'Повторный импорт реестра'}</strong>
        <span>{selected ? `Будут заменены данные по ${count} объектам.` : `Уже есть данные по ${count} объектам. Для импорта обновлённого файла выберите замену.`}</span>
      </div>
      <div className="registry-replace-actions">
        {selected ? (
          <button className="icon-button" disabled={disabled} onClick={() => onChange(false)}>Отменить замену</button>
        ) : (
          <button className="primary compact" disabled={disabled} onClick={() => onChange(true)}>Заменить существующие данные</button>
        )}
      </div>
    </div>
  )
}

function elapsedTime(startedAt: number | null) {
  if (!startedAt) return '0:00'
  const seconds = Math.max(0, Math.floor((Date.now() - startedAt) / 1000))
  const minutes = Math.floor(seconds / 60)
  return `${minutes}:${String(seconds % 60).padStart(2, '0')}`
}

export function RegistryImportPage() {
  const queryClient = useQueryClient()
  const [items, setItems] = useState<RegistryImportItem[]>([])
  const [message, setMessage] = useState('')
  const [notice, setNotice] = useState('')
  const [isPreviewing, setIsPreviewing] = useState(false)
  const [isCommitting, setIsCommitting] = useState(false)
  const [run, setRun] = useState<RegistryImportRun>(emptyRun)

  const readyCount = items.filter((item) => item.status === 'ready' && item.preview && registryItemReady(item)).length
  const blockedCount = items.filter((item) => item.status === 'blocked').length
  const importedItems = items.filter((item) => item.status === 'done')
  const blockedItems = items.filter((item) => item.status === 'blocked')
  const errorItems = items.filter((item) => item.status === 'error')
  const noPartyItems = items.filter((item) => item.blockedReason === 'missing-party')
  const activeImportItemId = items.find((item) => item.status === 'committing')?.id ?? null
  const compactCards = items.length > 20 || isCommitting
  const completedInRun = run.imported + run.failed
  const runProgressValue = run.phase === 'previewing' ? run.currentIndex : completedInRun
  const runPercent = run.totalToCommit ? Math.round((runProgressValue / run.totalToCommit) * 100) : 0
  const remainingInRun = Math.max(run.totalToCommit - completedInRun, 0)
  const previewedItems = items.filter((item) => item.preview)
  const summary = previewedItems.reduce(
    (total, item) => ({
      rows: total.rows + (item.preview?.rows_detected ?? 0),
      newObjects: total.newObjects + (item.preview?.new_objects_count ?? 0),
      existingObjects: total.existingObjects + (item.preview?.existing_objects_count ?? 0),
      stages: total.stages + stageCount(item.preview),
      skipped: total.skipped + (item.preview?.rows_skipped ?? 0)
    }),
    { rows: 0, newObjects: 0, existingObjects: 0, stages: 0, skipped: 0 }
  )

  function updateItem(id: string, patch: Partial<RegistryImportItem>) {
    setItems((prev) => prev.map((item) => item.id === id ? { ...item, ...patch } : item))
  }

  function registryItemNeedsReplace(item: RegistryImportItem) {
    return Boolean(item.preview && item.preview.replace_required_count > 0)
  }

  function registryItemReady(item: RegistryImportItem) {
    if (!item.preview) return false
    if (registryItemNeedsReplace(item) && item.duplicateMode !== 'replace') return false
    return true
  }

  function pushRunLog(message: string) {
    setRun((prev) => ({ ...prev, log: [message, ...prev.log].slice(0, 8) }))
  }

  async function previewFiles(files: File[]) {
    setIsPreviewing(true)
    setRun((prev) => ({
      ...prev,
      phase: 'previewing',
      currentIndex: 0,
      totalToCommit: files.length,
      currentFilename: files[0]?.name || '',
      startedAt: Date.now(),
      log: [`Старт предпросмотра: ${files.length} файлов`, ...prev.log].slice(0, 8)
    }))
    setMessage('')
    for (const [index, file] of files.entries()) {
      setRun((prev) => ({ ...prev, currentIndex: index + 1, currentFilename: file.name }))
      const fingerprint = fileFingerprint(file)
      const id = `${fingerprint}:${crypto.randomUUID?.() || `${Date.now()}-${Math.random()}`}`
      const item: RegistryImportItem = {
        id,
        fingerprint,
        file,
        filename: file.name,
        status: 'pending',
        duplicateMode: ''
      }
      setItems((prev) => [...prev, item])
      updateItem(id, { status: 'previewing' })
      try {
        const preview = await api.previewRegistry(file)
        const blockedReason = !preview.party_no
          ? 'missing-party'
          : fileDuplicateCount(preview) > 0
            ? 'file-duplicates'
            : undefined
        updateItem(id, {
          preview,
          filename: preview.filename || file.name,
          status: blockedReason ? 'blocked' : 'ready',
          error: undefined,
          blockedReason
        })
        pushRunLog(`${blockedReason ? 'Предпросмотр с блокировкой' : 'Готов к импорту'}: ${preview.filename || file.name}`)
      } catch (error) {
        updateItem(id, { status: 'error', error: errorMessage(error) })
        pushRunLog(`Ошибка предпросмотра: ${file.name}`)
      }
    }
    setIsPreviewing(false)
    setRun((prev) => ({ ...prev, phase: 'idle', currentIndex: 0, totalToCommit: 0, currentFilename: '' }))
  }

  function handleFiles(fileList: FileList | File[] | null) {
    if (!fileList?.length) return
    const known = new Set(items.map((item) => item.fingerprint))
    const unique: File[] = []
    const duplicateNames: string[] = []
    for (const file of Array.from(fileList)) {
      const fingerprint = fileFingerprint(file)
      if (known.has(fingerprint)) {
        duplicateNames.push(file.name)
        continue
      }
      known.add(fingerprint)
      unique.push(file)
    }
    setNotice(duplicateNames.length ? `Повторно выбранные файлы пропущены: ${duplicateNames.join(', ')}` : '')
    if (unique.length) void previewFiles(unique)
  }

  function invalidateAfterCommit() {
    queryClient.invalidateQueries({ queryKey: ['objects'] })
    queryClient.invalidateQueries({ queryKey: ['dashboard'] })
    queryClient.invalidateQueries({ queryKey: ['parties'] })
    queryClient.invalidateQueries({ queryKey: ['party'] })
    queryClient.invalidateQueries({ queryKey: ['party-progress'] })
    queryClient.invalidateQueries({ queryKey: ['party-stage-table'] })
  }

  async function commitReadyItems() {
    const targets = items.filter((item) => item.status === 'ready' && item.preview && registryItemReady(item))
    if (!targets.length) return
    setIsCommitting(true)
    setMessage('')
    setRun({
      ...emptyRun,
      phase: 'committing',
      totalToCommit: targets.length,
      startedAt: Date.now(),
      log: [`Старт импорта: ${targets.length} файлов`]
    })
    const total = { imported: 0, updated: 0, stages: 0, skipped: 0, succeeded: 0, failed: 0 }
    for (const [index, item] of targets.entries()) {
      setRun((prev) => ({ ...prev, currentIndex: index + 1, currentFilename: item.filename }))
      pushRunLog(`Импортируется: ${item.filename}`)
      updateItem(item.id, { status: 'committing', error: undefined })
      let itemLog = ''
      try {
        const result = await api.commitRegistry(
          item.preview!.upload_id,
          registryItemNeedsReplace(item) ? 'replace' : 'block'
        )
        total.imported += result.rows_imported
        total.updated += result.rows_updated
        total.stages += result.stage_events_written
        total.skipped += result.rows_skipped
        total.succeeded += 1
        itemLog = `Готово: ${item.filename}`
        updateItem(item.id, { status: 'done', result })
      } catch (error) {
        total.failed += 1
        itemLog = `Ошибка: ${item.filename}`
        updateItem(item.id, { status: 'error', error: errorMessage(error) })
      }
      setRun((prev) => ({
        ...prev,
        imported: total.succeeded,
        failed: total.failed,
        rowsImported: total.imported,
        rowsUpdated: total.updated,
        stages: total.stages,
        skipped: total.skipped,
        log: [itemLog, ...prev.log].slice(0, 8)
      }))
    }
    setIsCommitting(false)
    invalidateAfterCommit()
    setRun((prev) => ({ ...prev, phase: 'done', currentFilename: '' }))
    setMessage(`Файлов импортировано: ${total.succeeded}; ошибок: ${total.failed}; объектов добавлено ${total.imported}, обновлено ${total.updated}; этапов ${total.stages}; пропущено ${total.skipped}`)
  }

  return (
    <div className="page">
      <PageHeader
        title="Импорт реестра"
        description="Загрузите один или несколько Excel-реестров. Система покажет партии, объекты, этапы, дубликаты и предупреждения перед импортом."
      />
      <ImportIntro
        title="Как работает импорт"
        description="Новые реестры добавляются пакетно, а повторные требуют явного выбора замены существующих данных."
        formats={['.xlsx', '.xls']}
        steps={['preview файла', 'проверка дублей и партий', 'импорт доступных файлов']}
        warnings={['дубликаты внутри файла блокируются', 'объекты из другой партии не переносятся', 'замена затрагивает только registry_excel']}
      />
      <section className="upload-panel">
        <FileDropzone
          title="Перетащите Excel-реестры сюда"
          description="или нажмите для выбора одного или нескольких файлов"
          formats=".xlsx, .xls"
          accept=".xlsx,.xls"
          multiple
          onFiles={handleFiles}
        />
        {notice && <div className="alert">{notice}</div>}
      </section>
      <RecentImports />
      {items.length > 0 && (
        <section className="section">
          <div className="party-main-head">
            <h2>Предпросмотр пакета</h2>
            <div className="toolbar-actions">
              <button className="icon-button" disabled={isPreviewing || isCommitting} onClick={() => { setItems([]); setMessage(''); setNotice(''); setRun(emptyRun) }}><X size={18} />Очистить</button>
              <button className="primary compact" disabled={!readyCount || isPreviewing || isCommitting} onClick={() => void commitReadyItems()}><Check size={18} />{isCommitting ? 'Импорт идёт...' : 'Импортировать доступные'}</button>
            </div>
          </div>
          {run.phase !== 'idle' && (
            <div className="import-progress-panel">
              <div className="import-progress-head">
                <strong>{run.phase === 'previewing' ? 'Предпросмотр файлов' : run.phase === 'committing' ? `Импортируется файл ${run.currentIndex} из ${run.totalToCommit}` : `Готово: ${run.imported} импортировано, ${run.failed} ошибок`}</strong>
                <span>{run.currentFilename || `Прошло ${elapsedTime(run.startedAt)}`}</span>
              </div>
              <div className="import-progress-bar" aria-label="Прогресс импорта">
                <span style={{ width: `${run.phase === 'previewing' ? 0 : runPercent}%` }} />
              </div>
              <div className="summary-line">
                <strong>{run.imported} импортировано</strong>
                <strong>{run.failed} ошибок</strong>
                <strong>{remainingInRun} осталось</strong>
                <strong>{run.rowsImported} добавлено</strong>
                <strong>{run.rowsUpdated} обновлено</strong>
                <strong>{run.stages} этапов</strong>
                <strong>{run.skipped} пропущено</strong>
              </div>
              {run.log.length > 0 && (
                <div className="import-log">
                  {run.log.map((entry, index) => <span key={`${entry}-${index}`}>{entry}</span>)}
                </div>
              )}
            </div>
          )}
          <div className="summary-line">
            <strong>{items.length} файлов</strong>
            <strong>{readyCount} готовы</strong>
            <strong>{blockedCount} заблокированы</strong>
            <strong>{summary.rows} объектов</strong>
            <strong>{summary.newObjects} новых</strong>
            <strong>{summary.existingObjects} существующих</strong>
            <strong>{summary.stages} этапов</strong>
            <strong>{summary.skipped} пропущено</strong>
          </div>
          {(importedItems.length > 0 || blockedItems.length > 0 || errorItems.length > 0 || noPartyItems.length > 0) && (
            <div className="import-report">
              {importedItems.length > 0 && <div className="alert success"><strong>Импортированы:</strong> {importedItems.map((item) => item.filename).join(', ')}</div>}
              {blockedItems.length > 0 && <div className="alert"><strong>Заблокированы:</strong> {blockedItems.map((item) => item.filename).join(', ')}</div>}
              {noPartyItems.length > 0 && <div className="alert error"><strong>Без номера партии:</strong> {noPartyItems.map((item) => item.filename).join(', ')}</div>}
              {errorItems.length > 0 && <div className="alert error"><strong>Ошибки:</strong> {errorItems.map((item) => item.filename).join(', ')}</div>}
            </div>
          )}
          {message && <div className="alert success">{message}</div>}
          <div className="import-batch-list">
            {items.map((item) => {
              const preview = item.preview
              const duplicateWarnings = preview?.duplicates.slice(0, 8).map((d) => `Строка ${d.row_number}: дубликат ${d.field} = ${d.value} (${duplicateScopeLabel(d)})`) ?? []
              const warnings = [...(preview?.warnings ?? []), ...duplicateWarnings]
              return (
                <article className={`import-card ${item.status} ${activeImportItemId === item.id ? 'active' : ''} ${compactCards ? 'compact' : ''}`} key={item.id}>
                  <div className="party-main-head">
                    <div>
                      <h3>{item.filename}</h3>
                      <span>{itemStatusLabel(item)}</span>
                    </div>
                    {item.result && <strong>batch #{item.result.batch_id}</strong>}
                  </div>
                  {item.error && <div className="alert error">{item.error}</div>}
                  {preview ? (
                    <>
                      <div className="summary-line">
                        <strong>Партия {preview.party_no || 'не определена'}</strong>
                        <strong>{preview.rows_detected} объектов</strong>
                        <strong>{preview.new_objects_count} новых</strong>
                        <strong>{preview.existing_objects_count} существующих</strong>
                        {preview.replace_required_count > 0 && <strong>{preview.replace_required_count} требуют замены</strong>}
                        <strong>{stageCount(preview)} этапов</strong>
                        <strong>{preview.rows_skipped} пропущено</strong>
                        <strong>{preview.duplicates.length} дубликатов</strong>
                      </div>
                      {!compactCards && (
                        <>
                          {preview.replace_required_count > 0 && (
                            <RegistryReplacePanel
                              count={preview.replace_required_count}
                              selected={item.duplicateMode === 'replace'}
                              disabled={isCommitting || item.status === 'done'}
                              onChange={(selected) => updateItem(item.id, { duplicateMode: selected ? 'replace' : '' })}
                            />
                          )}
                          {fileDuplicateCount(preview) > 0 && <div className="alert error">Файл заблокирован: найдены дубликаты внутри файла.</div>}
                          {item.blockedReason === 'missing-party' && <div className="alert error">Файл заблокирован: номер партии не найден в имени файла.</div>}
                          {warnings.map((warning) => <div className="alert" key={warning}>{warning}</div>)}
                          {Object.entries(preview.party_control || {}).length > 0 && (
                            <div className="chips">
                              {Object.entries(preview.party_control).map(([key, value]) => (
                                <span key={key}>{key}: {typeof value === 'object' && value && 'text' in value ? String((value as { text?: unknown }).text || '') : String(value)}</span>
                              ))}
                            </div>
                          )}
                          <div className="mini-table">
                            {preview.sample_rows.slice(0, 8).map((row) => <div key={row.source_row_number}><span>{row.source_row_number}</span><span>{row.rcsme_reg_no}</span><span>{row.decree_no}</span></div>)}
                          </div>
                        </>
                      )}
                      {compactCards && (fileDuplicateCount(preview) > 0 || item.blockedReason === 'missing-party') && (
                        <div className="alert error">
                          {item.blockedReason === 'missing-party' ? 'Файл заблокирован: номер партии не найден в имени файла.' : 'Файл заблокирован: найдены дубликаты внутри файла.'}
                        </div>
                      )}
                      {compactCards && preview.replace_required_count > 0 && item.status !== 'done' && (
                        <RegistryReplacePanel
                          count={preview.replace_required_count}
                          selected={item.duplicateMode === 'replace'}
                          disabled={isCommitting}
                          compact
                          onChange={(selected) => updateItem(item.id, { duplicateMode: selected ? 'replace' : '' })}
                        />
                      )}
                      {item.result && <div className="alert success">Импортировано {item.result.rows_imported}, заменено/обновлено {item.result.rows_updated}; этапов {item.result.stage_events_written}; пропущено {item.result.rows_skipped}</div>}
                    </>
                  ) : item.status !== 'error' ? (
                    <div className="alert">Файл ожидает предпросмотр...</div>
                  ) : null}
                </article>
              )
            })}
          </div>
        </section>
      )}
    </div>
  )
}

export function RtImportPage() {
  const queryClient = useQueryClient()
  const [items, setItems] = useState<RtImportItem[]>([])
  const [performer, setPerformer] = useState('')
  const [message, setMessage] = useState('')
  const [notice, setNotice] = useState('')
  const [isPreviewing, setIsPreviewing] = useState(false)
  const [isCommitting, setIsCommitting] = useState(false)
  const [run, setRun] = useState<RtImportRun>(emptyRtRun)
  const [fixMessage, setFixMessage] = useState('')
  const employees = useQuery({ queryKey: ['employees', 'rt-import'], queryFn: () => api.employees('', null, 'realtime'), staleTime: 60_000 })
  const fixPreview = useMutation({ mutationFn: api.rcsmeFixPreview })
  const fixApply = useMutation({
    mutationFn: api.rcsmeFixApply,
    onSuccess: (result) => {
      setFixMessage(`Исправлено номеров: ${result.fixed}; пропущено: ${result.skipped}; конфликтов: ${result.conflicts}`)
      queryClient.invalidateQueries({ queryKey: ['objects'] })
      queryClient.invalidateQueries({ queryKey: ['party-stage-table'] })
    }
  })

  const readyItems = items.filter((item) => item.status === 'ready' && item.preview)
  const blockedItems = items.filter((item) => item.status === 'blocked')
  const errorItems = items.filter((item) => item.status === 'error')
  const doneItems = items.filter((item) => item.status === 'done')
  const activeItemId = items.find((item) => item.status === 'committing')?.id ?? null
  const compactCards = items.length > 12 || isCommitting
  const completedInRun = run.imported + run.failed
  const runProgressValue = run.phase === 'previewing' ? run.currentIndex : completedInRun
  const runPercent = run.totalToCommit ? Math.round((runProgressValue / run.totalToCommit) * 100) : 0
  const remainingInRun = Math.max(run.totalToCommit - completedInRun, 0)
  const summary = items.reduce(
    (total, item) => ({
      samples: total.samples + (item.preview?.sample_rows.length ?? 0),
      matched: total.matched + (item.preview?.matched_count ?? 0),
      unmatched: total.unmatched + (item.preview?.unmatched_count ?? 0),
      existing: total.existing + (item.preview?.existing_rt_count ?? 0),
      repeats: total.repeats + (item.preview?.repeat_samples.length ?? 0)
    }),
    { samples: 0, matched: 0, unmatched: 0, existing: 0, repeats: 0 }
  )

  function updateRtItem(id: string, patch: Partial<RtImportItem>) {
    setItems((prev) => prev.map((item) => item.id === id ? { ...item, ...patch } : item))
  }

  function pushRtRunLog(entry: string) {
    setRun((prev) => ({ ...prev, log: [entry, ...prev.log].slice(0, 8) }))
  }

  function rtItemReady(preview: RtPreview, duplicateMode: DuplicateMode) {
    if (!preview.matched_count) return false
    if (preview.existing_rt_count > 0 && !duplicateMode) return false
    return true
  }

  function rtStatusLabel(item: RtImportItem) {
    if (item.status === 'ready' && item.preview?.existing_rt_count) return 'нужен режим повтора'
    if (item.status === 'done') return item.result?.replaced_results || item.result?.replaced_stage_events ? 'импортирован с заменой' : 'импортирован'
    return statusLabel(item.status)
  }

  async function previewRtFiles(files: File[]) {
    setIsPreviewing(true)
    setMessage('')
    setRun((prev) => ({
      ...prev,
      phase: 'previewing',
      currentIndex: 0,
      totalToCommit: files.length,
      currentFilename: files[0]?.name || '',
      startedAt: Date.now(),
      log: [`Старт предпросмотра RT: ${files.length} файлов`, ...prev.log].slice(0, 8)
    }))
    for (const [index, file] of files.entries()) {
      setRun((prev) => ({ ...prev, currentIndex: index + 1, currentFilename: file.name }))
      const fingerprint = fileFingerprint(file)
      const id = `${fingerprint}:${crypto.randomUUID?.() || `${Date.now()}-${Math.random()}`}`
      const item: RtImportItem = {
        id,
        fingerprint,
        file,
        filename: file.name,
        status: 'pending',
        duplicateMode: ''
      }
      setItems((prev) => [...prev, item])
      updateRtItem(id, { status: 'previewing' })
      try {
        const preview = await api.previewRt(file)
        const status: RegistryImportStatus = preview.matched_count ? 'ready' : 'blocked'
        updateRtItem(id, {
          preview,
          filename: preview.filename || file.name,
          status,
          error: undefined,
          duplicateMode: ''
        })
        pushRtRunLog(`${status === 'ready' ? 'Готов к RT-импорту' : 'Нет сопоставленных объектов'}: ${preview.filename || file.name}`)
      } catch (error) {
        updateRtItem(id, { status: 'error', error: errorMessage(error) })
        pushRtRunLog(`Ошибка RT-предпросмотра: ${file.name}`)
      }
    }
    setIsPreviewing(false)
    setRun((prev) => ({ ...prev, phase: 'idle', currentIndex: 0, totalToCommit: 0, currentFilename: '' }))
  }

  function handleRtFiles(fileList: FileList | File[] | null) {
    if (!fileList?.length) return
    const known = new Set(items.map((item) => item.fingerprint))
    const unique: File[] = []
    const duplicateNames: string[] = []
    for (const file of Array.from(fileList)) {
      const fingerprint = fileFingerprint(file)
      if (known.has(fingerprint)) {
        duplicateNames.push(file.name)
        continue
      }
      known.add(fingerprint)
      unique.push(file)
    }
    setNotice(duplicateNames.length ? `Повторно выбранные RT-файлы пропущены: ${duplicateNames.join(', ')}` : '')
    if (unique.length) void previewRtFiles(unique)
  }

  function invalidateAfterRtCommit() {
    queryClient.invalidateQueries({ queryKey: ['party-stage-table'] })
    queryClient.invalidateQueries({ queryKey: ['objects'] })
    queryClient.invalidateQueries({ queryKey: ['dashboard'] })
    queryClient.invalidateQueries({ queryKey: ['party-progress'] })
    queryClient.invalidateQueries({ queryKey: ['parties'] })
  }

  async function commitReadyRtItems() {
    const targets = items.filter((item) => item.status === 'ready' && item.preview && rtItemReady(item.preview, item.duplicateMode))
    if (!targets.length || !performer) return
    setIsCommitting(true)
    setMessage('')
    setRun({
      ...emptyRtRun,
      phase: 'committing',
      totalToCommit: targets.length,
      startedAt: Date.now(),
      log: [`Старт RT-импорта: ${targets.length} файлов`]
    })
    const total = { succeeded: 0, failed: 0, stageEvents: 0, unmatched: 0, replacedResults: 0, replacedStageEvents: 0 }
    for (const [index, item] of targets.entries()) {
      setRun((prev) => ({ ...prev, currentIndex: index + 1, currentFilename: item.filename }))
      pushRtRunLog(`Импортируется RT: ${item.filename}`)
      updateRtItem(item.id, { status: 'committing', error: undefined })
      let itemLog = ''
      try {
        const result = await api.commitRt({
          upload_id: item.preview!.upload_id,
          quant_performer: performer,
          duplicate_mode: item.preview!.existing_rt_count > 0 ? item.duplicateMode || 'block' : 'block'
        })
        total.succeeded += 1
        total.stageEvents += result.stage_events_written
        total.unmatched += result.unmatched_count
        total.replacedResults += result.replaced_results
        total.replacedStageEvents += result.replaced_stage_events
        itemLog = `Готово RT: ${item.filename}`
        updateRtItem(item.id, { status: 'done', result })
      } catch (error) {
        total.failed += 1
        itemLog = `Ошибка RT: ${item.filename}`
        updateRtItem(item.id, { status: 'error', error: errorMessage(error) })
      }
      setRun((prev) => ({
        ...prev,
        imported: total.succeeded,
        failed: total.failed,
        stageEvents: total.stageEvents,
        unmatched: total.unmatched,
        replacedResults: total.replacedResults,
        replacedStageEvents: total.replacedStageEvents,
        log: [itemLog, ...prev.log].slice(0, 8)
      }))
    }
    setIsCommitting(false)
    invalidateAfterRtCommit()
    setRun((prev) => ({ ...prev, phase: 'done', currentFilename: '' }))
    setMessage(`RT-файлов импортировано: ${total.succeeded}; ошибок: ${total.failed}; событий RealTime: ${total.stageEvents}; не найдено: ${total.unmatched}; заменено результатов ${total.replacedResults}, событий ${total.replacedStageEvents}`)
  }

  return (
    <div className="page">
      <PageHeader
        title="Импорт RT / qPCR"
        description="Загрузите файлы RealTime/qPCR. Система сопоставит результаты с объектами по № рег РЦСМЭ, постановлениям и repeat-номерам."
      />
      <ImportIntro
        title="Правила сопоставления"
        description="Повторные образцы с *, x или х создают отдельные repeat-строки и не затирают основной объект."
        formats={['.xlsx', '.xls']}
        steps={['preview по каждому файлу', 'выбор исполнителя RT', 'замена или новая попытка при повторном импорте']}
        warnings={['без выбора режима старые RT-данные не перезаписываются', 'не найденные номера остаются в отчёте', 'пакет импортируется последовательно']}
      />
      <section className="upload-panel">
        <FileDropzone
          title="Перетащите файлы RealTime / qPCR сюда"
          description="или нажмите для выбора Abs Quant или TRIO"
          formats=".xlsx, .xls"
          accept=".xls,.xlsx"
          multiple
          onFiles={handleRtFiles}
        />
        {notice && <div className="alert">{notice}</div>}
      </section>
      <RecentImports />
      {items.length > 0 && (
        <section className="section">
          <div className="party-main-head">
            <h2>Предпросмотр RT-пакета</h2>
            <div className="toolbar-actions">
              <button className="icon-button" disabled={isPreviewing || isCommitting} onClick={() => { setItems([]); setMessage(''); setNotice(''); setRun(emptyRtRun) }}><X size={18} />Очистить</button>
              <button className="primary compact" disabled={!performer || !readyItems.some((item) => item.preview && rtItemReady(item.preview, item.duplicateMode)) || isPreviewing || isCommitting} onClick={() => void commitReadyRtItems()}><Check size={18} />{isCommitting ? 'Импорт идёт...' : 'Импортировать доступные'}</button>
            </div>
          </div>
          <div className="rt-import-actions">
            <label>Оценка концентрации ДНК — исполнитель
              <select value={performer} onChange={(event) => setPerformer(event.target.value)} disabled={isCommitting}>
                <option value="">Выберите сотрудника</option>
                {(employees.data ?? []).map((employee) => <option value={employee.full_name} key={employee.id}>{employee.short_name || employee.full_name}</option>)}
              </select>
            </label>
          </div>
          {run.phase !== 'idle' && (
            <div className="import-progress-panel">
              <div className="import-progress-head">
                <strong>{run.phase === 'previewing' ? 'Предпросмотр RT-файлов' : run.phase === 'committing' ? `Импортируется RT-файл ${run.currentIndex} из ${run.totalToCommit}` : `Готово: ${run.imported} импортировано, ${run.failed} ошибок`}</strong>
                <span>{run.currentFilename || `Прошло ${elapsedTime(run.startedAt)}`}</span>
              </div>
              <div className="import-progress-bar" aria-label="Прогресс RT-импорта">
                <span style={{ width: `${run.phase === 'previewing' ? 0 : runPercent}%` }} />
              </div>
              <div className="summary-line">
                <strong>{run.imported} импортировано</strong>
                <strong>{run.failed} ошибок</strong>
                <strong>{remainingInRun} осталось</strong>
                <strong>{run.stageEvents} событий RT</strong>
                <strong>{run.unmatched} не найдено</strong>
                <strong>{run.replacedResults} результатов заменено</strong>
                <strong>{run.replacedStageEvents} событий заменено</strong>
              </div>
              {run.log.length > 0 && (
                <div className="import-log">
                  {run.log.map((entry, index) => <span key={`${entry}-${index}`}>{entry}</span>)}
                </div>
              )}
            </div>
          )}
          <div className="summary-line">
            <strong>{items.length} файлов</strong>
            <strong>{readyItems.length} готовы</strong>
            <strong>{blockedItems.length} заблокированы</strong>
            <strong>{summary.samples} образцов</strong>
            <strong>{summary.matched} сопоставлено</strong>
            <strong>{summary.unmatched} без объекта</strong>
            <strong>{summary.existing} уже есть</strong>
            <strong>{summary.repeats} повторов</strong>
          </div>
          {message && <div className="alert success">{message}</div>}
          {(doneItems.length > 0 || errorItems.length > 0 || blockedItems.length > 0) && (
            <div className="import-report">
              {doneItems.length > 0 && <div className="alert success"><strong>Импортированы:</strong> {doneItems.map((item) => item.filename).join(', ')}</div>}
              {blockedItems.length > 0 && <div className="alert"><strong>Заблокированы:</strong> {blockedItems.map((item) => item.filename).join(', ')}</div>}
              {errorItems.length > 0 && <div className="alert error"><strong>Ошибки:</strong> {errorItems.map((item) => item.filename).join(', ')}</div>}
            </div>
          )}
          <div className="import-batch-list">
            {items.map((item) => {
              const preview = item.preview
              const existingRows = preview?.sample_rows.filter((row) => Boolean(row.has_existing_rt)) ?? []
              const unmatchedRows = preview?.unmatched_samples ?? []
              const repeatRows = preview?.repeat_samples ?? []
              const needsDuplicateChoice = Boolean(preview?.existing_rt_count)
              const canShowDetails = !compactCards || item.status === 'error' || item.status === 'blocked' || activeItemId === item.id
              return (
                <article className={`import-card ${item.status} ${activeItemId === item.id ? 'active' : ''} ${compactCards ? 'compact' : ''}`} key={item.id}>
                  <div className="party-main-head">
                    <div>
                      <h3>{item.filename}</h3>
                      <span>{rtStatusLabel(item)}</span>
                    </div>
                    {item.result && <strong>run #{item.result.run_id}</strong>}
                  </div>
                  {item.error && <div className="alert error">{item.error}</div>}
                  {preview ? (
                    <>
                      <div className="summary-line">
                        <strong>{preview.parser_type}</strong>
                        <strong>{preview.quant_method || 'метод не определён'}</strong>
                        <strong>{preview.run_date || 'дата не определена'}</strong>
                        <strong>{preview.sample_rows.length} образцов</strong>
                        <strong>{preview.matched_count} сопоставлено</strong>
                        <strong>{preview.unmatched_count} без объекта</strong>
                        {preview.existing_rt_count > 0 && <strong>{preview.existing_rt_count} уже есть</strong>}
                        {repeatRows.length > 0 && <strong>{repeatRows.length} повторов</strong>}
                      </div>
                      {needsDuplicateChoice && item.status !== 'done' && (
                        <div className="rt-import-actions">
                          <label>Повторный импорт этого файла
                            <select
                              value={item.duplicateMode}
                              disabled={isCommitting}
                              onChange={(event) => updateRtItem(item.id, { duplicateMode: event.target.value as DuplicateMode })}
                            >
                              <option value="">Выберите действие</option>
                              <option value="replace">Заменить существующие данные</option>
                              <option value="append">Добавить как новую попытку</option>
                            </select>
                          </label>
                        </div>
                      )}
                      {canShowDetails && (
                        <>
                          {preview.warnings.map((warning) => <div className="alert" key={warning}>{warning}</div>)}
                          {existingRows.length > 0 && (
                            <div className="alert warning">
                              <strong>Уже есть RT-данные:</strong> {existingRows.slice(0, 12).map((row) => String(row.normalized_sample_name || row.sample_name_raw)).join(', ')}
                              {existingRows.length > 12 ? ` и ещё ${existingRows.length - 12}` : ''}.
                            </div>
                          )}
                          <RepeatWarningPanel rows={repeatRows} />
                          <RtPreviewTable rows={preview.sample_rows.slice(0, 200)} />
                          {unmatchedRows.length > 0 && (
                            <div className="alert error">
                              <strong>Не найдены в БД:</strong> {unmatchedRows.map((row) => String(row.normalized_sample_name || row.sample_name_raw)).join(', ')}
                            </div>
                          )}
                        </>
                      )}
                      {item.result && <div className="alert success">Событий RealTime: {item.result.stage_events_written}; не найдено: {item.result.unmatched_count}; заменено результатов {item.result.replaced_results}, событий {item.result.replaced_stage_events}</div>}
                    </>
                  ) : item.status !== 'error' ? (
                    <div className="alert">Файл ожидает предпросмотр...</div>
                  ) : null}
                </article>
              )
            })}
          </div>
        </section>
      )}
      <details className="section service-tools">
        <summary><strong>Служебные инструменты</strong><span>Проверка номеров РЦСМЭ</span></summary>
        <div className="toolbar-actions">
          <button className="icon-button" onClick={() => fixPreview.mutate()} disabled={fixPreview.isPending}>Проверить</button>
          <button className="primary compact" onClick={() => fixApply.mutate()} disabled={fixApply.isPending || !fixPreview.data?.total}><Check size={18} />Исправить безопасные</button>
        </div>
        {fixPreview.data && (
          <div className="alert">
            Найдено: {fixPreview.data.total}; конфликтов: {fixPreview.data.conflicts}. Примеры: {fixPreview.data.sample_rows.slice(0, 5).map((row) => `${row.current_rcsme_reg_no} → ${row.suggested_rcsme_reg_no}`).join(', ')}
          </div>
        )}
        {fixMessage && <div className="alert success">{fixMessage}</div>}
        {(fixPreview.error || fixApply.error) && <div className="alert error">{errorMessage(fixPreview.error || fixApply.error)}</div>}
      </details>
    </div>
  )
}

function repeatSourceLabel(row: Record<string, unknown>) {
  return String(row.sample_name || row.normalized_sample_name || row.sample_name_raw || row.sample_object_no || '—')
}

function repeatParentLabel(row: Record<string, unknown>) {
  return String(row.parent_rcsme_reg_no || row.sample_object_no || 'оригинал не найден')
}

function repeatStatusLabel(row: Record<string, unknown>) {
  if (!row.parent_rcsme_reg_no && !row.sample_object_no) return 'оригинал не найден'
  if (row.will_create_repeat_object) return 'будет добавлен как повтор'
  if (row.repeat_object_exists) return 'повтор уже есть'
  return 'будет привязан как повтор'
}

function RepeatWarningPanel({ rows }: { rows: Array<Record<string, unknown>> }) {
  if (!rows.length) return null
  const visible = rows.slice(0, 24)
  return (
    <div className="structured-warning repeat-warning-panel">
      <div className="structured-warning-head">
        <strong>Повторные объекты</strong>
        <span>{rows.length}</span>
      </div>
      <div className="structured-warning-grid repeat-warning-grid" role="table" aria-label="Повторные объекты">
        <div role="columnheader">Из файла</div>
        <div role="columnheader">Оригинал</div>
        <div role="columnheader">Статус</div>
        {visible.map((row, index) => (
          <Fragment key={`${repeatSourceLabel(row)}-${index}`}>
            <div title={repeatSourceLabel(row)}>{repeatSourceLabel(row)}</div>
            <div title={repeatParentLabel(row)}>{repeatParentLabel(row)}</div>
            <div>{repeatStatusLabel(row)}</div>
          </Fragment>
        ))}
      </div>
      {rows.length > visible.length && <p>Показаны первые {visible.length}. Остальные: {rows.length - visible.length}.</p>}
    </div>
  )
}

function PdfWarningPanel({ items }: { items: ElectrophoresisPdfPreview['items'] }) {
  const rows = items.filter((item) => item.unmatched_count > 0 || item.warnings.length > 0)
  if (!rows.length) return null
  return (
    <div className="structured-warning pdf-warning-panel">
      <div className="structured-warning-head">
        <strong>Предупреждения по PDF</strong>
        <span>{rows.length}</span>
      </div>
      <div className="pdf-warning-list">
        {rows.map((item) => (
          <div className="pdf-warning-item" key={item.upload_id}>
            <strong title={item.filename}>{item.filename}</strong>
            <ul>
              {(item.warnings.length ? item.warnings : ['не найден объект']).map((warning) => <li key={warning}>{warning}</li>)}
            </ul>
          </div>
        ))}
      </div>
    </div>
  )
}

type PdfMode = '' | 'replace' | 'append'

function pdfSampleLabel(sample: Record<string, unknown>) {
  if (sample.is_control) return String(sample.control_label || sample.control_type || 'Контроль')
  return String(sample.sample_name_raw || sample.sample_object_no || '—')
}

function pdfObjectLabel(sample: Record<string, unknown>) {
  if (sample.is_control) return 'Контроль'
  return String(sample.object_rcsme_reg_no || sample.object_decree_no || '—')
}

function pdfRepeatLabel(sample: Record<string, unknown>) {
  if (!sample.is_repeat_sample) return '—'
  const raw = pdfSampleLabel(sample)
  const parent = String(sample.parent_rcsme_reg_no || sample.sample_object_no || '—')
  return sample.will_create_repeat_object ? `${raw} → повтор объекта ${parent}; будет добавлен` : `${raw} → повтор объекта ${parent}`
}

function pdfStatusLabel(item: ElectrophoresisPdfPreview['items'][number], mode: PdfMode) {
  const isControl = item.control_count > 0
  if (!item.matched_count && !isControl) return 'не найден объект'
  if (item.existing_count > 0 && !mode) return 'нужно выбрать действие'
  if (item.existing_count > 0 && mode === 'replace') return isControl ? 'контроль: замена' : 'готов к замене'
  if (item.existing_count > 0 && mode === 'append') return isControl ? 'контроль: добавить' : 'готов к добавлению'
  if (isControl && item.warnings.some((warning) => warning.includes('Выберите партии'))) return 'выберите партии для контроля'
  if (isControl) return `контроль ${pdfSampleLabel(item.samples[0] || {})}`
  return item.samples.some((sample) => sample.is_repeat_sample) ? 'повтор объекта' : 'объект найден'
}

export function ElectrophoresisImportPage() {
  const queryClient = useQueryClient()
  const [pdfPreview, setPdfPreview] = useState<ElectrophoresisPdfPreview | null>(null)
  const [fileModes, setFileModes] = useState<Record<string, PdfMode>>({})
  const [analysisDate, setAnalysisDate] = useState('')
  const [performer, setPerformer] = useState('')
  const [selectedYear, setSelectedYear] = useState('')
  const [selectedControlPartyIds, setSelectedControlPartyIds] = useState<string[]>([])
  const [message, setMessage] = useState('')
  const [previewError, setPreviewError] = useState('')
  const [previewProgress, setPreviewProgress] = useState<{ current: number; total: number; filename: string } | null>(null)
  const employees = useQuery({ queryKey: ['employees', 'electrophoresis-pdf-analysis'], queryFn: () => api.employees('', null, 'analysis'), staleTime: 60_000 })
  const partyYears = useQuery({ queryKey: ['parties', 'years', 'electrophoresis-import'], queryFn: api.partyYears, staleTime: 300_000 })
  const parties = useQuery({
    queryKey: ['parties', 'electrophoresis-import', selectedYear],
    queryFn: () => api.parties('', false, selectedYear ? Number(selectedYear) : null),
    enabled: Boolean(selectedYear),
    staleTime: 60_000
  })
  const controlPartyIds = selectedControlPartyIds.map((value) => Number(value)).filter((value) => Number.isFinite(value))
  const selectedControlParties = (parties.data?.items || []).filter((party) => selectedControlPartyIds.includes(String(party.id)))
  const selectedControlPartyLabel = selectedControlParties.length
    ? selectedControlParties.map((party) => party.party_no).join(', ')
    : 'не выбраны'
  const availableControlParties = parties.data?.items || []
  const uploadPdf = useMutation({
    mutationFn: ({ files, caseYear, partyIds }: { files: File[]; caseYear: number; partyIds: number[] }) =>
      api.previewElectrophoresisPdf(files, caseYear, partyIds)
  })

  const readyItems = (pdfPreview?.items || []).filter((item) => (item.matched_count > 0 || item.control_count > 0) && (!item.existing_count || fileModes[item.upload_id]))
  const repeatCount = (pdfPreview?.items || []).reduce((total, item) => total + item.samples.filter((sample) => Boolean(sample.is_repeat_sample)).length, 0)
  const controlCount = (pdfPreview?.items || []).reduce((total, item) => total + (item.control_count || 0), 0)
  useEffect(() => {
    if (!selectedYear && partyYears.data?.default_year) setSelectedYear(String(partyYears.data.default_year))
  }, [partyYears.data?.default_year, selectedYear])
  const commitPdf = useMutation({
    mutationFn: () => api.commitElectrophoresisPdf({
      upload_ids: readyItems.map((item) => item.upload_id),
      case_year: selectedYear ? Number(selectedYear) : null,
      control_party_ids: controlPartyIds,
      duplicate_mode: 'block',
      file_modes: Object.fromEntries(Object.entries(fileModes).filter(([, mode]) => mode)) as Record<string, 'replace' | 'append'>,
      analysis_date: analysisDate,
      analysis_performer: performer
    }),
    onSuccess: (result) => {
      const replacedText = result.files_replaced ? `; заменено PDF ${result.files_replaced}` : ''
      const controlsText = result.control_files_written ? `; контролей ${result.control_files_written}` : ''
      setMessage(`PDF фореза: сохранено ${result.files_written}${replacedText}${controlsText}; событий анализа ${result.analysis_events_written}; не найдено ${result.unmatched_count}`)
      queryClient.invalidateQueries({ queryKey: ['objects'] })
      queryClient.invalidateQueries({ queryKey: ['object'] })
      queryClient.invalidateQueries({ queryKey: ['party-stage-table'] })
      queryClient.invalidateQueries({ queryKey: ['party-progress'] })
      queryClient.invalidateQueries({ queryKey: ['dashboard'] })
      queryClient.invalidateQueries({ queryKey: ['parties'] })
    }
  })

  const hasControlReady = readyItems.some((item) => item.control_count > 0)
  const canCommit = Boolean(selectedYear && (!hasControlReady || controlPartyIds.length) && analysisDate && performer && readyItems.length && !commitPdf.isPending)

  function setPdfMode(uploadId: string, mode: PdfMode) {
    setFileModes((prev) => ({ ...prev, [uploadId]: mode }))
  }

  function setControlParties(nextIds: string[]) {
    setSelectedControlPartyIds(nextIds)
    clearPdfPreview()
  }

  async function previewPdfFiles(files: File[]) {
    if (!selectedYear) {
      setPreviewError('Сначала выберите год для сопоставления PDF фореза')
      return
    }
    setPreviewError('')
    setMessage('')
    setPdfPreview(null)
    setFileModes({})
    const aggregate: ElectrophoresisPdfPreview = { items: [], matched_count: 0, unmatched_count: 0, existing_count: 0, control_count: 0 }
    for (const [index, file] of files.entries()) {
      setPreviewProgress({ current: index + 1, total: files.length, filename: file.name })
      try {
        const result = await uploadPdf.mutateAsync({ files: [file], caseYear: Number(selectedYear), partyIds: controlPartyIds })
        aggregate.items.push(...result.items)
        aggregate.matched_count += result.matched_count
        aggregate.unmatched_count += result.unmatched_count
        aggregate.existing_count += result.existing_count
        aggregate.control_count += result.control_count
        setPdfPreview({ ...aggregate, items: [...aggregate.items] })
      } catch (error) {
        aggregate.items.push({
          upload_id: `error-${file.name}-${index}`,
          filename: file.name,
          file_sha256: '',
          samples: [],
          matched_count: 0,
          unmatched_count: 1,
          existing_count: 0,
          control_count: 0,
          warnings: [errorMessage(error)]
        })
        aggregate.unmatched_count += 1
        setPdfPreview({ ...aggregate, items: [...aggregate.items] })
        setPreviewError(`Не удалось прочитать часть PDF: ${file.name}. Остальные файлы обработаны.`)
      }
    }
    setPreviewProgress(null)
  }

  function clearPdfPreview() {
    setPdfPreview(null)
    setFileModes({})
    setMessage('')
    setPreviewError('')
    setPreviewProgress(null)
  }

  return (
    <div className="page">
      <PageHeader
        title="Импорт фореза"
        description="Загрузите PDF-файлы электрофореза. Для контрольных PDF выберите партии, к которым нужно привязать К+, К-, PC или NC."
      />
      <ImportIntro
        title="PDF фореза"
        description="Обычные файлы привязываются по имени PDF, контрольные файлы сохраняются как строки контролей на этапе Анализ."
        formats={['.pdf']}
        steps={['выбор года для сопоставления', 'preview обычных PDF и контролей', 'сохранение с датой и исполнителем анализа']}
        warnings={['для контролей можно выбрать несколько партий', 'повторы x/х/* привязываются к repeat-объектам', 'существующие PDF требуют replace или append']}
      />
      <section className="upload-panel">
        <div className="rt-import-actions electrophoresis-import-actions">
          <label>Год для сопоставления объектов
            <select value={selectedYear} onChange={(event) => { setSelectedYear(event.target.value); setSelectedControlPartyIds([]); clearPdfPreview() }} disabled={commitPdf.isPending}>
              <option value="">Выберите год</option>
              {(partyYears.data?.years ?? []).map((year) => <option value={year} key={year}>{year}</option>)}
            </select>
          </label>
          <label>Партии для контролей
            <MultiPartyPicker
              parties={availableControlParties}
              selectedIds={controlPartyIds}
              onChange={(ids) => setControlParties(ids.map(String))}
              disabled={!selectedYear || commitPdf.isPending}
              title="Партии для контролей"
            />
            <span className="field-hint">Используется только для К+, К-, PC, NC. Можно выбрать несколько.</span>
          </label>
        </div>
        <FileDropzone
          title="Перетащите PDF фореза сюда"
          description="или нажмите для выбора нескольких файлов"
          formats=".pdf"
          accept=".pdf,application/pdf"
          multiple
          disabled={!selectedYear}
          onFiles={(files) => void previewPdfFiles(files)}
        />
      </section>
      <RecentImports />
      {previewProgress && (
        <section className="section">
          <div className="import-progress-panel">
            <div className="import-progress-head">
              <strong>Предпросмотр PDF: {previewProgress.current} из {previewProgress.total}</strong>
              <span>{previewProgress.filename}</span>
            </div>
            <div className="import-progress-bar" aria-label="Прогресс PDF фореза">
              <span style={{ width: `${Math.round((previewProgress.current / previewProgress.total) * 100)}%` }} />
            </div>
          </div>
        </section>
      )}
      {previewError && <div className="alert error">{previewError}</div>}
      {uploadPdf.error && !pdfPreview && <div className="alert error">{errorMessage(uploadPdf.error)}</div>}
      {pdfPreview && (
        <section className="section">
          <div className="party-main-head">
            <h2>Предпросмотр PDF фореза</h2>
            <div className="toolbar-actions">
              <button className="icon-button" disabled={commitPdf.isPending} onClick={clearPdfPreview}><X size={18} />Очистить</button>
              <button className="primary compact" disabled={!canCommit} onClick={() => commitPdf.mutate()}><Check size={18} />{commitPdf.isPending ? 'Сохранение...' : 'Сохранить доступные PDF'}</button>
            </div>
          </div>
          <div className="summary-line">
            <strong>{pdfPreview.items.length} файлов</strong>
            <strong>{pdfPreview.matched_count} сопоставлено</strong>
            <strong>{pdfPreview.unmatched_count} без объекта</strong>
            <strong>{repeatCount} повторов</strong>
            <strong>{controlCount} контролей</strong>
            {pdfPreview.existing_count > 0 && <strong>{pdfPreview.existing_count} уже есть</strong>}
          </div>
          <div className="rt-import-actions electrophoresis-import-actions">
            <label>Год
              <input value={selectedYear || '—'} readOnly />
            </label>
            <label>Партия контролей
              <input value={selectedControlPartyLabel} readOnly />
            </label>
            <label>Дата анализа фореза
              <input type="date" value={analysisDate} onChange={(event) => setAnalysisDate(event.target.value)} disabled={commitPdf.isPending} />
            </label>
            <label>Исполнитель анализа
              <select value={performer} onChange={(event) => setPerformer(event.target.value)} disabled={commitPdf.isPending}>
                <option value="">Выберите сотрудника</option>
                {(employees.data ?? []).map((employee) => <option value={employee.full_name} key={employee.id}>{employee.short_name || employee.full_name}</option>)}
              </select>
            </label>
          </div>
          <div className="pdf-preview-table" role="table" aria-label="Предпросмотр PDF фореза">
            <div className="pdf-preview-row pdf-preview-head" role="row">
              {['Файл', 'Объект из файла', 'Объект в базе', 'Партия', 'Повтор', 'PDF уже есть', 'Статус', 'Действие'].map((column) => <div role="columnheader" key={column}>{column}</div>)}
            </div>
            {pdfPreview.items.map((item) => {
              const primarySample = item.samples[0] || {}
              const mode = fileModes[item.upload_id] || ''
              const isUnmatched = item.matched_count === 0 && item.control_count === 0
              return (
                <div className={`pdf-preview-row${isUnmatched ? ' is-unmatched' : ''}${item.existing_count ? ' has-existing' : ''}`} role="row" key={item.upload_id}>
                  <div title={item.filename}>{item.filename}</div>
                  <div title={item.samples.map(pdfSampleLabel).join(', ')}>{item.samples.map(pdfSampleLabel).join(', ') || '—'}</div>
                  <div title={item.samples.map(pdfObjectLabel).join(', ')}>{item.samples.map(pdfObjectLabel).join(', ') || '—'}</div>
                  <div title={String(primarySample.party_no || selectedControlPartyLabel || '—')}>{String(primarySample.party_no || selectedControlPartyLabel || '—')}</div>
                  <div title={item.samples.map(pdfRepeatLabel).join('; ')}>{item.samples.map(pdfRepeatLabel).filter((value) => value !== '—').join('; ') || '—'}</div>
                  <div>{item.existing_count || '—'}</div>
                  <div>{pdfStatusLabel(item, mode)}</div>
                  <div>
                    {item.existing_count > 0 ? (
                      <div className="pdf-row-actions">
                        <button type="button" className={mode === 'replace' ? 'primary compact' : 'icon-button'} onClick={() => setPdfMode(item.upload_id, mode === 'replace' ? '' : 'replace')}>Заменить</button>
                        <button type="button" className={mode === 'append' ? 'primary compact' : 'icon-button'} onClick={() => setPdfMode(item.upload_id, mode === 'append' ? '' : 'append')}>Добавить</button>
                      </div>
                    ) : (item.matched_count || item.control_count) ? '—' : 'не сохраняется'}
                  </div>
                </div>
              )
            })}
          </div>
          <PdfWarningPanel items={pdfPreview.items} />
          {message && <div className="alert success">{message}</div>}
          {commitPdf.error && <div className="alert error">{errorMessage(commitPdf.error)}</div>}
        </section>
      )}
    </div>
  )
}


function RtPreviewTable({ rows }: { rows: Array<Record<string, unknown>> }) {
  return (
    <div className="rt-preview-table" role="table" aria-label="Предпросмотр RT">
      <div className="rt-preview-row rt-preview-head" role="row">
        {['Объект из RT', 'Объект в базе', 'Партия', 'Длинная', 'Короткая', 'Y', 'Статус'].map((column) => <div role="columnheader" key={column}>{column}</div>)}
      </div>
      {rows.map((row, index) => (
        <div className={`rt-preview-row${row.matched ? '' : ' is-unmatched'}`} role="row" key={`${String(row.normalized_sample_name || row.sample_name_raw || 'row')}-${index}`}>
          <div role="cell">{String(row.normalized_sample_name || row.sample_name_raw || '—')}</div>
          <div role="cell">{String(row.object_rcsme_reg_no || row.sample_object_no || '—')}</div>
          <div role="cell">{String(row.party_no || '—')}</div>
          <div role="cell">{formatRtValue(row.long_quantity)}</div>
          <div role="cell">{formatRtValue(row.small_quantity)}</div>
          <div role="cell">{formatRtValue(row.y_quantity)}</div>
          <div role="cell">{Boolean(row.has_existing_rt) ? 'уже есть' : Boolean(row.matched) ? 'найден' : 'не найден в БД'}</div>
        </div>
      ))}
    </div>
  )
}

function formatRtValue(value: unknown) {
  if (typeof value === 'number') return value.toFixed(4)
  if (typeof value === 'string' && value !== '') {
    const parsed = Number(value)
    return Number.isFinite(parsed) ? parsed.toFixed(4) : value
  }
  return '—'
}
