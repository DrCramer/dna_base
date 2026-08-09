import { useQuery } from '@tanstack/react-query'
import { Database, FileDown, FilterX, Search } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { api } from '../api/client'
import type { RegistryObjectListItemBase } from '../api/types'
import { EmptyState, ErrorState, LoadingState, PageHeader } from '../components/ui'
import { useDebouncedValue } from '../hooks/useDebouncedValue'

type ObjectQuickFilter = 'no_object' | 'no_decree' | 'no_biomaterial' | 'burned' | 'no_analysis' | 'no_pcr' | 'has_repeats'

const objectQuickFilters: Array<{ id: ObjectQuickFilter; label: string }> = [
  { id: 'no_object', label: 'Нет объекта' },
  { id: 'no_decree', label: 'Нет постановления' },
  { id: 'no_biomaterial', label: 'Нет биоматериала' },
  { id: 'burned', label: 'Горелая кость' },
  { id: 'no_analysis', label: 'Без анализа' },
  { id: 'no_pcr', label: 'Без ПЦР' },
  { id: 'has_repeats', label: 'Есть повторы' }
]

const objectStages = [
  ['dna_extraction', 'Выделение'],
  ['realtime', 'RT'],
  ['pcr', 'PCR'],
  ['electrophoresis', 'Форез'],
  ['analysis', 'Анализ']
] as const

function display(value: string | number | null | undefined) {
  return value || '—'
}

function stageCount(row: RegistryObjectListItemBase, stage: string) {
  const count = row.stage_summary?.[stage]?.count ?? 0
  return count ? String(count) : '—'
}

function objectSortValue(row: RegistryObjectListItemBase, sortMode: string) {
  if (sortMode === 'party') return row.party_no || ''
  if (sortMode === 'last_stage') return row.last_stage_date || ''
  if (sortMode === 'investigator') return row.investigator || ''
  if (sortMode === 'decree') return row.decree_no || ''
  return Number(row.rcsme_reg_no_base ?? 0)
}

function objectText(row: RegistryObjectListItemBase) {
  return `${row.object_description || ''} ${row.object_type || ''}`.toLowerCase()
}

function hasAny(value: string, needles: string[]) {
  return needles.some((needle) => value.includes(needle))
}

function hasQuickFilter(row: RegistryObjectListItemBase, filter: ObjectQuickFilter) {
  const text = objectText(row)
  if (filter === 'no_object') {
    return hasAny(text, ['нет объекта', 'нет объект', 'без объекта', 'объект отсутствует', 'отсутствует объект'])
  }
  if (filter === 'no_decree') return !String(row.decree_no || '').trim()
  if (filter === 'no_biomaterial') return hasAny(text, ['нет биоматериала', 'без биоматериала', 'биоматериал отсутствует'])
  if (filter === 'burned') return hasAny(text, ['горелая кость', 'горел'])
  if (filter === 'no_analysis') return (row.stage_summary?.analysis?.count ?? 0) === 0
  if (filter === 'no_pcr') return (row.stage_summary?.pcr?.count ?? 0) === 0
  return Boolean(row.repeat_count || row.repeat_suffix || row.parent_object_id)
}

export function ObjectsPage({
  initialQuery,
  partyFilter,
  onQueryChange,
  onPartyFilterChange,
  onOpen,
  onPartyOpen
}: {
  initialQuery: string
  partyFilter: string | null
  onQueryChange: (query: string) => void
  onPartyFilterChange: (partyNo: string | null) => void
  onOpen: (id: number) => void
  onPartyOpen: (partyNo: string) => void
}) {
  const [q, setQ] = useState(initialQuery)
  const [yearFilter, setYearFilter] = useState('')
  const [sortMode, setSortMode] = useState('number_desc')
  const [stageFilter, setStageFilter] = useState('')
  const [typeFilter, setTypeFilter] = useState('')
  const [boxFilter, setBoxFilter] = useState('')
  const [onlyActive, setOnlyActive] = useState(true)
  const [quickFilters, setQuickFilters] = useState<Set<ObjectQuickFilter>>(() => new Set())
  const debouncedQ = useDebouncedValue(q.trim(), 250)
  const debouncedPartyFilter = useDebouncedValue((partyFilter || '').trim(), 250)
  useEffect(() => setQ(initialQuery), [initialQuery])

  function changeQuery(query: string) {
    setQ(query)
    onQueryChange(query)
  }

  function openParty(partyNo: string) {
    if (partyFilter === partyNo) return
    onPartyOpen(partyNo)
  }

  function resetFilters() {
    changeQuery('')
    onPartyFilterChange(null)
    setYearFilter('')
    setStageFilter('')
    setTypeFilter('')
    setBoxFilter('')
    setOnlyActive(true)
    setQuickFilters(new Set())
  }

  function toggleQuickFilter(filter: ObjectQuickFilter) {
    setQuickFilters((prev) => {
      const next = new Set(prev)
      if (next.has(filter)) next.delete(filter)
      else next.add(filter)
      return next
    })
  }

  const partyYears = useQuery({ queryKey: ['parties', 'years', 'objects'], queryFn: api.partyYears, staleTime: 300_000 })
  const { data, isFetching, isLoading, isError, error, refetch } = useQuery({
    queryKey: ['objects', debouncedQ, debouncedPartyFilter, yearFilter],
    queryFn: () => api.objects(debouncedQ, debouncedPartyFilter || null, yearFilter ? Number(yearFilter) : null),
    staleTime: 30_000,
    refetchOnWindowFocus: false,
    placeholderData: (previous) => previous
  })
  const rows = data?.items ?? []
  const total = data?.total ?? 0
  const clientFilteredRows = useMemo(() => rows.filter((row) => {
    if (onlyActive && row.status === 'archived') return false
    if (stageFilter && (row.stage_summary?.[stageFilter]?.count ?? 0) === 0) return false
    if (typeFilter && !String(row.object_type || '').toLowerCase().includes(typeFilter.toLowerCase())) return false
    if (boxFilter && !String(row.box_no || '').toLowerCase().includes(boxFilter.toLowerCase())) return false
    for (const filter of quickFilters) {
      if (!hasQuickFilter(row, filter)) return false
    }
    return true
  }), [boxFilter, onlyActive, quickFilters, rows, stageFilter, typeFilter])
  const sortedRows = useMemo(() => {
    const desc = sortMode.endsWith('_desc')
    const key = sortMode.replace(/_(asc|desc)$/, '')
    return [...clientFilteredRows].sort((a, b) => {
      const av = objectSortValue(a, key)
      const bv = objectSortValue(b, key)
      if (typeof av === 'number' && typeof bv === 'number') return desc ? bv - av : av - bv
      return desc ? String(bv).localeCompare(String(av), 'ru') : String(av).localeCompare(String(bv), 'ru')
    })
  }, [clientFilteredRows, sortMode])
  const visibleRows = sortedRows.slice(0, 300)

  return (
    <div className="page objects-page">
      <PageHeader
        title="Объекты"
        description="Общий список объектов с поиском по номерам, партиям, описанию, следователю и этапам."
        actions={(
          <>
            <button className="icon-button" onClick={resetFilters} title="Сбросить фильтры"><FilterX size={18} />Сбросить</button>
            <a className="icon-button" href={api.exportRegistryUrl(q, partyFilter, yearFilter ? Number(yearFilter) : null)} title="Экспорт"><FileDown size={18} />Экспорт</a>
          </>
        )}
      />
      <section className="section">
        <div className="objects-filter-panel">
          <div className="searchbox"><Search size={18} /><input value={q} onChange={(event) => changeQuery(event.target.value)} placeholder="Поиск по номеру, партии, описанию, следователю..." /></div>
          <select value={yearFilter} onChange={(event) => setYearFilter(event.target.value)} aria-label="Год">
            <option value="">Все годы</option>
            {(partyYears.data?.years ?? []).map((year) => <option key={year} value={year}>{year}</option>)}
          </select>
          <input value={partyFilter || ''} onChange={(event) => onPartyFilterChange(event.target.value.trim() || null)} placeholder="Партия" aria-label="Партия" />
          <select value={stageFilter} onChange={(event) => setStageFilter(event.target.value)} aria-label="Этап">
            <option value="">Все этапы</option>
            {objectStages.map(([stage, label]) => <option key={stage} value={stage}>Есть {label}</option>)}
          </select>
          <input value={typeFilter} onChange={(event) => setTypeFilter(event.target.value)} placeholder="Тип объекта" aria-label="Тип объекта" />
          <input value={boxFilter} onChange={(event) => setBoxFilter(event.target.value)} placeholder="Коробка" aria-label="Коробка" />
          <select value={sortMode} onChange={(event) => setSortMode(event.target.value)} aria-label="Сортировка">
            <option value="number_desc">№ рег РЦСМЭ ↓</option>
            <option value="number_asc">№ рег РЦСМЭ ↑</option>
            <option value="party_desc">Партия ↓</option>
            <option value="party_asc">Партия ↑</option>
            <option value="last_stage_desc">Последний этап ↓</option>
            <option value="investigator_asc">Следователь ↑</option>
            <option value="decree_asc">Постановление ↑</option>
          </select>
          <label className="inline-check objects-active-toggle">
            <input type="checkbox" checked={onlyActive} onChange={(event) => setOnlyActive(event.target.checked)} />
            Только активные
          </label>
        </div>
        <div className="quick-filter-row">
          {partyFilter && <button className="icon-button" onClick={() => onPartyFilterChange(null)}>Партия {partyFilter} ×</button>}
          {yearFilter && <button className="icon-button" onClick={() => setYearFilter('')}>Год {yearFilter} ×</button>}
          {objectQuickFilters.map((filter) => (
            <button
              className={`icon-button${quickFilters.has(filter.id) ? ' active' : ''}`}
              key={filter.id}
              onClick={() => toggleQuickFilter(filter.id)}
            >
              {filter.label}
            </button>
          ))}
          <span className="muted-note">
            {isFetching && !isLoading
              ? 'Обновление...'
              : `${visibleRows.length} показано из ${total}${sortedRows.length > visibleRows.length ? `, первые ${visibleRows.length}` : ''}`}
          </span>
        </div>
      </section>
      {isLoading ? (
        <LoadingState title="Загрузка объектов..." rows={7} />
      ) : isError ? (
        <ErrorState error={error} onRetry={() => void refetch()} />
      ) : sortedRows.length ? (
        <div className="table-wrap">
          <div className="registry-table" role="table" aria-label="Объекты реестра">
            <div className="registry-row registry-head objects-grid" role="row">
              <div role="columnheader">Партия</div>
              <div role="columnheader">№ рег РЦСМЭ</div>
              <div role="columnheader">№ постановления</div>
              <div role="columnheader">№ в в/ч №522</div>
              <div role="columnheader">Выделение</div>
              <div role="columnheader">RT</div>
              <div role="columnheader">PCR</div>
              <div role="columnheader">Форез</div>
              <div role="columnheader">Анализ</div>
              <div role="columnheader">Следователь</div>
              <div role="columnheader">Описание</div>
              <div role="columnheader">Тип</div>
              <div role="columnheader">Повт.</div>
              <div role="columnheader">Статус</div>
            </div>
            {visibleRows.map((row: RegistryObjectListItemBase) => (
              <div
                className="registry-row registry-body-row objects-grid"
                role="row"
                tabIndex={0}
                key={row.id}
                onClick={() => onOpen(row.id)}
                onKeyDown={(event) => {
                  if (event.key === 'Enter' || event.key === ' ') {
                    event.preventDefault()
                    onOpen(row.id)
                  }
                }}
              >
                <div role="cell">
                  {row.party_no
                    ? <button type="button" className="link-button" onClick={(event) => { event.stopPropagation(); openParty(row.party_no!) }}>{row.party_no}</button>
                    : '—'}
                </div>
                <div role="cell">{display(row.rcsme_reg_no)}</div>
                <div role="cell">{display(row.decree_no)}</div>
                <div role="cell">{display(row.external_military_no)}</div>
                <div role="cell"><span className="stage-badge">{stageCount(row, 'dna_extraction')}</span></div>
                <div role="cell"><span className="stage-badge">{stageCount(row, 'realtime')}</span></div>
                <div role="cell"><span className="stage-badge">{stageCount(row, 'pcr')}</span></div>
                <div role="cell"><span className="stage-badge">{stageCount(row, 'electrophoresis')}</span></div>
                <div role="cell"><span className="stage-badge">{stageCount(row, 'analysis')}</span></div>
                <div role="cell">{display(row.investigator)}</div>
                <div role="cell">{display(row.object_description)}</div>
                <div role="cell">{display(row.object_type)}</div>
                <div role="cell">{row.repeat_count || '—'}</div>
                <div role="cell"><span className="status">{row.status || 'new'}</span></div>
              </div>
            ))}
          </div>
        </div>
      ) : (
        <EmptyState
          icon={<Database size={22} />}
          title="Объекты не найдены"
          actions={<button className="icon-button" onClick={() => { changeQuery(''); onPartyFilterChange(null) }}>Сбросить поиск</button>}
        >
          Измените поисковый запрос или откройте партию из списка.
        </EmptyState>
      )}
    </div>
  )
}
