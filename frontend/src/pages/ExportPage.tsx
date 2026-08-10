import { useQuery } from '@tanstack/react-query'
import { Check, FileDown, FilterX } from 'lucide-react'
import { useMemo, useState } from 'react'
import { api } from '../api/client'
import { EmptyState, LoadingState, MultiPartyPicker, PageHeader } from '../components/ui'

type ExportMode = 'all' | 'parties' | 'objects' | 'search' | 'leader'
type ExportFormat = 'legacy' | 'extended' | 'csv'

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
  const [format, setFormat] = useState<ExportFormat>('legacy')
  const [q, setQ] = useState('')
  const [year, setYear] = useState('')
  const [partyRange, setPartyRange] = useState('')
  const [selectedPartyIds, setSelectedPartyIds] = useState<number[]>([])
  const [objectNos, setObjectNos] = useState('')
  const [stage, setStage] = useState('')
  const [period, setPeriod] = useState('year')
  const [onlyActive, setOnlyActive] = useState(true)
  const [includeArchived, setIncludeArchived] = useState(false)
  const [onlyProblematic, setOnlyProblematic] = useState(false)
  const [selectedBlocks, setSelectedBlocks] = useState(() => new Set(exportBlocks.slice(0, 8)))
  const parties = useQuery({
    queryKey: ['export-parties', year, includeArchived],
    queryFn: () => api.parties('', includeArchived, year ? Number(year) : null),
    staleTime: 60_000
  })
  const selectedParties = useMemo(() => (parties.data?.items ?? []).filter((party) => selectedPartyIds.includes(party.id)), [parties.data, selectedPartyIds])
  const scopedParties = mode === 'parties' || mode === 'leader' ? selectedParties : (parties.data?.items ?? [])
  const scopedObjectCount = scopedParties.reduce((sum, party) => sum + party.object_count, 0)
  const query = useMemo(() => {
    const modeQuery = mode === 'objects' ? objectNos : mode === 'search' ? q : q
    return [modeQuery, partyRange, selectedParties.map((party) => party.party_no).join(' '), stage, onlyProblematic ? 'проблемные' : ''].filter(Boolean).join(' ')
  }, [mode, objectNos, onlyProblematic, partyRange, q, selectedParties, stage])
  const downloadParty = selectedParties.length === 1 ? selectedParties[0].party_no : null

  function toggleBlock(block: string) {
    setSelectedBlocks((prev) => {
      const next = new Set(prev)
      if (next.has(block)) next.delete(block)
      else next.add(block)
      return next
    })
  }

  function reset() {
    setMode('all')
    setFormat('legacy')
    setQ('')
    setYear('')
    setPartyRange('')
    setSelectedPartyIds([])
    setObjectNos('')
    setStage('')
    setPeriod('year')
    setOnlyActive(true)
    setIncludeArchived(false)
    setOnlyProblematic(false)
    setSelectedBlocks(new Set(exportBlocks.slice(0, 8)))
  }

  return (
    <div className="page">
      <PageHeader
        title="Экспорт"
        description="Сформируйте Excel-реестр или выгрузку по выбранным партиям, объектам, этапам и фильтрам."
        actions={(
          <>
            <button className="icon-button" onClick={reset}><FilterX size={18} />Сбросить</button>
            <a className="primary download" href={api.exportRegistryUrl(query, downloadParty, year ? Number(year) : null)}><FileDown size={18} />Скачать Excel</a>
          </>
        )}
      />

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
              {['Регистрация', 'Пробоподготовка', 'Выделение', 'RealTime', 'ПЦР', 'Электрофорез', 'Анализ'].map((item) => <option value={item} key={item}>{item}</option>)}
            </select>
          </label>
          <label>Формат
            <select value={format} onChange={(event) => setFormat(event.target.value as ExportFormat)}>
              <option value="legacy">Excel старого формата реестра</option>
              <option value="extended">Excel расширенный</option>
              <option value="csv">CSV</option>
            </select>
          </label>
        </div>
        <div className="quick-filter-row">
          <label className="inline-check"><input type="checkbox" checked={onlyActive} onChange={(event) => setOnlyActive(event.target.checked)} />Только активные</label>
          <label className="inline-check"><input type="checkbox" checked={includeArchived} onChange={(event) => setIncludeArchived(event.target.checked)} />Включить архивные</label>
          <label className="inline-check"><input type="checkbox" checked={onlyProblematic} onChange={(event) => setOnlyProblematic(event.target.checked)} />Только проблемные</label>
        </div>
      </section>

      <section className="section">
        <h2>Состав выгрузки</h2>
        <h3 className="export-group-title">Этапы</h3>
        <div className="export-option-list">
          {exportBlocks.slice(0, 8).map((block) => (
            <label className="inline-check" key={block}>
              <input type="checkbox" checked={selectedBlocks.has(block)} onChange={() => toggleBlock(block)} />
              {block}
            </label>
          ))}
        </div>
        <h3 className="export-group-title">Дополнительно</h3>
        <div className="export-option-list">
          {exportBlocks.slice(8).map((block) => (
            <label className="inline-check" key={block}>
              <input type="checkbox" checked={selectedBlocks.has(block)} onChange={() => toggleBlock(block)} />
              {block}
            </label>
          ))}
        </div>
      </section>

      <section className="section">
        <h2>Предпросмотр</h2>
        {selectedBlocks.size ? (
          parties.isLoading ? <LoadingState title="Рассчитываем объём выгрузки..." rows={3} /> : <div className="overview-grid export-preview-grid">
            <div><span>Режим</span><strong>{exportModes.find((item) => item.id === mode)?.title}</strong></div>
            <div><span>Год</span><strong>{year || 'Все годы'}</strong></div>
            <div><span>Партии</span><strong>{scopedParties.length}</strong></div>
            <div><span>Объекты</span><strong>{scopedObjectCount}</strong></div>
            <div><span>Разделов</span><strong>{selectedBlocks.size}</strong></div>
            <div><span>Формат</span><strong>{format === 'legacy' ? 'старый Excel' : format === 'extended' ? 'расширенный Excel' : 'CSV'}</strong></div>
          </div>
        ) : (
          <EmptyState title="Нет данных для экспорта">
            Выберите хотя бы один раздел выгрузки или измените фильтры.
          </EmptyState>
        )}
      </section>
    </div>
  )
}
