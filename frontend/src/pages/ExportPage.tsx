import { useQuery } from '@tanstack/react-query'
import { Check, FileDown, FilterX } from 'lucide-react'
import { useMemo, useState } from 'react'
import { api, type RegistryExportOptions } from '../api/client'
import { EmptyState, ErrorState, LoadingState, MultiPartyPicker, PageHeader } from '../components/ui'
import { useDebouncedValue } from '../hooks/useDebouncedValue'

type ExportMode = 'all' | 'parties' | 'objects' | 'search' | 'leader'

const exportModes: Array<{ id: ExportMode; title: string; description: string }> = [
  { id: 'all', title: 'Весь реестр', description: 'Полная выгрузка по выбранному году и фильтрам.' },
  { id: 'parties', title: 'По партиям', description: 'Отдельные партии или диапазон партий.' },
  { id: 'objects', title: 'По объектам', description: 'Конкретные номера РЦСМЭ или постановлений.' },
  { id: 'search', title: 'По результатам поиска', description: 'Выгрузка по текстовому запросу.' },
  { id: 'leader', title: 'Отчёт руководителя', description: 'Сводная управленческая выгрузка.' }
]

const exportBlocks = [
  'Регистрация',
  'Пробоподготовка',
  'Измельчение',
  'Выделение',
  'RealTime',
  'ПЦР',
  'Электрофорез',
  'Анализ',
  'Контроль партии',
  'История повторов',
  'RT-результаты',
  'PDF фореза'
]

export function ExportPage() {
  const partyYears = useQuery({ queryKey: ['parties', 'years'], queryFn: api.partyYears, staleTime: 300_000 })
  const [mode, setMode] = useState<ExportMode>('all')
  const [q, setQ] = useState('')
  const [year, setYear] = useState('')
  const [partyRange, setPartyRange] = useState('')
  const [selectedPartyIds, setSelectedPartyIds] = useState<number[]>([])
  const [objectNos, setObjectNos] = useState('')
  const [stage, setStage] = useState('')
  const [period, setPeriod] = useState('year')
  const [includeArchived, setIncludeArchived] = useState(false)
  const [onlyProblematic, setOnlyProblematic] = useState(false)
  const [downloading, setDownloading] = useState(false)
  const [downloadError, setDownloadError] = useState('')
  const parties = useQuery({
    queryKey: ['export-parties', year, includeArchived],
    queryFn: () => api.parties('', includeArchived, year ? Number(year) : null),
    staleTime: 60_000
  })
  const selectedParties = useMemo(() => (parties.data?.items ?? []).filter((party) => selectedPartyIds.includes(party.id)), [parties.data, selectedPartyIds])
  const registryOptions = useMemo<RegistryExportOptions>(() => ({
    q: mode === 'search' || mode === 'objects' ? q.trim() || undefined : undefined,
    partyNo: mode === 'objects' ? partyRange.trim() || undefined : undefined,
    partyIds: mode === 'parties' ? selectedPartyIds : undefined,
    objectNos: mode === 'objects' ? objectNos : undefined,
    year: year ? Number(year) : undefined,
    stageType: stage || undefined,
    includeArchived,
    onlyProblematic: mode !== 'objects' && onlyProblematic
  }), [includeArchived, mode, objectNos, onlyProblematic, partyRange, q, selectedPartyIds, stage, year])
  const debouncedRegistryOptions = useDebouncedValue(registryOptions, 300)
  const hasScope = mode === 'parties'
    ? selectedPartyIds.length > 0
    : mode === 'objects'
      ? objectNos.trim().length > 0
      : mode === 'search'
        ? q.trim().length > 1
        : true
  const registryPreview = useQuery({
    queryKey: ['export-registry-preview', debouncedRegistryOptions],
    queryFn: () => api.exportRegistryPreview(debouncedRegistryOptions),
    enabled: mode !== 'leader' && hasScope,
    staleTime: 30_000
  })
  const leaderPeriod = useMemo(() => {
    const now = new Date()
    const selectedYear = year ? Number(year) : now.getFullYear()
    const end = new Date(selectedYear, period === 'year' ? 11 : now.getMonth() + 1, period === 'year' ? 31 : 0)
    let start = new Date(selectedYear, 0, 1)
    if (period === 'month') start = new Date(selectedYear, now.getMonth(), 1)
    if (period === 'quarter') start = new Date(selectedYear, Math.floor(now.getMonth() / 3) * 3, 1)
    const iso = (value: Date) => value.toISOString().slice(0, 10)
    return { date_from: iso(start), date_to: iso(end) }
  }, [period, year])
  const leaderFilters = useMemo(() => ({
    case_year: year || undefined,
    party_ids: selectedPartyIds.length ? selectedPartyIds.join(',') : undefined,
    stage_type: stage || undefined,
    include_archived: includeArchived || undefined,
    only_problematic: onlyProblematic || undefined,
    ...leaderPeriod
  }), [includeArchived, leaderPeriod, onlyProblematic, selectedPartyIds, stage, year])
  const downloadHref = mode === 'leader'
    ? api.reportExportUrl('overview', leaderFilters)
    : api.exportRegistryUrl(registryOptions)
  const downloadReady = hasScope && (mode === 'leader' || (registryPreview.data?.object_count ?? 0) > 0)
  const scopedParties = mode === 'parties'
    ? selectedParties
    : mode === 'leader' && selectedParties.length
      ? selectedParties
      : (parties.data?.items ?? [])
  const leaderObjectCount = scopedParties.reduce((sum, party) => sum + party.object_count, 0)

  async function downloadExport() {
    if (!downloadReady || downloading) return
    setDownloading(true)
    setDownloadError('')
    try {
      const response = await fetch(downloadHref, { credentials: 'include' })
      if (!response.ok) {
        const payload = await response.json().catch(() => null)
        throw new Error(payload?.detail || `Сервер вернул ошибку ${response.status}`)
      }
      const blob = await response.blob()
      const disposition = response.headers.get('content-disposition') || ''
      const matchedName = disposition.match(/filename="?([^";]+)"?/i)?.[1]
      const objectUrl = URL.createObjectURL(blob)
      const anchor = document.createElement('a')
      anchor.href = objectUrl
      anchor.download = matchedName || (mode === 'leader' ? 'report.xlsx' : 'registry.xlsx')
      anchor.click()
      window.setTimeout(() => URL.revokeObjectURL(objectUrl), 1000)
    } catch (error) {
      setDownloadError(error instanceof Error ? error.message : 'Не удалось подготовить файл')
    } finally {
      setDownloading(false)
    }
  }

  function reset() {
    setMode('all')
    setQ('')
    setYear('')
    setPartyRange('')
    setSelectedPartyIds([])
    setObjectNos('')
    setStage('')
    setPeriod('year')
    setIncludeArchived(false)
    setOnlyProblematic(false)
  }

  return (
    <div className="page">
      <PageHeader
        title="Экспорт"
        description="Сформируйте Excel-реестр или выгрузку по выбранным партиям, объектам, этапам и фильтрам."
        actions={(
          <>
            <button className="icon-button" onClick={reset}><FilterX size={18} />Сбросить</button>
            <button className="primary download" disabled={!downloadReady || downloading} onClick={downloadExport}>
              <FileDown size={18} />{downloading ? 'Готовим файл...' : mode === 'leader' ? 'Скачать отчёт' : 'Скачать Excel'}
            </button>
          </>
        )}
      />
      {downloadError ? <div className="alert error" role="alert">{downloadError}</div> : null}

      <section className="section">
        <div className="section-head">
          <div>
            <h2>Режим экспорта</h2>
            <p>Выберите сценарий, а затем уточните фильтры и состав выгрузки.</p>
          </div>
        </div>
        <div className="export-mode-grid">
          {exportModes.map((item) => (
            <button key={item.id} type="button" aria-pressed={mode === item.id} className={`mode-card${mode === item.id ? ' active' : ''}`} onClick={() => setMode(item.id)}>
              {mode === item.id ? <Check className="mode-card-check" size={17} aria-hidden="true" /> : null}
              <strong>{item.title}</strong>
              <span>{item.description}</span>
            </button>
          ))}
        </div>
      </section>

      <section className="section">
        <h2>Фильтры</h2>
        <div className="filter-panel">
          <label>Год
            <select value={year} onChange={(event) => setYear(event.target.value)}>
              <option value="">Все годы</option>
              {(partyYears.data?.years ?? []).map((item) => <option value={item} key={item}>{item}</option>)}
            </select>
          </label>
          {(mode === 'parties' || mode === 'leader') ? (
            <label>Партии
              <MultiPartyPicker parties={parties.data?.items ?? []} selectedIds={selectedPartyIds} onChange={setSelectedPartyIds} disabled={parties.isLoading} />
            </label>
          ) : null}
          {mode === 'objects' ? (
            <>
              <label>№ рег РЦСМЭ / диапазон
                <textarea rows={2} value={objectNos} onChange={(event) => setObjectNos(event.target.value)} placeholder={'3303-1\n3304-1'} />
              </label>
              <label>Партия
                <input value={partyRange} onChange={(event) => setPartyRange(event.target.value)} placeholder="Например, 160" />
              </label>
              <label>Дополнительный поиск
                <input value={q} onChange={(event) => setQ(event.target.value)} placeholder="следователь, коробка, комментарий..." />
              </label>
            </>
          ) : null}
          {mode === 'search' ? (
            <label>Текущий поисковый запрос
              <input autoFocus value={q} onChange={(event) => setQ(event.target.value)} placeholder="номер, следователь, коробка, комментарий..." />
            </label>
          ) : null}
          {mode === 'leader' ? (
            <label>Период
              <select value={period} onChange={(event) => setPeriod(event.target.value)}>
                <option value="month">Месяц</option>
                <option value="quarter">Квартал</option>
                <option value="year">Год</option>
              </select>
            </label>
          ) : null}
          <label>Этап
            <select value={stage} onChange={(event) => setStage(event.target.value)}>
              <option value="">Все этапы</option>
              {[
                ['registration', 'Регистрация'],
                ['sample_prep', 'Пробоподготовка'],
                ['milling', 'Измельчение'],
                ['dna_extraction', 'Выделение'],
                ['realtime', 'RealTime'],
                ['pcr', 'ПЦР'],
                ['electrophoresis', 'Электрофорез'],
                ['analysis', 'Анализ']
              ].map(([value, label]) => <option value={value} key={value}>{label}</option>)}
            </select>
          </label>
          <label>Формат
            <select value="xlsx" disabled>
              <option value="xlsx">{mode === 'leader' ? 'Excel отчёта руководителя' : 'Excel старого формата реестра'}</option>
            </select>
          </label>
        </div>
        <div className="quick-filter-row">
          <label className="inline-check"><input type="checkbox" checked={!includeArchived} onChange={(event) => setIncludeArchived(!event.target.checked)} />Только активные</label>
          <label className="inline-check"><input type="checkbox" checked={includeArchived} onChange={(event) => setIncludeArchived(event.target.checked)} />Включить архивные</label>
          {mode !== 'objects' ? <label className="inline-check"><input type="checkbox" checked={onlyProblematic} onChange={(event) => setOnlyProblematic(event.target.checked)} />Только проблемные</label> : null}
        </div>
      </section>

      <section className="section">
        <h2>Состав выгрузки</h2>
        <p className="section-hint">Стандартный Excel сохраняет привычные названия и порядок колонок реестра.</p>
        <h3 className="export-group-title">Этапы</h3>
        <div className="export-option-list">
          {exportBlocks.slice(0, 8).map((block) => (
            <label className="inline-check" key={block}>
              <input type="checkbox" checked disabled />
              {block}
            </label>
          ))}
        </div>
        <h3 className="export-group-title">Дополнительно</h3>
        <p className="section-hint">Контроль партии, история попыток и файлы фореза выгружаются через профильные отчёты. В стандартный реестр они не добавляются, чтобы не менять совместимость Excel.</p>
      </section>

      <section className="section">
        <h2>Предпросмотр</h2>
        {!hasScope ? (
          <EmptyState title={mode === 'parties' || mode === 'leader' ? 'Выберите партии' : mode === 'objects' ? 'Укажите номера объектов' : 'Введите поисковый запрос'}>
            После выбора система рассчитает точный объём файла.
          </EmptyState>
        ) : registryPreview.isError && mode !== 'leader' ? (
          <ErrorState title="Не удалось рассчитать объём выгрузки" onRetry={() => registryPreview.refetch()} />
        ) : registryPreview.isLoading && mode !== 'leader' ? (
          <LoadingState title="Рассчитываем объём выгрузки..." rows={3} />
        ) : (
          <div className="overview-grid export-preview-grid">
            <div><span>Режим</span><strong>{exportModes.find((item) => item.id === mode)?.title}</strong></div>
            <div><span>Год</span><strong>{year || 'Все годы'}</strong></div>
            <div><span>Партии</span><strong>{mode === 'leader' ? scopedParties.length : registryPreview.data?.party_count ?? 0}</strong></div>
            <div><span>Объекты</span><strong>{mode === 'leader' ? leaderObjectCount : registryPreview.data?.object_count ?? 0}</strong></div>
            <div><span>Разделов</span><strong>{mode === 'leader' ? 'сводный отчёт' : exportBlocks.slice(0, 8).length}</strong></div>
            <div><span>Формат</span><strong>{mode === 'leader' ? 'Excel отчёта' : 'старый Excel'}</strong></div>
          </div>
        )}
      </section>
    </div>
  )
}
