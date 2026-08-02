import { useQuery } from '@tanstack/react-query'
import { Search } from 'lucide-react'
import { useState } from 'react'
import { api } from '../api/client'

export function SearchPage({ onObjectOpen }: { onObjectOpen: (id: number) => void }) {
  const [q, setQ] = useState('')
  const { data, isFetching } = useQuery({
    queryKey: ['global-search', q],
    queryFn: () => api.objects(q),
    enabled: q.trim().length > 1,
    staleTime: 20_000,
    refetchOnWindowFocus: false
  })
  return (
    <div className="page">
      <header className="page-header">
        <h1>Поиск</h1>
      </header>
      <div className="toolbar">
        <div className="searchbox"><Search size={18} /><input value={q} onChange={(event) => setQ(event.target.value)} placeholder="Номер, партия, исполнитель, метод, объект..." /></div>
        <span>{isFetching ? 'Поиск...' : `${data?.total ?? 0} найдено`}</span>
      </div>
      <section className="section">
        <div className="mini-object-list">
          {(data?.items ?? []).map((item) => (
            <button key={item.id} onClick={() => onObjectOpen(item.id)}>
              <span>{item.rcsme_reg_no || item.decree_no || `Объект ${item.id}`}</span>
              <em>{item.party_no ? `${item.party_no} · ` : ''}{item.last_stage || item.object_type || item.status || 'new'}</em>
            </button>
          ))}
          {q.trim().length < 2 && <div className="empty">Введите запрос</div>}
          {q.trim().length > 1 && !data?.items?.length && !isFetching && <div className="empty">Ничего не найдено</div>}
        </div>
      </section>
    </div>
  )
}
