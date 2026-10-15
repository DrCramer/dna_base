import { useMutation } from '@tanstack/react-query'
import { Check, FilePlus, Trash2, Upload, X } from 'lucide-react'
import { useRef, useState } from 'react'
import { api } from '../../api/client'
import type { GeneticObject, GeneticRtFile } from '../../api/types'
import { formatProtocolValue } from './ProtocolSupplementTables'

export function GeneticRtImport({ year, objects, onApplied, onClose }: { year: number; objects: GeneticObject[]; onApplied: (objects: GeneticObject[], matched: number) => void; onClose: () => void }) {
  const [files, setFiles] = useState<File[]>([])
  const [preview, setPreview] = useState<GeneticRtFile[]>([])
  const [mapping, setMapping] = useState<Record<string, number>>({})
  const [included, setIncluded] = useState<Record<string, boolean>>({})
  const [mode, setMode] = useState<'attempt' | 'replace'>('attempt')
  const [confirmDuplicate, setConfirmDuplicate] = useState(false)
  const [offset, setOffset] = useState(0)
  const input = useRef<HTMLInputElement>(null)
  const key = (uploadId: string, sample: string) => `${uploadId}:${sample}`
  function addFiles(added: File[]) {
    setFiles((previous) => [...previous, ...added.filter((file) => !previous.some((item) => item.name === file.name && item.size === file.size && item.lastModified === file.lastModified))])
    setPreview([])
  }
  const analyze = useMutation({ gcTime: 0, mutationFn: () => api.geneticRtPreview(year, objects.map((obj) => obj.id), files), onSuccess: (result) => {
    setPreview(result.files)
    setOffset(0)
    setMapping(Object.fromEntries(result.files.flatMap((file) => file.samples.map((sample) => [key(file.upload_id, sample.normalized_sample_name), sample.object_id || 0]))))
    setIncluded(Object.fromEntries(result.files.flatMap((file) => file.samples.map((sample) => [key(file.upload_id, sample.normalized_sample_name), Boolean(sample.object_id)]))))
  } })
  const rows = preview.flatMap((file) => file.samples.map((sample) => ({ file, sample, key: key(file.upload_id, sample.normalized_sample_name) })))
  const chosen = rows.filter((row) => included[row.key])
  const duplicates = preview.filter((file) => file.duplicate).length
  const apply = useMutation({ gcTime: 0, mutationFn: () => api.geneticRtCommit({ examination_year: year, object_ids: objects.map((obj) => obj.id), upload_ids: preview.map((file) => file.upload_id), mappings: chosen.map(({ file, sample, key }) => ({ upload_id: file.upload_id, sample_key: sample.normalized_sample_name, object_id: mapping[key] })), excluded_samples: rows.filter((row) => !included[row.key]).map(({ file, sample }) => ({ upload_id: file.upload_id, sample_key: sample.normalized_sample_name })), mode, confirm_duplicate: confirmDuplicate }), onSuccess: (result) => { onApplied(result.objects, result.matched); onClose() } })
  const pending = analyze.isPending || apply.isPending
  const error = analyze.error || apply.error
  return <div className="modal-backdrop" onMouseDown={() => { if (!pending) onClose() }}><div className="modal genetic-import-modal" role="dialog" aria-modal="true" aria-label="Импорт RT экспертиз" onMouseDown={(event) => event.stopPropagation()}>
    <div className="genetic-dialog-title"><h2>Импорт RT · {year}</h2><button type="button" className="icon-only" title="Закрыть" disabled={pending} onClick={onClose}><X size={18} /></button></div>
    <input ref={input} hidden type="file" multiple accept=".xlsx,.xls,.csv" onChange={(event) => { addFiles(Array.from(event.target.files || [])); event.target.value = '' }} />
    <div className="genetic-upload-area" onDragOver={(event) => event.preventDefault()} onDrop={(event) => { event.preventDefault(); if (!pending) addFiles(Array.from(event.dataTransfer.files)) }}>
      <button type="button" className="icon-button" disabled={pending} onClick={() => input.current?.click()}><FilePlus size={17} />Добавить RT-файлы</button>
      {files.map((file, index) => <div className="genetic-upload-file" key={`${file.name}-${index}`}><span>{file.name}</span><button type="button" className="icon-only" title="Убрать файл" disabled={pending} onClick={() => { setFiles((items) => items.filter((_, i) => i !== index)); setPreview([]) }}><Trash2 size={15} /></button></div>)}
    </div>
    {error ? <div className="alert danger">{error instanceof Error ? error.message : 'Не удалось импортировать RT'}</div> : null}
    {preview.length ? <>
      <div className="genetic-import-summary">Совпало: {rows.filter((row) => row.sample.status === 'matched').length} · Не найдено: {rows.filter((row) => row.sample.status === 'unmatched').length} · Неоднозначно: {rows.filter((row) => row.sample.status === 'ambiguous').length} · Уже импортировано: {duplicates}</div>
      <div className="genetic-import-table"><table><thead><tr><th /><th>Файл / образец</th><th>Long</th><th>Small</th><th>Y</th><th>Ct/Cq</th><th>Сопоставление</th></tr></thead><tbody>{rows.slice(offset, offset + 100).map(({ file, sample, key }) => <tr key={key}><td><input type="checkbox" aria-label={`Импортировать ${sample.sample_name_raw}`} checked={included[key] || false} disabled={pending} onChange={(event) => setIncluded((current) => ({ ...current, [key]: event.target.checked }))} /></td><td><strong>{sample.sample_name_raw}</strong><small>{file.filename}</small><small>{sample.status === 'ambiguous' ? 'Неоднозначно' : sample.status === 'unmatched' ? 'Не найдено' : 'Совпало'}</small></td><td>{formatProtocolValue(sample.long_quantity)}</td><td>{formatProtocolValue(sample.small_quantity)}</td><td>{formatProtocolValue(sample.y_quantity)}</td><td>{formatProtocolValue(sample.targets.small?.ct)}</td><td><select aria-label={`Объект для ${sample.sample_name_raw}`} value={mapping[key] || ''} disabled={pending} onChange={(event) => { const id = Number(event.target.value); setMapping((current) => ({ ...current, [key]: id })); setIncluded((current) => ({ ...current, [key]: Boolean(id) })) }}><option value="">Не импортировать</option>{objects.map((obj) => <option key={obj.id} value={obj.id}>{obj.display_name} · {obj.examination_no}-{obj.examination_year}</option>)}</select></td></tr>)}</tbody></table></div>
      {rows.length > 100 ? <div className="protocol-pagination"><button type="button" disabled={!offset} onClick={() => setOffset(Math.max(0, offset - 100))}>Назад</button><span>{offset + 1}–{Math.min(offset + 100, rows.length)} из {rows.length}</span><button type="button" disabled={offset + 100 >= rows.length} onClick={() => setOffset(offset + 100)}>Далее</button></div> : null}
      <div className="genetic-import-options"><label>Результаты<select value={mode} disabled={pending} onChange={(event) => setMode(event.target.value as typeof mode)}><option value="attempt">Новая попытка</option><option value="replace">Заменить выбранные результаты</option></select></label>{duplicates ? <label><input type="checkbox" disabled={pending} checked={confirmDuplicate} onChange={(event) => setConfirmDuplicate(event.target.checked)} />Подтверждаю повторный импорт файлов</label> : null}</div>
      <details><summary>Подробности</summary>{preview.map((file) => <section key={file.upload_id}><strong>{file.filename}</strong>{file.warnings.map((warning) => <p key={warning}>{warning}</p>)}<div>{file.samples.slice(0, 100).map((sample) => <small key={sample.normalized_sample_name}>{sample.sample_name_raw} · ключ: {sample.normalized_sample_name}<br /></small>)}</div></section>)}</details>
    </> : null}
    <div className="modal-actions"><button type="button" className="icon-button" disabled={pending} onClick={onClose}>Отмена</button><button type="button" className="icon-button" disabled={!files.length || pending} onClick={() => analyze.mutate()}><Upload size={17} />{analyze.isPending ? 'Анализ...' : 'Проверить файлы'}</button>{preview.length ? <button type="button" className="primary compact" disabled={pending || !chosen.length || chosen.some((row) => !mapping[row.key]) || preview.some((file) => !chosen.some((row) => row.file.upload_id === file.upload_id)) || Boolean(duplicates && !confirmDuplicate)} onClick={() => { if (mode === 'replace' && !window.confirm('Заменить текущие результаты выбранных объектов? Предыдущие измерения сохранятся в истории.')) return; apply.mutate() }}><Check size={17} />Импортировать</button> : null}</div>
  </div></div>
}
