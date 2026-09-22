import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Archive, Copy, Eye, Plus, Printer, Search } from 'lucide-react'
import { useState } from 'react'
import { api } from '../api/client'
import type { ProtocolStatus, User } from '../api/types'
import { EmptyState, ErrorState, LoadingState, PageHeader, StatusBadge } from '../components/ui'

const statusLabels: Record<ProtocolStatus, string> = { draft: 'Черновик', final: 'Сохранён', archived: 'Архив' }

export function ProtocolsPage({ user, onCreate, onOpen, onPrint }: { user: User; onCreate: () => void; onOpen: (id: number) => void; onPrint: (id: number) => void }) {
  const queryClient = useQueryClient()
  const [q, setQ] = useState('')
  const [status, setStatus] = useState('')
  const [stageType, setStageType] = useState('')
  const [year, setYear] = useState(new Date().getFullYear())
  const [partyId, setPartyId] = useState('')
  const [employeeId, setEmployeeId] = useState('')
  const [dateFrom, setDateFrom] = useState('')
  const [dateTo, setDateTo] = useState('')
  const [period, setPeriod] = useState('')
  const [offset, setOffset] = useState(0)
  const today = new Date().toISOString().slice(0, 10)
  const weekStartDate = new Date()
  weekStartDate.setDate(weekStartDate.getDate() - ((weekStartDate.getDay() + 6) % 7))
  const weekStart = weekStartDate.toISOString().slice(0, 10)
  const resolvedDateFrom = period === 'today' ? today : period === 'week' ? weekStart : dateFrom || undefined
  const resolvedDateTo = period ? today : dateTo || undefined
  const parties = useQuery({ queryKey: ['parties', 'protocol-filters', year], queryFn: () => api.parties('', true, year), staleTime: 30_000 })
  const employees = useQuery({ queryKey: ['employees', 'protocol-filters'], queryFn: () => api.employees('', undefined, undefined, undefined, true), staleTime: 30_000 })
  const protocols = useQuery({ queryKey: ['protocols', q, status, stageType, year, partyId, employeeId, resolvedDateFrom, resolvedDateTo, offset], queryFn: () => api.protocols({ q, status: status || undefined, stage_type: stageType || undefined, year, party_id: partyId || undefined, employee_id: employeeId || undefined, date_from: resolvedDateFrom, date_to: resolvedDateTo, limit: 50, offset }) })
  const duplicate = useMutation({ mutationFn: ({ id, copyObjects }: { id: number; copyObjects: boolean }) => api.duplicateProtocol(id, copyObjects), onSuccess: (item) => { queryClient.invalidateQueries({ queryKey: ['protocols'] }); onOpen(item.id) } })
  const archive = useMutation({ mutationFn: api.archiveProtocol, onSuccess: () => queryClient.invalidateQueries({ queryKey: ['protocols'] }) })
  return (
    <div className="page protocols-list-page">
      <PageHeader title="Сохранённые протоколы" description="Черновики, сохранённые версии и архив лабораторных протоколов." actions={user.role !== 'viewer' ? <button type="button" className="primary compact" onClick={onCreate}><Plus size={18} />Создать</button> : null} />
      <div className="protocol-list-filters">
        <div className="searchbox"><Search size={17} /><input value={q} onChange={(event) => { setQ(event.target.value); setOffset(0) }} placeholder="№, название, партия, объект, набор..." /></div>
        <select value={year} onChange={(event) => { setYear(Number(event.target.value)); setPartyId(''); setOffset(0) }}>{Array.from({ length: 6 }, (_, index) => new Date().getFullYear() - index).map((item) => <option key={item}>{item}</option>)}</select>
        <select value={status} onChange={(event) => { setStatus(event.target.value); setOffset(0) }}><option value="">Все актуальные</option><option value="draft">Черновики</option><option value="final">Сохранённые</option><option value="archived">Архив</option></select>
        <select value={stageType} onChange={(event) => { setStageType(event.target.value); setOffset(0) }}><option value="">Все этапы</option><option value="dna_extraction">Выделение</option><option value="realtime">RealTime</option><option value="pcr">ПЦР</option><option value="electrophoresis">Форез</option></select>
      </div>
      <div className="protocol-list-quick"><button type="button" className={!status && !period ? 'active' : ''} onClick={() => { setStatus(''); setPeriod(''); setOffset(0) }}>Все</button><button type="button" className={status === 'draft' ? 'active' : ''} onClick={() => { setStatus('draft'); setPeriod(''); setOffset(0) }}>Черновики</button><button type="button" className={status === 'final' ? 'active' : ''} onClick={() => { setStatus('final'); setPeriod(''); setOffset(0) }}>Сохранённые</button><button type="button" className={status === 'archived' ? 'active' : ''} onClick={() => { setStatus('archived'); setPeriod(''); setOffset(0) }}>Архив</button><button type="button" className={period === 'today' ? 'active' : ''} onClick={() => { setPeriod('today'); setOffset(0) }}>Сегодня</button><button type="button" className={period === 'week' ? 'active' : ''} onClick={() => { setPeriod('week'); setOffset(0) }}>Эта неделя</button></div>
      <details className="protocol-list-advanced"><summary>Дополнительные фильтры</summary><div><label>Дата с<input type="date" value={dateFrom} disabled={Boolean(period)} onChange={(event) => { setDateFrom(event.target.value); setOffset(0) }} /></label><label>Дата по<input type="date" value={dateTo} disabled={Boolean(period)} onChange={(event) => { setDateTo(event.target.value); setOffset(0) }} /></label><label>Партия<select value={partyId} onChange={(event) => { setPartyId(event.target.value); setOffset(0) }}><option value="">Все</option>{(parties.data?.items || []).map((item) => <option value={item.id} key={item.id}>{item.party_no}</option>)}</select></label><label>Исполнитель<select value={employeeId} onChange={(event) => { setEmployeeId(event.target.value); setOffset(0) }}><option value="">Все</option>{(employees.data || []).map((item) => <option value={item.id} key={item.id}>{item.short_name || item.full_name}</option>)}</select></label></div></details>
      {protocols.isLoading ? <LoadingState title="Загрузка протоколов..." rows={7} /> : null}
      {protocols.isError ? <ErrorState error={protocols.error} onRetry={() => protocols.refetch()} /> : null}
      {!protocols.isLoading && protocols.data?.items.length ? <div className="protocol-list-table-wrap"><table className="protocol-list-table"><thead><tr><th>Дата</th><th>№</th><th>Название</th><th>Партии</th><th>Объектов</th><th>Этапы</th><th>Автор</th><th>Изменён</th><th>Статус</th><th /></tr></thead><tbody>{protocols.data.items.map((item) => <tr key={item.id}><td>{new Date(`${item.protocol_date}T00:00:00`).toLocaleDateString('ru-RU')}</td><td>{item.protocol_no}</td><td><button type="button" className="link-button" onClick={() => onOpen(item.id)}>{item.name}</button><small>версия {item.revision_no}</small></td><td>{item.party_numbers.join(', ') || '—'}</td><td>{item.object_count}</td><td>{item.stage_types.length}</td><td>{item.author || '—'}</td><td>{new Date(item.updated_at).toLocaleString('ru-RU')}</td><td><StatusBadge tone={item.status === 'final' ? 'success' : item.status === 'archived' ? 'muted' : 'warning'}>{statusLabels[item.status]}</StatusBadge></td><td><div className="protocol-row-actions"><button type="button" className="icon-only" title="Открыть" onClick={() => onOpen(item.id)}><Eye size={16} /></button><button type="button" className="icon-only" title="Предпросмотр печати" onClick={() => onPrint(item.id)}><Printer size={16} /></button>{user.role !== 'viewer' ? <><button type="button" className="icon-only" title="Дублировать настройки" onClick={() => duplicate.mutate({ id: item.id, copyObjects: false })}><Copy size={16} /></button><button type="button" className="icon-only" title="Дублировать вместе с объектами" onClick={() => duplicate.mutate({ id: item.id, copyObjects: true })}><Copy size={16} /><span>+</span></button></> : null}{user.role === 'admin' && item.status !== 'archived' ? <button type="button" className="icon-only danger" title="Архивировать" onClick={() => window.confirm(`Архивировать ${item.name}?`) && archive.mutate(item.id)}><Archive size={16} /></button> : null}</div></td></tr>)}</tbody></table></div> : null}
      {!protocols.isLoading && !protocols.data?.items.length ? <EmptyState title="Протоколы не найдены">Измените фильтры или создайте первый протокол.</EmptyState> : null}
      {(protocols.data?.total || 0) > 50 ? <div className="protocol-pagination"><button type="button" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - 50))}>Назад</button><span>{offset + 1}–{Math.min(offset + 50, protocols.data?.total || 0)} из {protocols.data?.total}</span><button type="button" disabled={offset + 50 >= (protocols.data?.total || 0)} onClick={() => setOffset(offset + 50)}>Далее</button></div> : null}
    </div>
  )
}
