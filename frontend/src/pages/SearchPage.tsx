import { useQuery } from '@tanstack/react-query'
import { Search, SearchCheck } from 'lucide-react'
import { useState } from 'react'
import { api } from '../api/client'
import { EmptyState, LoadingState, PageHeader } from '../components/ui'
import { RcsmeLookup } from '../components/RcsmeLookup'
import { useDebouncedValue } from '../hooks/useDebouncedValue'

const searchExamples = ['6606-1', '6606-2026', 'ии1285', 'партия 196', 'Непомнящая', 'GlobalFiler', 'горелая кость']
const searchTabs = [['general', 'Общий поиск'], ['rcsme', 'Таблица по номерам РЦСМЭ']] as const
type SearchTab = typeof searchTabs[number][0]

export function SearchPage({
  onObjectOpen,
  onPartyOpen
}: {
  onObjectOpen: (id: number) => void
  onPartyOpen: (partyNo: string) => void
}) {
  const [q, setQ] = useState('')
  const [tab, setTab] = useState<SearchTab>('general')
  const [lookupOpened, setLookupOpened] = useState(false)
  const openTab = (key: SearchTab) => {
    setTab(key)
    if (key === 'rcsme') setLookupOpened(true)
  }
  const debouncedQ = useDebouncedValue(q.trim(), 250)
  const { data, isFetching } = useQuery({
    queryKey: ['global-search', debouncedQ],
    queryFn: () => api.objects(debouncedQ),
    enabled: tab === 'general' && debouncedQ.length > 1,
    staleTime: 20_000,
    refetchOnWindowFocus: false
  })
  const parties = useQuery({
    queryKey: ['global-search', 'parties', debouncedQ],
    queryFn: () => api.parties(debouncedQ, false),
    enabled: tab === 'general' && debouncedQ.length > 1,
    staleTime: 20_000,
    refetchOnWindowFocus: false
  })
  const objects = debouncedQ.length > 1 ? data?.items ?? [] : []
  const partyRows = debouncedQ.length > 1 ? parties.data?.items ?? [] : []
  const foundCount = (data?.total ?? 0) + partyRows.length
  return (
    <div className="page">
      <PageHeader title="Поиск" />
      <div className="protocol-source-tabs search-tabs" role="tablist" aria-label="Режим поиска">
        {searchTabs.map(([key, label]) => (
          <button key={key} type="button" role="tab" id={`search-tab-${key}`} aria-controls={`search-panel-${key}`} aria-selected={tab === key}
            tabIndex={tab === key ? 0 : -1} className={tab === key ? 'active' : ''} onClick={() => openTab(key)}
            onKeyDown={(event) => {
              const next = event.key === 'Home' ? 'general' : event.key === 'End' ? 'rcsme'
                : event.key === 'ArrowLeft' || event.key === 'ArrowRight' ? (key === 'general' ? 'rcsme' : 'general') : null
              if (next) { event.preventDefault(); openTab(next); document.getElementById(`search-tab-${next}`)?.focus() }
            }}>{label}</button>
        ))}
      </div>
      <div className="search-tab-panel" id="search-panel-general" role="tabpanel" aria-labelledby="search-tab-general" hidden={tab !== 'general'}>
      <section className="section">
        <div className="searchbox"><Search size={18} /><input value={q} onChange={(event) => setQ(event.target.value)} placeholder="Номер, партия, исполнитель, метод, объект..." /></div>
        <div className="quick-filter-row">
          {['Нет объекта', 'Нет постановления', 'Пустой конверт', 'Горелая кость', 'Без анализа', 'Есть повторы', 'Проблемные партии'].map((item) => (
            <button className="icon-button" key={item} onClick={() => setQ(item)}>{item}</button>
          ))}
          <span className="muted-note">{isFetching || parties.isFetching ? 'Поиск...' : `${foundCount} найдено`}</span>
        </div>
      </section>
      <section className="section">
        {partyRows.length > 0 && (
          <div className="search-result-group">
            <h2>Партии</h2>
            <div className="mini-object-list">
              {partyRows.map((party) => (
                <button key={party.id} onClick={() => onPartyOpen(party.party_no)}>
                  <span>Партия {party.party_no}</span>
                  <em>{party.case_year || 'год не указан'} · {party.object_count} объектов · {party.status}</em>
                </button>
              ))}
            </div>
          </div>
        )}
        {objects.length > 0 && (
          <div className="search-result-group">
            <h2>Объекты</h2>
            <div className="mini-object-list">
              {objects.map((item) => (
                <button key={item.id} onClick={() => onObjectOpen(item.id)}>
                  <span>{item.rcsme_reg_no || item.decree_no || `Объект ${item.id}`}</span>
                  <em>{item.party_no ? `${item.party_no} · ` : ''}{item.last_stage || item.object_type || item.status || 'new'}</em>
                </button>
              ))}
            </div>
          </div>
        )}
        {(isFetching || parties.isFetching) && debouncedQ.length > 1 && !objects.length && !partyRows.length && <LoadingState title="Идёт поиск..." rows={4} />}
        {q.trim().length < 2 && (
          <EmptyState icon={<SearchCheck size={22} />} title="Введите запрос">
            Можно искать по № рег РЦСМЭ, № постановления, № в в/ч №522, партии, следователю, исполнителю, методу, типу объекта или комментарию.
          </EmptyState>
        )}
        {q.trim().length < 2 && (
          <div className="search-examples">
            <strong>Что можно искать</strong>
            <div className="quick-filter-row">
              {searchExamples.map((example) => (
                <button className="icon-button" key={example} onClick={() => setQ(example)}>{example}</button>
              ))}
            </div>
          </div>
        )}
        {debouncedQ.length > 1 && !objects.length && !partyRows.length && !isFetching && !parties.isFetching && (
          <EmptyState title="Ничего не найдено">
            Проверьте номер или попробуйте более общий запрос.
          </EmptyState>
        )}
      </section>
      </div>
      <div className="search-tab-panel" id="search-panel-rcsme" role="tabpanel" aria-labelledby="search-tab-rcsme" hidden={tab !== 'rcsme'}>
        {lookupOpened ? <RcsmeLookup /> : null}
      </div>
    </div>
  )
}
