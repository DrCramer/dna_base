import { useMutation, useQuery } from '@tanstack/react-query'
import { Check, ChevronLeft, ChevronRight, ClipboardPaste, Search, X } from 'lucide-react'
import { useEffect, useMemo, useRef, useState } from 'react'
import { api } from '../../api/client'
import type { Party, ProtocolObject } from '../../api/types'
import { MultiPartyPicker } from '../ui'

interface Props {
  parties: Party[]
  year: number
  partyIds: number[]
  selectedIds: number[]
  onPartyIds: (ids: number[]) => void
  onSelectedIds: (ids: number[]) => void
  disabled?: boolean
}

const boundaryPattern = /^\d+(?:-\d+)?$/

function parseNumberList(value: string) {
  const result: string[] = []
  const seen = new Set<string>()
  value.split(/[\s,;]+/).forEach((item) => {
    const number = item.trim()
    const key = number.toLocaleLowerCase('ru')
    if (number && !seen.has(key)) {
      result.push(number)
      seen.add(key)
    }
  })
  return result
}

export function ProtocolObjectSelector({ parties, year, partyIds, selectedIds, onPartyIds, onSelectedIds, disabled }: Props) {
  const [query, setQuery] = useState('')
  const [description, setDescription] = useState('')
  const [rcsmeFrom, setRcsmeFrom] = useState('')
  const [rcsmeTo, setRcsmeTo] = useState('')
  const [debounced, setDebounced] = useState({ query: '', rcsmeFrom: '', rcsmeTo: '' })
  const [quick, setQuick] = useState('all')
  const [numberList, setNumberList] = useState<string[]>([])
  const [numberListDraft, setNumberListDraft] = useState('')
  const [numberListOpen, setNumberListOpen] = useState(false)
  const [offset, setOffset] = useState(0)
  const partyResolveSequence = useRef(0)

  useEffect(() => {
    const timer = window.setTimeout(() => setDebounced({ query, rcsmeFrom: rcsmeFrom.trim(), rcsmeTo: rcsmeTo.trim() }), 250)
    return () => window.clearTimeout(timer)
  }, [query, rcsmeFrom, rcsmeTo])

  const rangeError = Boolean(
    (debounced.rcsmeFrom && !boundaryPattern.test(debounced.rcsmeFrom))
    || (debounced.rcsmeTo && !boundaryPattern.test(debounced.rcsmeTo))
  )
  const numberListKey = numberList.join('\u0000')
  useEffect(() => setOffset(0), [partyIds, year, debounced, description, quick, numberListKey])

  const filterOptions = useQuery({
    queryKey: ['protocol-object-filter-options', partyIds, year],
    queryFn: () => api.protocolObjectFilterOptions(partyIds, year),
    staleTime: 30_000
  })
  useEffect(() => {
    if (description && filterOptions.data && !filterOptions.data.includes(description)) setDescription('')
  }, [description, filterOptions.data])

  const resolutionFilters = useMemo(() => ({
    partyIds,
    caseYear: year,
    selectedIds: quick === 'selected' ? selectedIds : undefined,
    q: debounced.query || undefined,
    description: description || undefined,
    rcsmeFrom: debounced.rcsmeFrom || undefined,
    rcsmeTo: debounced.rcsmeTo || undefined,
    numbers: numberList.length ? numberList : undefined,
    quick: quick === 'all' ? undefined : quick
  }), [partyIds, year, selectedIds, debounced, description, numberList, quick])
  const filters = useMemo(() => ({
    ...resolutionFilters,
    limit: 100,
    offset
  }), [resolutionFilters, offset])
  const hasScope = partyIds.length > 0 || numberList.length > 0
  const objects = useQuery({ queryKey: ['protocol-objects', filters], queryFn: () => api.protocolObjects(filters), enabled: hasScope && !rangeError, placeholderData: (previous) => previous })
  const allMatching = useQuery({
    queryKey: ['protocol-object-resolution', resolutionFilters],
    queryFn: () => api.resolveProtocolObjects(resolutionFilters),
    enabled: hasScope && !rangeError
  })
  const selectParties = useMutation({ mutationFn: (ids: number[]) => api.resolveProtocolObjects({ partyIds: ids, caseYear: year }) })
  const selected = useMemo(() => new Set(selectedIds), [selectedIds])
  const visible = objects.data?.items || []
  const matchingIds = allMatching.data?.object_ids || []
  const allMatchingSelected = matchingIds.length > 0 && matchingIds.every((id) => selected.has(id))
  const missingNumbers = allMatching.data?.missing_numbers || []
  const foundNumbers = numberList.length - missingNumbers.length

  function toggle(item: ProtocolObject) {
    const next = new Set(selected)
    if (next.has(item.id)) next.delete(item.id)
    else next.add(item.id)
    onSelectedIds(Array.from(next))
  }

  function toggleMatching() {
    const next = new Set(selected)
    matchingIds.forEach((id) => allMatchingSelected ? next.delete(id) : next.add(id))
    onSelectedIds(Array.from(next))
  }

  function changeParties(ids: number[]) {
    const sequence = ++partyResolveSequence.current
    onPartyIds(ids)
    if (!ids.length) {
      onSelectedIds([])
      return
    }
    selectParties.mutate(ids, {
      onSuccess: (result) => { if (sequence === partyResolveSequence.current) onSelectedIds(result.object_ids) },
      onError: () => { if (sequence === partyResolveSequence.current) onSelectedIds([]) }
    })
  }

  function openNumberList() {
    setNumberListDraft(numberList.join('\n'))
    setNumberListOpen(true)
  }

  function applyNumberList() {
    setNumberList(parseNumberList(numberListDraft))
    setRcsmeFrom('')
    setRcsmeTo('')
    setDebounced((current) => ({ ...current, rcsmeFrom: '', rcsmeTo: '' }))
    setNumberListOpen(false)
  }

  return (
    <div className="protocol-object-selector">
      <div className="protocol-selector-row protocol-selector-primary">
        <MultiPartyPicker parties={parties} selectedIds={partyIds} onChange={changeParties} disabled={disabled || selectParties.isPending} title="Партии протокола" />
        <div className="searchbox compact-search"><Search size={16} /><input value={query} disabled={disabled} onChange={(event) => setQuery(event.target.value)} placeholder="№ РЦСМЭ, постановления, в/ч" /></div>
      </div>
      <div className="protocol-selector-row protocol-selector-filters">
        {!numberList.length ? <><input className="compact-input" value={rcsmeFrom} disabled={disabled} onChange={(event) => setRcsmeFrom(event.target.value)} placeholder="№ рег РЦСМЭ от" />
        <input className="compact-input" value={rcsmeTo} disabled={disabled} onChange={(event) => setRcsmeTo(event.target.value)} placeholder="№ рег РЦСМЭ до" /></> : null}
        <select className="compact-input" aria-label="Описание" value={description} disabled={disabled || filterOptions.isLoading} onChange={(event) => setDescription(event.target.value)}>
          <option value="">Все описания</option>
          {(filterOptions.data || []).map((option) => <option value={option} key={option}>{option}</option>)}
        </select>
      </div>
      {rangeError ? <div className="protocol-filter-error">Диапазон РЦСМЭ: используйте формат 7600 или 7600-1.</div> : null}
      <div className="protocol-number-list-row">
        <button type="button" className="tiny-button" disabled={disabled} onClick={openNumberList}><ClipboardPaste size={14} />{numberList.length ? 'Изменить список номеров' : 'Вставить список номеров'}</button>
        {numberList.length ? <>
          <span>{allMatching.isError ? 'Не удалось проверить список' : allMatching.isFetching ? 'Проверяем список...' : `Найдено: ${foundNumbers} из ${numberList.length}`}</span>
          {missingNumbers.length ? <details><summary>Не найдено: {missingNumbers.length}</summary><div>{missingNumbers.join(', ')}</div></details> : null}
          <button type="button" className="tiny-button" disabled={disabled} onClick={() => setNumberList([])}><X size={14} />Очистить список</button>
        </> : null}
      </div>
      <div className="protocol-quick-filters">
        {[
          ['all', 'Все'], ['selected', 'Только выбранные'], ['has_rt', 'Есть концентрация RT'], ['no_rt', 'Нет концентрации RT'],
          ['dna_extraction', 'Есть Выделение'], ['realtime', 'Есть RealTime'], ['pcr', 'Есть PCR'], ['electrophoresis', 'Есть Форез']
        ].map(([key, label]) => <button type="button" key={key} className={quick === key ? 'active' : ''} onClick={() => setQuick(key)}>{label}</button>)}
      </div>
      <div className="protocol-selection-actions">
        <label><input type="checkbox" checked={allMatchingSelected} disabled={!matchingIds.length || allMatching.isFetching || disabled || rangeError} onChange={toggleMatching} /> Выбрать все</label>
        <button type="button" className="tiny-button" disabled={!selectedIds.length || disabled} onClick={() => onSelectedIds([])}><X size={14} />Очистить</button>
        <strong>Выбрано: {selectedIds.length}</strong>
      </div>
      {objects.isError || allMatching.isError || selectParties.isError ? <div className="alert danger">Не удалось загрузить или выбрать объекты.</div> : null}
      {!hasScope ? <div className="protocol-selector-empty">Выберите партии или вставьте список номеров.</div> : (
        <div className="protocol-object-table-wrap">
          <table className="protocol-object-table">
            <thead><tr><th /><th>№ рег РЦСМЭ</th><th>Партия</th><th>Описание</th><th>№ постановления</th><th>№ в/ч №522</th><th>Тип объекта</th><th>Коробка</th><th>RT</th></tr></thead>
            <tbody>
              {visible.map((item) => (
                <tr key={item.id} className={selected.has(item.id) ? 'is-selected' : ''} onClick={() => !disabled && toggle(item)}>
                  <td><input type="checkbox" checked={selected.has(item.id)} disabled={disabled} onChange={() => toggle(item)} onClick={(event) => event.stopPropagation()} /></td>
                  <td><strong>{item.rcsme_reg_no || '—'}</strong></td><td>{item.party_no || '—'}</td><td className="protocol-description-cell" title={item.object_description || ''}>{item.object_description || '—'}</td><td>{item.decree_no || '—'}</td><td>{item.external_military_no || '—'}</td><td>{item.object_type || '—'}</td><td>{item.box_no || '—'}</td><td>{item.has_rt ? 'есть' : '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {objects.isLoading ? <div className="protocol-selector-empty">Загрузка объектов...</div> : null}
          {!objects.isLoading && !visible.length && !rangeError ? <div className="protocol-selector-empty">Объекты не найдены.</div> : null}
        </div>
      )}
      {(objects.data?.total || 0) > 100 ? (
        <div className="protocol-pagination">
          <button type="button" className="icon-only" title="Предыдущая страница" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - 100))}><ChevronLeft size={17} /></button>
          <span>{offset + 1}–{Math.min(offset + 100, objects.data?.total || 0)} из {objects.data?.total}</span>
          <button type="button" className="icon-only" title="Следующая страница" disabled={offset + 100 >= (objects.data?.total || 0)} onClick={() => setOffset(offset + 100)}><ChevronRight size={17} /></button>
        </div>
      ) : null}
      {numberListOpen ? <div className="modal-backdrop" onMouseDown={() => setNumberListOpen(false)}><div className="modal protocol-number-list-modal" role="dialog" aria-modal="true" aria-label="Вставить список номеров" onMouseDown={(event) => event.stopPropagation()}>
        <h2>Вставить список номеров</h2>
        <p>Разделяйте номера переносом строки, пробелом, запятой или точкой с запятой.</p>
        <textarea rows={12} autoFocus value={numberListDraft} onChange={(event) => setNumberListDraft(event.target.value)} placeholder={'7600-1\n7601-1\n7602-1'} />
        <div className="modal-actions"><button type="button" className="icon-button" onClick={() => setNumberListOpen(false)}>Отмена</button><button type="button" className="primary compact" disabled={!parseNumberList(numberListDraft).length} onClick={applyNumberList}><Check size={16} />Применить</button></div>
      </div></div> : null}
    </div>
  )
}
