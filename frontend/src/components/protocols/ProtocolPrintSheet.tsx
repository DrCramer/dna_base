import { useLayoutEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { paginateDilutionRowHeights } from './ProtocolDilutionPrintPages'
import { ProtocolPrintPageNumber } from './ProtocolPrintPageNumber'

interface Detail { label: string; value: string }
interface Props {
  sheetKey: string
  contentKey: string
  title: string
  name: string
  pageNumber: number
  totalPageCount: number
  details: Detail[]
  children: (continued: boolean) => ReactNode
  onPageCountChange: (key: string, count: number) => void
}

export function splitProtocolPrintText(text: string, maximum = 160): string[] {
  const parts: string[] = []
  let offset = 0
  while (offset < text.length) {
    const remaining = text.slice(offset, offset + maximum)
    const boundary = remaining.lastIndexOf(' ')
    const length = offset + maximum < text.length && boundary > maximum / 2 ? boundary + 1 : remaining.length
    parts.push(text.slice(offset, offset + length))
    offset += length
  }
  return parts
}

function Notes({ rows, title, name }: { rows: Detail[]; title: string; name: string }) {
  return <>
    <h1>{title} · продолжение</h1>
    <div className="protocol-print-notes-name">{name}</div>
    <table className="protocol-print-notes-table"><tbody>{rows.map((row, index) => <tr key={index}><th>{row.label}</th><td>{row.value}</td></tr>)}</tbody></table>
  </>
}

export function ProtocolPrintSheet({ sheetKey, contentKey, title, name, pageNumber, totalPageCount, details, children, onPageCountChange }: Props) {
  const main = useRef<HTMLElement>(null)
  const measure = useRef<HTMLElement>(null)
  const [overflow, setOverflow] = useState<{ key: string; continued: boolean } | null>(null)
  const continued = overflow?.key === contentKey && overflow.continued
  const detailKey = JSON.stringify(details)
  const rows = useMemo(() => details.flatMap((detail) => splitProtocolPrintText(detail.value).map((value, index) => ({ label: index ? '' : detail.label, value }))), [detailKey])
  const [pagination, setPagination] = useState<{ rows: Detail[]; ends: number[] } | null>(null)
  const ends = continued && pagination?.rows === rows ? pagination.ends : []
  useLayoutEffect(() => {
    const article = main.current
    const content = article?.querySelector<HTMLElement>('.protocol-print-sheet-content')
    if (!article || !content) return
    const style = getComputedStyle(article)
    const available = article.clientHeight - parseFloat(style.paddingTop) - parseFloat(style.paddingBottom) - 2
    setOverflow({ key: contentKey, continued: content.scrollHeight > available })
  }, [contentKey])
  useLayoutEffect(() => {
    const article = measure.current
    const elements = Array.from(article?.querySelectorAll<HTMLElement>('tbody tr') || [])
    if (!continued || !article || !elements.length) return
    const bottom = article.getBoundingClientRect().bottom - parseFloat(getComputedStyle(article).paddingBottom) - 3
    setPagination({ rows, ends: paginateDilutionRowHeights(elements.map((row) => row.getBoundingClientRect().height), bottom - elements[0].getBoundingClientRect().top) })
  }, [continued, rows])
  useLayoutEffect(() => onPageCountChange(sheetKey, 1 + ends.length), [sheetKey, ends.length, onPageCountChange])
  return <>
    <div className="protocol-print-page-shell protocol-plate-print-shell">
      <div className="protocol-print-page-label">Страница {pageNumber} · {title}</div>
      <article ref={main} className="protocol-print-page protocol-plate-print-page">
        <div className="protocol-print-sheet-content">{children(Boolean(continued))}</div>
        <ProtocolPrintPageNumber page={pageNumber} total={totalPageCount} />
      </article>
    </div>
    {continued && pagination?.rows !== rows ? <div className="protocol-print-measure" aria-hidden="true"><article ref={measure} className="protocol-print-page protocol-print-notes-page"><Notes rows={rows} title={title} name={name} /></article></div> : null}
    {ends.map((end, index) => <div className="protocol-print-page-shell protocol-print-notes-shell" key={index}>
      <div className="protocol-print-page-label">Страница {pageNumber + index + 1} · {title} · продолжение</div>
      <article className="protocol-print-page protocol-print-notes-page">
        <Notes rows={rows.slice(index ? ends[index - 1] : 0, end)} title={title} name={name} />
        <ProtocolPrintPageNumber page={pageNumber + index + 1} total={totalPageCount} />
      </article>
    </div>)}
  </>
}
