import { useQuery } from '@tanstack/react-query'
import { Download, ExternalLink, FileText, RefreshCw } from 'lucide-react'
import { ErrorState, PageHeader } from '../components/ui'

type PrintJob = {
  id?: string
  status?: string
  created_at?: string
  updated_at?: string
  total?: number
  pdfs?: unknown[]
  result_pdf?: string | null
  result_zip?: string | null
  build?: {
    done?: number
    total?: number
    percent?: number
    message?: string
  }
}

function printStatusLabel(status?: string) {
  if (status === 'ready') return 'Готово'
  if (status === 'converting') return 'Собирается'
  if (status === 'created') return 'Загружено'
  if (status === 'error') return 'Ошибка'
  return 'Нет активной задачи'
}

function formatPrintDate(value?: string) {
  if (!value) return '—'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return '—'
  return date.toLocaleString('ru-RU', { dateStyle: 'short', timeStyle: 'short' })
}

async function fetchRecentPrintJob(): Promise<PrintJob> {
  const response = await fetch('/api/print/jobs/recent', { credentials: 'include' })
  if (!response.ok) throw new Error(`Не удалось получить последнюю задачу печати (${response.status})`)
  return response.json()
}

export function PrintPage() {
  const recentJob = useQuery({
    queryKey: ['print', 'recent-job'],
    queryFn: fetchRecentPrintJob,
    staleTime: 15_000,
    refetchInterval: (query) => query.state.data?.status === 'converting' ? 3000 : false
  })
  const job = recentJob.data || {}
  const hasReadyResult = Boolean(job.id && job.status === 'ready')

  return (
    <div className="page print-page" aria-label="Печать DOCX">
      <PageHeader
        title="Печать DOCX"
        description="Соберите лабораторный реестр, проверьте порядок документов и скачайте готовый PDF или архив."
        actions={(
          <>
            <button className="icon-button" type="button" onClick={() => recentJob.refetch()}>
              <RefreshCw size={18} />
              Обновить
            </button>
            <a className="primary download" href="/print?embedded=1&v=20260809-registration-preview-v2" target="_blank" rel="noreferrer">
              <ExternalLink size={18} />
              Открыть отдельно
            </a>
          </>
        )}
      />
      {recentJob.isError ? (
        <ErrorState error={recentJob.error} onRetry={() => void recentJob.refetch()} />
      ) : (
        <section className="print-status-panel" aria-label="Последняя задача печати">
          <div>
            <span>Последняя задача</span>
            <strong>{printStatusLabel(job.status)}</strong>
          </div>
          <div>
            <span>Документы</span>
            <strong>{job.build?.total ?? job.total ?? job.pdfs?.length ?? '—'}</strong>
          </div>
          <div>
            <span>Прогресс</span>
            <strong>{job.build?.percent != null ? `${job.build.percent}%` : job.status === 'ready' ? '100%' : '—'}</strong>
          </div>
          <div>
            <span>Обновлено</span>
            <strong>{formatPrintDate(job.updated_at || job.created_at)}</strong>
          </div>
          <div className="print-status-actions">
            {hasReadyResult ? (
              <>
                {job.result_pdf ? (
                  <a className="icon-button" href={`/api/print/jobs/${job.id}/download/pdf`}>
                    <Download size={16} />
                    PDF
                  </a>
                ) : null}
                {job.result_zip ? (
                  <a className="icon-button" href={`/api/print/jobs/${job.id}/download/zip`}>
                    <Download size={16} />
                    ZIP
                  </a>
                ) : null}
                <a className="icon-button" href={`/api/print/jobs/${job.id}/download/report.csv`}>
                  <FileText size={16} />
                  CSV
                </a>
              </>
            ) : (
              <span>{job.build?.message || 'Результат появится после сборки внутри формы.'}</span>
            )}
          </div>
        </section>
      )}
      <div className="print-frame-wrap">
        <iframe
          title="Печать DOCX"
          src="/print?embedded=1&v=20260809-registration-preview-v2"
          className="print-frame"
        />
      </div>
    </div>
  )
}
