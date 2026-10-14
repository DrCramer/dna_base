import { useLayoutEffect, useMemo, useRef, useState } from 'react'
import { ProtocolDilutionsTable, type DilutionRow, type DilutionView } from './ProtocolSupplementTables'

export function paginateDilutionRowHeights(heights: number[], availableHeight: number): number[] {
  const ends: number[] = []
  let used = 0
  let start = 0
  heights.forEach((height, index) => {
    if (index > start && used + height > availableHeight) {
      ends.push(index)
      start = index
      used = 0
    }
    used += height
  })
  if (heights.length) ends.push(heights.length)
  return ends
}

interface Props {
  rows: DilutionRow[]
  protocolDate: string
  protocolNo: number
  name: string
  note: string | null
  view: DilutionView
  precedingPageCount: number
  onPageCountChange: (count: number) => void
}

function DilutionPage({ rows, protocolDate, protocolNo, name, note, view }: Omit<Props, 'precedingPageCount' | 'onPageCountChange'>) {
  return <article className="protocol-print-page protocol-print-data-page protocol-print-dilutions-page">
    <h1>Разведения · {name || 'Протокол'}</h1>
    <div className="protocol-print-meta"><div><span>Дата</span><strong>{protocolDate}</strong></div><div><span>№</span><strong>{protocolNo}</strong></div><div className="protocol-print-name"><span>Название</span><strong>{name || '—'}</strong></div><div><span>Строк</span><strong>{rows.length}</strong></div></div>
    {note ? <p className="protocol-print-optimization-note">{note}</p> : null}
    <ProtocolDilutionsTable rows={rows} view={{ ...view, hideNoDilution: false, sortKey: null }} print />
  </article>
}

export function ProtocolDilutionPrintPages(props: Props) {
  const { rows, precedingPageCount, onPageCountChange } = props
  const measure = useRef<HTMLDivElement>(null)
  const input = useMemo(() => ({ rows, protocolDate: props.protocolDate, protocolNo: props.protocolNo, name: props.name, note: props.note, view: props.view }), [rows, props.protocolDate, props.protocolNo, props.name, props.note, props.view])
  const [layout, setLayout] = useState<{ input: typeof input; ends: number[] } | null>(null)
  const ends = layout?.input === input ? layout.ends : []
  useLayoutEffect(() => {
    const article = measure.current?.querySelector<HTMLElement>('article')
    const tableRows = Array.from(article?.querySelectorAll<HTMLElement>('tbody tr') || [])
    if (!article || !tableRows.length) {
      setLayout({ input, ends: [] })
      onPageCountChange(0)
      return
    }
    const style = getComputedStyle(article)
    // Измеряем при ширине печати, оставляя запас на округление размеров браузером.
    const bottom = article.getBoundingClientRect().bottom - parseFloat(style.paddingBottom) - parseFloat(style.borderBottomWidth) - 2
    const heights = tableRows.map((row) => row.getBoundingClientRect().height)
    const pageEnds = paginateDilutionRowHeights(heights, bottom - tableRows[0].getBoundingClientRect().top)
    setLayout({ input, ends: pageEnds })
    onPageCountChange(pageEnds.length)
  }, [input, onPageCountChange])
  return <>
    {rows.length && layout?.input !== input ? <div className="protocol-print-measure" ref={measure} aria-hidden="true"><DilutionPage {...input} /></div> : null}
    {ends.map((end, index) => <div className="protocol-print-page-shell protocol-print-dilutions-shell" key={index}>
      <div className="protocol-print-page-label">Страница {precedingPageCount + index + 1} · Разведения · лист {index + 1}</div>
      <DilutionPage {...input} rows={rows.slice(index ? ends[index - 1] : 0, end)} />
    </div>)}
  </>
}
