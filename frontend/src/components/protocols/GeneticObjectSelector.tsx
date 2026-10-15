import { useMutation } from '@tanstack/react-query'
import { Check, ClipboardPaste, FileSpreadsheet, FlaskConical, X } from 'lucide-react'
import { useRef, useState } from 'react'
import { api } from '../../api/client'
import type { GeneticApplyResult, GeneticExcelPreview, GeneticNumberInput, GeneticNumbersPreview, GeneticObject, ProtocolWell } from '../../api/types'
import { GeneticRtImport } from './GeneticRtImport'
import { ProtocolPlate } from './ProtocolPlate'

export function GeneticObjectSelector({ year, objects, selectedIds, onYear, onSelectedIds, onApply, onRt }: {
  year: number; objects: GeneticObject[]; selectedIds: number[]
  onYear: (year: number) => void; onSelectedIds: (ids: number[]) => void
  onApply: (result: GeneticApplyResult, replace: boolean) => void
  onRt: (objects: GeneticObject[]) => void
}) {
  const [dialog, setDialog] = useState<'numbers' | 'excel' | 'rt' | null>(null)
  const [text, setText] = useState('')
  const [items, setItems] = useState<GeneticNumberInput[]>([])
  const [preview, setPreview] = useState<GeneticNumbersPreview | null>(null)
  const [excel, setExcel] = useState<GeneticExcelPreview | null>(null)
  const [fields, setFields] = useState(['header', 'stages', 'layout'])
  const [stageFields, setStageFields] = useState(['date', 'kit', 'performers', 'sequencer', 'comment'])
  const [wellMappings, setWellMappings] = useState<Record<string, string>>({})
  const [notice, setNotice] = useState('')
  const [offset, setOffset] = useState(0)
  const [previewOffset, setPreviewOffset] = useState(0)
  const [layoutOpen, setLayoutOpen] = useState(false)
  const [layoutKey, setLayoutKey] = useState('')
  const input = useRef<HTMLInputElement>(null)
  const selected = new Set(selectedIds)
  const activeObjects = objects.filter((obj) => selected.has(obj.id))
  const analyze = useMutation({ gcTime: 0, mutationFn: () => api.geneticNumbersPreview(year, items.length ? items : text.split(/\r?\n/).filter((line) => line.trim()).map((raw_name) => ({ raw_name }))), onSuccess: (result) => { setPreview(result); setItems(result.items.map(({ raw_name, examination_no, description, source_key }) => ({ raw_name, examination_no, description, source_key }))); setPreviewOffset(0) } })
  const upload = useMutation({ gcTime: 0, mutationFn: (file: File) => api.geneticExcelPreview(year, file), onSuccess: (result) => {
    setExcel(result); setPreview(result)
    setItems(result.items.map(({ raw_name, examination_no, description, source_key }) => ({ raw_name, examination_no, description, source_key })))
    const mappings: Record<string, string> = {}
    for (const [key, layout] of Object.entries(result.layouts)) {
      for (const cell of layout.filter((entry) => entry.kind === 'sample')) {
        const coordinate = `${key}:${cell.plate_index}:${cell.well}`
        const direct = result.items.find((item) => item.source_key === coordinate)
        const candidates = result.items.filter((item) => item.normalized_name === cell.normalized_sample_name)
        mappings[coordinate] = direct?.source_key || (candidates.length === 1 ? candidates[0].source_key : '') || ''
      }
    }
    setWellMappings(mappings); setDialog('excel'); setPreviewOffset(0); setLayoutKey(''); setLayoutOpen(false)
  } })
  const apply = useMutation({ gcTime: 0, mutationFn: (replace: boolean) => dialog === 'excel' && excel ? api.geneticExcelApply(year, excel.upload_id, items, fields, stageFields, wellMappings).then((result) => ({ result, replace })) : api.geneticNumbersApply(year, items).then((result) => ({ result, replace })), onSuccess: ({ result, replace }) => { onApply(result, replace); setNotice(`Добавлено: ${result.added} · Уже существует: ${result.existing} · Требует уточнения: ${result.unresolved}`); setDialog(null) } })
  const pending = analyze.isPending || upload.isPending || apply.isPending
  const error = analyze.error || upload.error || apply.error
  function openNumbers() { setDialog('numbers'); setText(''); setItems([]); setPreview(null); setExcel(null); analyze.reset(); apply.reset() }
  function applySelection(replace: boolean) {
    if (selectedIds.length && replace && !window.confirm('Заменить текущий состав протокола?')) return
    apply.mutate(replace)
  }
  const plateKeys = excel ? Object.entries(excel.layouts).flatMap(([key, cells]) => Array.from(new Set(cells.map((cell) => cell.plate_index))).map((index) => `${key}:${index}`)) : []
  const selectedLayoutKey = layoutKey || plateKeys[0] || ''
  const [source, index] = selectedLayoutKey.split(':')
  const cells = (excel?.layouts[source] || []).filter((cell) => cell.plate_index === Number(index))
  return <div className="genetic-object-selector">
    <div className="genetic-selector-toolbar"><label>Год экспертизы<input key={year} type="number" min={1900} max={2200} aria-label="Год экспертизы" defaultValue={year} disabled={pending} onBlur={(event) => { const next = Number(event.target.value); event.target.value = String(year); if (Number.isInteger(next) && next >= 1900 && next <= 2200) onYear(next) }} /></label><button type="button" className="icon-button" disabled={pending} onClick={openNumbers}><ClipboardPaste size={17} />Вставить список номеров</button><button type="button" className="icon-button" disabled={pending} onClick={() => input.current?.click()}><FileSpreadsheet size={17} />Импорт Excel протокола</button><button type="button" className="icon-button" disabled={!activeObjects.length || pending} onClick={() => setDialog('rt')}><FlaskConical size={17} />Импорт RT</button><input ref={input} hidden type="file" accept=".xlsx" onChange={(event) => { const file = event.target.files?.[0]; if (file) { upload.reset(); apply.reset(); upload.mutate(file) } event.target.value = '' }} /></div>
    <div className="genetic-import-summary">Экспертизы: {Array.from(new Set(activeObjects.map((obj) => `${obj.examination_no}-${obj.examination_year}`))).join(', ') || '—'} · Объектов: {selectedIds.length} · Без концентрации Small: {activeObjects.filter((obj) => !obj.rt?.small_quantity || obj.rt.small_quantity <= 0).length}</div>
    {notice ? <div className="muted">{notice}</div> : null}{upload.error && !dialog ? <div className="alert danger">{upload.error instanceof Error ? upload.error.message : 'Не удалось прочитать Excel'}</div> : null}
    {objects.length ? <><div className="protocol-selection-actions"><label><input type="checkbox" aria-label="Все объекты экспертиз" checked={objects.every((obj) => selected.has(obj.id))} onChange={(event) => onSelectedIds(event.target.checked ? objects.map((obj) => obj.id) : [])} />Все объекты</label><strong>Выбрано: {selectedIds.length}</strong></div><div className="genetic-import-table"><table><thead><tr><th /><th>Объект</th><th>Экспертиза</th><th>Описание</th><th>RT Small</th></tr></thead><tbody>{objects.slice(offset, offset + 100).map((obj) => <tr key={obj.id}><td><input type="checkbox" aria-label={`Выбрать ${obj.display_name}`} checked={selected.has(obj.id)} onChange={(event) => onSelectedIds(event.target.checked ? [...selectedIds, obj.id] : selectedIds.filter((id) => id !== obj.id))} /></td><td><strong>{obj.display_name}</strong></td><td>{obj.examination_no}-{obj.examination_year}</td><td>{obj.description || '—'}</td><td>{obj.rt?.small_quantity ?? '—'}</td></tr>)}</tbody></table></div>{objects.length > 100 ? <div className="protocol-pagination"><button type="button" disabled={!offset} onClick={() => setOffset(Math.max(0, offset - 100))}>Назад</button><span>{offset + 1}–{Math.min(offset + 100, objects.length)} из {objects.length}</span><button type="button" disabled={offset + 100 >= objects.length} onClick={() => setOffset(offset + 100)}>Далее</button></div> : null}</> : null}
    {dialog === 'rt' ? <GeneticRtImport year={year} objects={activeObjects} onClose={() => setDialog(null)} onApplied={(updated, matched) => { onRt(updated); setNotice(`RT совпало: ${matched}`) }} /> : null}
    {dialog === 'numbers' || dialog === 'excel' ? <div className="modal-backdrop" onMouseDown={() => { if (!pending) setDialog(null) }}><div className="modal genetic-import-modal" role="dialog" aria-modal="true" aria-label={dialog === 'excel' ? 'Импорт Excel экспертиз' : 'Список номеров экспертиз'} onMouseDown={(event) => event.stopPropagation()}>
      <div className="genetic-dialog-title"><h2>{dialog === 'excel' ? excel?.filename || 'Импорт Excel протокола' : 'Вставить список номеров'} · {year}</h2><button type="button" className="icon-only" title="Закрыть" disabled={pending} onClick={() => setDialog(null)}><X size={18} /></button></div>
      {dialog === 'numbers' ? <textarea rows={8} aria-label="Номера объектов экспертиз" placeholder={'251-1\n251-2\n252-1\nАБ-125/1'} value={text} disabled={pending} onChange={(event) => { setText(event.target.value); setItems([]); setPreview(null) }} /> : null}
      {error ? <div className="alert danger">{error instanceof Error ? error.message : 'Не удалось применить импорт'}</div> : null}
      {preview ? <><div className="genetic-import-summary">Добавлено: {preview.added} · Уже существует: {preview.existing} · Требует уточнения: {preview.unresolved}</div><div className="genetic-import-table"><table><thead><tr><th>Исходное имя</th><th>Год</th><th>№ экспертизы</th><th>Индекс</th><th>Состояние</th></tr></thead><tbody>{items.slice(previewOffset, previewOffset + 100).map((item, i) => { const rowIndex = previewOffset + i; const row = preview.items[rowIndex]; return <tr key={rowIndex}><td><input aria-label={`Имя объекта ${rowIndex + 1}`} value={item.raw_name} disabled={pending} onChange={(event) => { setItems((previous) => previous.map((entry, index) => index === rowIndex ? { ...entry, raw_name: event.target.value } : entry)); setPreview((current) => current ? { ...current, unresolved: 1 } : current) }} /></td><td>{year}</td><td><input aria-label={`Экспертиза объекта ${rowIndex + 1}`} value={item.examination_no || ''} disabled={pending} onChange={(event) => { setItems((previous) => previous.map((entry, index) => index === rowIndex ? { ...entry, examination_no: event.target.value } : entry)); setPreview((current) => current ? { ...current, unresolved: 1 } : current) }} /></td><td>{row?.object_index ?? '—'}</td><td>{row?.error || (row?.existing ? 'Уже существует' : 'Распознан')}</td></tr> })}</tbody></table></div>{items.length > 100 ? <div className="protocol-pagination"><button type="button" disabled={!previewOffset} onClick={() => setPreviewOffset(Math.max(0, previewOffset - 100))}>Назад</button><span>{previewOffset + 1}–{Math.min(previewOffset + 100, items.length)} из {items.length}</span><button type="button" disabled={previewOffset + 100 >= items.length} onClick={() => setPreviewOffset(previewOffset + 100)}>Далее</button></div> : null}</> : null}
      {excel && dialog === 'excel' ? <>
        <div className="genetic-import-options">{([['header', 'Шапка'], ['stages', 'Поля этапов'], ['layout', 'Лунки Excel']] as const).map(([field, label]) => <label key={field}><input type="checkbox" checked={fields.includes(field)} onChange={(event) => setFields((current) => event.target.checked ? [...current, field] : current.filter((item) => item !== field))} />{label}</label>)}</div>
        {fields.includes('stages') ? <div className="genetic-import-options">{([['date', 'Даты'], ['kit', 'Наборы'], ['performers', 'Исполнители'], ['sequencer', 'Секвенатор'], ['comment', 'Комментарии']] as const).map(([field, label]) => <label key={field}><input type="checkbox" checked={stageFields.includes(field)} onChange={(event) => setStageFields((current) => event.target.checked ? [...current, field] : current.filter((item) => item !== field))} />{label}</label>)}</div> : null}
        <details onToggle={(event) => setLayoutOpen(event.currentTarget.open)}><summary>Лунки и параметры Excel</summary>{layoutOpen ? <>
          <select aria-label="Плашка Excel" value={selectedLayoutKey} onChange={(event) => setLayoutKey(event.target.value)}>{plateKeys.map((key) => <option key={key} value={key}>{key.startsWith('source') ? 'Исходная' : 'PCR'} · плашка {key.split(':')[1]}</option>)}</select>
          {cells.length ? <ProtocolPlate title={`${source === 'source' ? 'Исходная' : 'PCR'} · плашка ${index}`} plate={{ plate_index: Number(index), sample_count: cells.filter((cell) => cell.kind === 'sample').length, wells: cells.map((cell, order_index) => ({ plate_index: cell.plate_index, well: cell.well, kind: cell.kind as ProtocolWell['kind'], object_id: null, display_name: items.find((item) => item.source_key === wellMappings[`${source}:${cell.plate_index}:${cell.well}`])?.raw_name || cell.sample_name_raw, label: null, order_index })) }} /> : null}
          <div className="genetic-import-table"><table><thead><tr><th>Лунка</th><th>Имя в Excel</th><th>Объект</th></tr></thead><tbody>{cells.filter((cell) => cell.kind === 'sample').map((cell) => {
            const coordinate = `${source}:${cell.plate_index}:${cell.well}`
            return <tr key={coordinate}><td>{cell.well}</td><td>{cell.sample_name_raw}</td><td><select aria-label={`Объект в ${source === 'source' ? 'исходной' : 'PCR'} ${index} ${cell.well}`} value={wellMappings[coordinate] || ''} disabled={pending} onChange={(event) => setWellMappings((current) => ({ ...current, [coordinate]: event.target.value }))}><option value="">Уточнить объект...</option>{items.map((item) => <option key={item.source_key} value={item.source_key || undefined}>{item.raw_name} · {item.examination_no || '№ экспертизы не указан'}</option>)}</select></td></tr>
          })}</tbody></table></div>
          {excel.stage_blocks.map((stage) => <div key={stage.stage_type}>{stage.stage_type === 'extraction' ? 'Выделение' : stage.stage_type} · {Object.values(stage.detail_data).filter(Boolean).join(' · ')} · {stage.performers.map((performer) => performer.raw_name).join(', ')}</div>)}{excel.warnings.map((warning) => <p key={warning}>{warning}</p>)}
        </> : null}</details>
      </> : null}
      <div className="modal-actions"><button type="button" className="icon-button" disabled={pending} onClick={() => setDialog(null)}>Отмена</button><button type="button" className="icon-button" disabled={pending || !items.length && !text.trim()} onClick={() => analyze.mutate()}><Check size={17} />Проверить</button>{preview ? <><button type="button" className="icon-button" disabled={pending || Boolean(preview.unresolved)} onClick={() => applySelection(false)}>Добавить к текущему</button><button type="button" className="primary compact" disabled={pending || Boolean(preview.unresolved)} onClick={() => applySelection(true)}>Заменить текущий список</button></> : null}</div>
    </div></div> : null}
  </div>
}
