import { useMutation, useQuery } from '@tanstack/react-query'
import { Download, FileSpreadsheet, Search, X } from 'lucide-react'
import { useRef, useState, type FormEvent } from 'react'
import { api } from '../api/client'

const pageSize = 50
const headers = ['№ партии', '№ рег РЦСМЭ', '№ в в/ч №522']

export function RcsmeLookup() {
  const [yearOverride, setYear] = useState<string>()
  const [numbers, setNumbers] = useState('')
  const [file, setFile] = useState<File | null>(null)
  const [page, setPage] = useState(0)
  const fileInput = useRef<HTMLInputElement>(null)
  const years = useQuery({ queryKey: ['party-years'], queryFn: api.partyYears })
  const year = yearOverride ?? String(years.data?.default_year ?? '')
  const options = Array.from(new Set([...(years.data?.years ?? []), ...(year ? [Number(year)] : [])]))
  const preview = useMutation({ mutationFn: api.previewRcsmeLookup })
  const download = useMutation({
    mutationFn: api.downloadRcsmeLookup,
    onSuccess: (blob) => {
      const url = URL.createObjectURL(blob)
      const link = document.createElement('a')
      link.href = url
      link.download = 'Сопоставление номеров РЦСМЭ.xlsx'
      link.click()
      window.setTimeout(() => URL.revokeObjectURL(url), 1000)
    }
  })
  const busy = preview.isPending || download.isPending
  const result = preview.data
  const error = preview.error || download.error

  function clearResult() {
    preview.reset()
    download.reset()
    setPage(0)
  }

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (busy || years.isPending || (!file && !numbers.trim())) return
    const data = new FormData()
    if (year) data.set('case_year', year)
    if (file) data.set('file', file)
    else data.set('numbers', numbers)
    clearResult()
    preview.mutate(data)
  }

  return (
    <>
      <form className="rcsme-lookup-form" onSubmit={submit}>
        <div className="rcsme-lookup-controls">
          <label>Год регистрации
            <select value={year} disabled={busy || years.isPending} onChange={(event) => { setYear(event.target.value); clearResult() }}>
              <option value="">Все годы</option>
              {options.map((item) => <option key={item} value={item}>{item}</option>)}
            </select>
          </label>
          <input type="file" accept=".xlsx,.csv,.txt" aria-label="Файл с номерами РЦСМЭ" ref={fileInput} hidden disabled={busy} onChange={(event) => {
            const next = event.target.files?.[0]
            if (next) { setFile(next); setNumbers(''); clearResult() }
            event.target.value = ''
          }} />
          <button className="icon-button" type="button" disabled={busy} onClick={() => fileInput.current?.click()}><FileSpreadsheet size={17} />Загрузить список</button>
          <span className="muted-note">XLSX, CSV, TXT</span>
        </div>
        {file ? <div className="rcsme-lookup-file">
          <span>{file.name}</span>
          <button type="button" className="icon-button rcsme-icon-only" disabled={busy} aria-label="Убрать файл" title="Убрать файл" onClick={() => { setFile(null); clearResult() }}><X size={16} /></button>
        </div> : <label className="rcsme-lookup-numbers">Номера РЦСМЭ
          <textarea rows={5} value={numbers} disabled={busy} onChange={(event) => { setNumbers(event.target.value); clearResult() }} />
        </label>}
        {years.isError && !year ? <div className="alert warning">Не удалось загрузить список годов. Поиск будет выполнен по всем годам.</div> : null}
        <div className="rcsme-lookup-controls">
          <button className="primary compact" type="submit" disabled={busy || years.isPending || (!file && !numbers.trim())}><Search size={17} />{preview.isPending ? 'Поиск…' : 'Найти номера'}</button>
        </div>
        {error ? <div className="alert danger" role="alert">{error.message}</div> : null}
      </form>
      {result ? <section className="rcsme-lookup-results" aria-label="Результаты сопоставления">
        <div className="rcsme-lookup-result-bar">
          <div role="status" className="rcsme-lookup-counts">
            <strong>Найдено: {result.rows.length}</strong>
            <span>Не найдено: {result.missing.length}</span>
            <span>Неоднозначных: {result.ambiguous.length}</span>
            {result.duplicates ? <span>Повторов в списке: {result.duplicates}</span> : null}
          </div>
          <button className="icon-button" type="button" disabled={!result.rows.length || busy} onClick={() => download.mutate(result.rows)}>
            <Download size={17} />{download.isPending ? 'Подготовка…' : 'Скачать Excel'}
          </button>
        </div>
        {result.missing.length || result.ambiguous.length ? <div className="rcsme-lookup-issues">
          <span className="muted-note">В Excel попадут только однозначные совпадения.</span>
          {result.missing.length ? <details><summary>Ненайденные номера ({result.missing.length})</summary><div>{result.missing.join(', ')}</div></details> : null}
          {result.ambiguous.length ? <details><summary>Неоднозначные номера ({result.ambiguous.length})</summary><div>{result.ambiguous.join(', ')}</div></details> : null}
        </div> : null}
        {result.rows.length ? <div className="rcsme-lookup-table" tabIndex={0}>
          <table><thead><tr>{headers.map((header) => <th key={header} scope="col">{header}</th>)}</tr></thead>
            <tbody>{result.rows.slice(page * pageSize, (page + 1) * pageSize).map((row) => <tr key={row.rcsme_reg_no}>
              <td>{row.party_no || '—'}</td><td>{row.rcsme_reg_no}</td><td>{row.external_military_no || '—'}</td>
            </tr>)}</tbody>
          </table>
        </div> : <p className="muted-note">Нет однозначных совпадений.</p>}
        {result.rows.length > pageSize ? <div className="protocol-pagination">
          <button className="icon-button" type="button" disabled={!page} onClick={() => setPage(page - 1)}>Назад</button>
          <span>{page * pageSize + 1}–{Math.min((page + 1) * pageSize, result.rows.length)} из {result.rows.length}</span>
          <button className="icon-button" type="button" disabled={(page + 1) * pageSize >= result.rows.length} onClick={() => setPage(page + 1)}>Далее</button>
        </div> : null}
      </section> : null}
    </>
  )
}
