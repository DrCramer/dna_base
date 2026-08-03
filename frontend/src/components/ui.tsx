import type { ReactNode } from 'react'

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
