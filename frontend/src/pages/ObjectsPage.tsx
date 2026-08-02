import { useQuery } from '@tanstack/react-query'
import { FileDown, Search } from 'lucide-react'
import { useEffect, useState } from 'react'
import { api } from '../api/client'
import type { RegistryObjectListItemBase } from '../api/types'

function display(value: string | number | null | undefined) {
  return value || '—'
}

function stageCount(row: RegistryObjectListItemBase, stage: string) {
  const count = row.stage_summary?.[stage]?.count ?? 0
  return count ? String(count) : '—'
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
  useEffect(() => setQ(initialQuery), [initialQuery])

  function changeQuery(query: string) {
    setQ(query)
    onQueryChange(query)
  }

  function openParty(partyNo: string) {
    if (partyFilter === partyNo) return
    onPartyOpen(partyNo)
  }

  const { data, isFetching } = useQuery({
    queryKey: ['objects', q, partyFilter],
    queryFn: () => api.objects(q, partyFilter),
    staleTime: 30_000,
    refetchOnWindowFocus: false,
    placeholderData: (previous) => previous
  })
  const rows = data?.items ?? []
  const total = data?.total ?? 0

  return (
    <div className="page">
      <header className="page-header">
        <h1>Объекты</h1>
        <a className="icon-button" href={api.exportRegistryUrl(q, partyFilter)} title="Экспорт"><FileDown size={18} />Экспорт</a>
      </header>
      <div className="toolbar">
        <div className="searchbox"><Search size={18} /><input value={q} onChange={(event) => changeQuery(event.target.value)} placeholder="Поиск по номеру, партии, описанию, следователю..." /></div>
        {partyFilter && <button className="icon-button" onClick={() => onPartyFilterChange(null)}>{partyFilter} ×</button>}
        <span>{isFetching ? 'Обновление...' : `${total} объектов`}</span>
      </div>
      <div className="table-wrap">
        <div className="registry-table" role="table" aria-label="Объекты реестра">
          <div className="registry-row registry-head objects-grid" role="row">
            <div role="columnheader">Партия</div>
            <div role="columnheader">№ рег РЦСМЭ</div>
            <div role="columnheader">№ постановления</div>
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
          {rows.map((row: RegistryObjectListItemBase) => (
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
    </div>
  )
}
