import { FileDown } from 'lucide-react'
import { useState } from 'react'
import { api } from '../api/client'

export function ExportPage() {
  const [q, setQ] = useState('')
  return (
    <div className="page">
      <header className="page-header"><h1>Экспорт</h1></header>
      <section className="section export-box">
        <label>Фильтр поиска<input value={q} onChange={(event) => setQ(event.target.value)} placeholder="Оставьте пустым для всего реестра" /></label>
        <a className="primary download" href={api.exportRegistryUrl(q)}><FileDown size={18} />Скачать Excel</a>
      </section>
    </div>
  )
}
