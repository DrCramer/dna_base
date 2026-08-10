import { Check, Search, UploadCloud, X } from 'lucide-react'
import { useMemo, useState } from 'react'
import type { ChangeEvent, DragEvent, ReactNode } from 'react'
import type { Party } from '../api/types'

export function PageHeader({
  title,
  description,
  actions
}: {
  title: string
  description?: ReactNode
  actions?: ReactNode
}) {
  return (
    <header className="page-header page-header-unified">
      <div className="page-header-copy">
        <h1>{title}</h1>
        {description ? <p>{description}</p> : null}
      </div>
      {actions ? <div className="page-header-actions">{actions}</div> : null}
    </header>
  )
}

export function EmptyState({
  icon,
  title,
  children,
  actions
}: {
  icon?: ReactNode
  title: string
  children?: ReactNode
  actions?: ReactNode
}) {
  return (
    <div className="empty-state">
      {icon ? <div className="empty-state-icon">{icon}</div> : null}
      <strong>{title}</strong>
      {children ? <p>{children}</p> : null}
      {actions ? <div className="empty-state-actions">{actions}</div> : null}
    </div>
  )
}

export function LoadingState({ title = 'Загрузка данных...', rows = 5 }: { title?: string; rows?: number }) {
  return (
    <div className="loading-state" aria-live="polite">
      <span>{title}</span>
      <div className="skeleton-table" aria-hidden="true">
        {Array.from({ length: rows }, (_, index) => <i key={index} />)}
      </div>
    </div>
  )
}

export function ErrorState({
  title = 'Не удалось загрузить данные',
  error,
  onRetry
}: {
  title?: string
  error?: unknown
  onRetry?: () => void
}) {
  const message = error instanceof Error ? error.message : error ? String(error) : ''
  return (
    <div className="error-state">
      <strong>{title}</strong>
      <span>Попробуйте повторить запрос. Технические детали можно раскрыть ниже.</span>
      {message ? <details><summary>Подробнее</summary><pre>{message}</pre></details> : null}
      {onRetry ? <button type="button" className="icon-button" onClick={onRetry}>Повторить</button> : null}
    </div>
  )
}

export function StatusBadge({
  tone = 'muted',
  children
}: {
  tone?: 'muted' | 'info' | 'warning' | 'success' | 'danger'
  children: ReactNode
}) {
  return <span className={`status-badge ${tone}`}>{children}</span>
}

export function ProgressCell({ done, total }: { done: number; total: number }) {
  const percent = total > 0 ? Math.min(100, Math.round((done / total) * 100)) : 0
  const tone = percent >= 100 ? 'success' : percent > 0 ? 'warning' : 'muted'
  return (
    <span className={`progress-cell ${tone}`} role="progressbar" aria-valuemin={0} aria-valuemax={100} aria-valuenow={percent}>
      <span className="progress-cell-track" aria-hidden="true"><i style={{ width: `${percent}%` }} /></span>
      <span>{done} / {total}</span>
    </span>
  )
}

export function BulkActionBar({
  count,
  children
}: {
  count: number
  children: ReactNode
}) {
  if (!count) return null
  return (
    <div className="bulk-action-bar" role="region" aria-label={`Действия с выбранными строками: ${count}`}>
      <strong>Выбрано: {count}</strong>
      <div>{children}</div>
    </div>
  )
}

export function FileDropzone({
  title = 'Перетащите файлы сюда',
  description = 'или нажмите для выбора',
  formats,
  multiple = false,
  maxFiles,
  disabled = false,
  accept,
  className = '',
  onFiles
}: {
  title?: string
  description?: string
  formats?: string
  multiple?: boolean
  maxFiles?: number
  disabled?: boolean
  accept?: string
  className?: string
  onFiles: (files: File[]) => void
}) {
  const [dragging, setDragging] = useState(false)
  function deliver(files: File[]) {
    const limited = maxFiles ? files.slice(0, maxFiles) : files
    if (limited.length) onFiles(limited)
  }
  function change(event: ChangeEvent<HTMLInputElement>) {
    const files = Array.from(event.currentTarget.files || [])
    deliver(files)
    event.currentTarget.value = ''
  }
  function drop(event: DragEvent<HTMLLabelElement>) {
    event.preventDefault()
    setDragging(false)
    if (!disabled) deliver(Array.from(event.dataTransfer.files || []))
  }
  return (
    <label
      className={`file-drop file-dropzone${disabled ? ' is-disabled' : ''}${dragging ? ' is-dragging' : ''}${className ? ` ${className}` : ''}`}
      onDragEnter={(event) => { event.preventDefault(); if (!disabled) setDragging(true) }}
      onDragOver={(event) => event.preventDefault()}
      onDragLeave={() => setDragging(false)}
      onDrop={drop}
    >
      <UploadCloud size={24} />
      <strong>{title}</strong>
      <span>{description}</span>
      {formats ? <small>{formats}</small> : null}
      <input type="file" accept={accept} multiple={multiple} disabled={disabled} onChange={change} />
    </label>
  )
}

export function MultiPartyPicker({
  parties,
  selectedIds,
  onChange,
  disabled = false,
  title = 'Выбрать партии',
  triggerLabel
}: {
  parties: Party[]
  selectedIds: number[]
  onChange: (ids: number[]) => void
  disabled?: boolean
  title?: string
  triggerLabel?: string
}) {
  const [open, setOpen] = useState(false)
  const [search, setSearch] = useState('')
  const selected = useMemo(() => new Set(selectedIds), [selectedIds])
  const visible = useMemo(() => {
    const needle = search.trim().toLowerCase()
    if (!needle) return parties
    return parties.filter((party) => `${party.party_no} ${party.case_year || ''} ${party.object_count}`.toLowerCase().includes(needle))
  }, [parties, search])
  const selectedObjects = parties.reduce((total, party) => total + (selected.has(party.id) ? party.object_count : 0), 0)
  const label = triggerLabel || (selectedIds.length ? `${selectedIds.length} партий · ${selectedObjects} объектов` : 'Выбрать партии')
  function toggle(id: number) {
    const next = new Set(selected)
    if (next.has(id)) next.delete(id)
    else next.add(id)
    onChange(Array.from(next))
  }
  return (
    <>
      <button type="button" className="cell-picker-button multi-party-trigger" aria-label={title} disabled={disabled} onClick={() => setOpen(true)}>
        <span>{label}</span>
      </button>
      {open ? (
        <div className="modal-backdrop" role="presentation" onMouseDown={() => setOpen(false)}>
          <div className="modal compact-modal multi-party-modal" role="dialog" aria-modal="true" aria-label={title} onMouseDown={(event) => event.stopPropagation()}>
            <h2>{title}</h2>
            <div className="searchbox compact-search"><Search size={16} /><input autoFocus value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Поиск партии" /></div>
            <div className="picker-toolbar">
              <button type="button" className="tiny-button" onClick={() => onChange(Array.from(new Set([...selectedIds, ...visible.map((party) => party.id)])))}>Выбрать видимые</button>
              <button type="button" className="tiny-button" onClick={() => onChange([])}><X size={14} />Очистить</button>
            </div>
            <div className="check-list compact-check-list">
              {visible.map((party) => (
                <label key={party.id}>
                  <input type="checkbox" checked={selected.has(party.id)} onChange={() => toggle(party.id)} />
                  <span>Партия {party.party_no}</span>
                  <em>{party.object_count} объектов</em>
                </label>
              ))}
              {!visible.length ? <div className="compact-empty">Партии не найдены</div> : null}
            </div>
            <div className="picker-summary">Выбрано: <strong>{selectedIds.length}</strong> · {selectedObjects} объектов</div>
            <div className="modal-actions">
              <button type="button" className="icon-button" onClick={() => setOpen(false)}>Отмена</button>
              <button type="button" className="primary compact" onClick={() => setOpen(false)}><Check size={18} />Готово</button>
            </div>
          </div>
        </div>
      ) : null}
    </>
  )
}
