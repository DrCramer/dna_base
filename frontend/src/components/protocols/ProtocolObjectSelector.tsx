import { useMutation, useQuery } from '@tanstack/react-query'
import { Check, ChevronLeft, ChevronRight, Search, X } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { api } from '../../api/client'
import type { Party, ProtocolObject } from '../../api/types'
import { MultiPartyPicker } from '../ui'

interface Props {
  parties: Party[]
  partyIds: number[]
  selectedIds: number[]
  onPartyIds: (ids: number[]) => void
  onSelectedIds: (ids: number[]) => void
  disabled?: boolean
}

export function ProtocolObjectSelector({ parties, partyIds, selectedIds, onPartyIds, onSelectedIds, disabled }: Props) {
  const [query, setQuery] = useState('')
  const [debouncedQuery, setDebouncedQuery] = useState('')
  const [objectType, setObjectType] = useState('')
  const [boxNo, setBoxNo] = useState('')
  const [quick, setQuick] = useState('all')
  const [offset, setOffset] = useState(0)
  useEffect(() => {
    const timer = window.setTimeout(() => setDebouncedQuery(query), 250)
    return () => window.clearTimeout(timer)
  }, [query])
  useEffect(() => setOffset(0), [partyIds, debouncedQuery, objectType, boxNo, quick])
  const filters = useMemo(() => ({ partyIds, selectedIds: quick === 'selected' ? selectedIds : undefined, q: debouncedQuery, objectType: objectType || undefined, boxNo: boxNo || undefined, quick: quick === 'all' ? undefined : quick, limit: 100, offset }), [partyIds, selectedIds, debouncedQuery, objectType, boxNo, quick, offset])
  const objects = useQuery({ queryKey: ['protocol-objects', filters], queryFn: () => api.protocolObjects(filters), enabled: partyIds.length > 0, placeholderData: (previous) => previous })
  const resolve = useMutation({ mutationFn: () => api.resolveProtocolObjects(filters), onSuccess: (result) => onSelectedIds(result.object_ids) })
  const selected = useMemo(() => new Set(selectedIds), [selectedIds])
  const visible = objects.data?.items || []
  const allVisible = visible.length > 0 && visible.every((item) => selected.has(item.id))
  function toggle(item: ProtocolObject) {
    const next = new Set(selected)
    if (next.has(item.id)) next.delete(item.id)
    else next.add(item.id)
    onSelectedIds(Array.from(next))
  }
  function toggleVisible() {
    const next = new Set(selected)
    visible.forEach((item) => allVisible ? next.delete(item.id) : next.add(item.id))
    onSelectedIds(Array.from(next))
  }
  return (
    <div className="protocol-object-selector">
      <div className="protocol-selector-row">
        <MultiPartyPicker parties={parties} selectedIds={partyIds} onChange={onPartyIds} disabled={disabled} title="Партии протокола" />
        <div className="searchbox compact-search"><Search size={16} /><input value={query} disabled={disabled} onChange={(event) => setQuery(event.target.value)} placeholder="№ РЦСМЭ, постановления, в/ч" /></div>
        <input className="compact-input" value={objectType} disabled={disabled} onChange={(event) => setObjectType(event.target.value)} placeholder="Тип объекта" />
        <input className="compact-input" value={boxNo} disabled={disabled} onChange={(event) => setBoxNo(event.target.value)} placeholder="Коробка" />
      </div>
      <div className="protocol-quick-filters">
        {[
          ['all', 'Все'], ['selected', 'Только выбранные'], ['has_rt', 'Есть концентрация RT'], ['no_rt', 'Нет концентрации RT'],
          ['dna_extraction', 'Есть Выделение'], ['realtime', 'Есть RealTime'], ['pcr', 'Есть PCR'], ['electrophoresis', 'Есть Форез']
        ].map(([key, label]) => <button type="button" key={key} className={quick === key ? 'active' : ''} onClick={() => setQuick(key)}>{label}</button>)}
      </div>
      <div className="protocol-selection-actions">
        <label><input type="checkbox" checked={allVisible} disabled={!visible.length || disabled} onChange={toggleVisible} /> Выбрать видимые</label>
        <button type="button" className="tiny-button" disabled={!partyIds.length || resolve.isPending || disabled} onClick={() => resolve.mutate()}><Check size={14} />Выбрать все по текущему фильтру</button>
        <button type="button" className="tiny-button" disabled={!selectedIds.length || disabled} onClick={() => onSelectedIds([])}><X size={14} />Очистить</button>
        <strong>Выбрано: {selectedIds.length}</strong>
      </div>
      {!partyIds.length ? <div className="protocol-selector-empty">Сначала выберите одну или несколько партий.</div> : (
        <div className="protocol-object-table-wrap">
          <table className="protocol-object-table">
            <thead><tr><th /><th>№ рег РЦСМЭ</th><th>Партия</th><th>№ постановления</th><th>№ в/ч №522</th><th>Тип объекта</th><th>Коробка</th><th>RT</th></tr></thead>
            <tbody>
              {visible.map((item) => (
                <tr key={item.id} className={selected.has(item.id) ? 'is-selected' : ''} onClick={() => !disabled && toggle(item)}>
                  <td><input type="checkbox" checked={selected.has(item.id)} disabled={disabled} onChange={() => toggle(item)} onClick={(event) => event.stopPropagation()} /></td>
                  <td><strong>{item.rcsme_reg_no || '—'}</strong></td><td>{item.party_no || '—'}</td><td>{item.decree_no || '—'}</td><td>{item.external_military_no || '—'}</td><td>{item.object_type || '—'}</td><td>{item.box_no || '—'}</td><td>{item.has_rt ? 'есть' : '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {objects.isLoading ? <div className="protocol-selector-empty">Загрузка объектов...</div> : null}
          {!objects.isLoading && !visible.length ? <div className="protocol-selector-empty">Объекты не найдены.</div> : null}
        </div>
      )}
      {(objects.data?.total || 0) > 100 ? (
        <div className="protocol-pagination">
          <button type="button" className="icon-only" title="Предыдущая страница" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - 100))}><ChevronLeft size={17} /></button>
          <span>{offset + 1}–{Math.min(offset + 100, objects.data?.total || 0)} из {objects.data?.total}</span>
          <button type="button" className="icon-only" title="Следующая страница" disabled={offset + 100 >= (objects.data?.total || 0)} onClick={() => setOffset(offset + 100)}><ChevronRight size={17} /></button>
        </div>
      ) : null}
    </div>
  )
}
