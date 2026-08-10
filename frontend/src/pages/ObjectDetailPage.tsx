import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ArrowLeft, Save } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { api } from '../api/client'
import type { RegistryObject, StageEvent, User } from '../api/types'
import { EmptyState, ErrorState, LoadingState } from '../components/ui'

const tabs = ['Обзор', 'Регистрация', 'Пробоподготовка', 'Измельчение', 'Выделение', 'RealTime', 'ПЦР', 'Электрофорез', 'Анализ', 'Файлы', 'История']

const stageLabels: Record<string, string> = {
  sample_prep: 'Пробоподготовка',
  milling: 'Измельчение',
  dna_extraction: 'Выделение',
  realtime: 'RealTime',
  pcr: 'ПЦР',
  electrophoresis: 'Электрофорез',
  analysis: 'Анализ',
  photo: 'Фотофиксация',
  washing: 'Отмывка',
  soft_tissue_grinding: 'Размельчение / ткани',
  mill_grinding: 'Мельница'
}

const sourceLabels: Record<string, string> = {
  registry_excel: 'импортировано из Excel',
  manual: 'внесено вручную',
  rt_import: 'импорт RT',
  legacy: 'старые данные'
}

const statusLabels: Record<string, string> = {
  new: 'новый',
  active: 'активна',
  archived: 'архив',
  draft: 'черновик',
  applied: 'применено',
  cancelled: 'отменено'
}

const detailLabels: Record<string, string> = {
  registry_filled_by: 'Заполнение реестра',
  photo_performers: 'Фотофиксация',
  photo_assistants: 'Помощь в фотофиксации',
  washing_performers: 'Отмывка',
  washing_assistants: 'Помощь в отмывке',
  washing_date: 'Дата отмывки',
  bone_tissue_performers: 'Размельчение / изъятие тканей',
  bone_tissue_date: 'Дата размельчения / изъятия',
  milling_performers: 'Размельчение на мельнице',
  cups: 'Стаканы',
  milling_date: 'Дата измельчения',
  extraction_date: 'Дата получения препарата ДНК',
  extraction_method: 'Метод получения препарата ДНК',
  quant_method: 'Метод измерения концентрации',
  quant_date: 'Дата измерения концентрации',
  quant_performer: 'Исполнитель RT',
  pipetting_method: 'Робот / ручной метод',
  concentration: 'Концентрация',
  ct_cq: 'Ct / Cq',
  di: 'DI',
  ipc: 'IPC',
  long_quantity: 'Длинная',
  small_quantity: 'Короткая',
  y_quantity: 'Y',
  pcr_date: 'Дата PCR',
  locus_panel: 'Панель локусов',
  normalization_performers: 'Нормализация PCR',
  pcr_performers: 'Постановка PCR',
  electrophoresis_date: 'Дата электрофореза',
  sequencer: 'Секвенатор',
  performers: 'Исполнители',
  genotype: 'Генотип',
  analysis_date: 'Дата анализа',
  status: 'Статус анализа'
}

function value(text: string | number | null | undefined) {
  if (typeof text === 'number') return Number.isInteger(text) ? String(text) : text.toFixed(4)
  return text || '—'
}

function EmptyStage({ title = 'Нет записей этапа', description = 'Для этого объекта данные ещё не добавлены.' }: { title?: string; description?: string }) {
  return <EmptyState title={title}>{description}</EmptyState>
}

function performerText(event: StageEvent) {
  const names = event.performers?.map((item) => item.raw_name).filter(Boolean)
  return names?.length ? names.join(', ') : '—'
}

function detailSummary(event: StageEvent) {
  const detail =
    event.sample_prep_detail ||
    event.milling_detail ||
    event.dna_extraction_detail ||
    event.realtime_detail ||
    event.pcr_detail ||
    event.electrophoresis_detail ||
    event.analysis_detail
  if (!detail) return '—'
  const parts = Object.entries(detail)
    .filter(([, item]) => {
      if (Array.isArray(item)) return item.length > 0
      return item !== null && item !== undefined && item !== ''
    })
    .map(([key, item]) => `${key}: ${Array.isArray(item) ? item.join(', ') : item}`)
    .map((text) => {
      const index = text.indexOf(':')
      if (index < 0) return text
      const key = text.slice(0, index)
      return `${detailLabels[key] || key}${text.slice(index)}`
    })
  return parts.length ? parts.join('; ') : '—'
}

function StageTable({
  columns,
  rows
}: {
  columns: string[]
  rows: Array<Array<string | number | null | undefined>>
}) {
  if (!rows.length) return <EmptyStage />
  return (
    <div className="stage-table">
      <div className="stage-row stage-head">{columns.map((column) => <div key={column}>{column}</div>)}</div>
      {rows.map((row, index) => (
        <div className="stage-row" key={index}>
          {row.map((cell, cellIndex) => <div key={cellIndex}>{value(cell)}</div>)}
        </div>
      ))}
    </div>
  )
}

function canonicalRows(events: StageEvent[], stageType: string) {
  return events
    .filter((event) => !event.is_cancelled && event.stage_type === stageType)
    .sort((a, b) => a.attempt_no - b.attempt_no || (a.event_date || '').localeCompare(b.event_date || ''))
    .map((event) => [
      event.attempt_no,
      event.event_date,
      performerText(event),
      sourceLabels[event.source] || event.source,
      event.comment,
      detailSummary(event)
    ])
}

function editableFields(data: RegistryObject): Partial<RegistryObject> {
  return {
    party_no: data.party_no,
    rcsme_reg_no: data.rcsme_reg_no,
    decree_no: data.decree_no,
    investigator: data.investigator,
    box_no: data.box_no,
    object_type: data.object_type,
    status: data.status,
    object_description: data.object_description
  }
}

export function ObjectDetailPage({
  id,
  user,
  onBack,
  onPartyOpen
}: {
  id: number
  user: User
  onBack: () => void
  onPartyOpen: (partyNo: string) => void
}) {
  const queryClient = useQueryClient()
  const { data, isLoading, isError, error, refetch } = useQuery({ queryKey: ['object', id], queryFn: () => api.object(id) })
  const [form, setForm] = useState<Partial<RegistryObject>>({})
  const [tab, setTab] = useState(tabs[0])
  const canEdit = user.role !== 'viewer'
  const events = useMemo(() => [...(data?.stage_events ?? [])].sort((a, b) => (b.event_date || '').localeCompare(a.event_date || '') || b.id - a.id), [data])
  useEffect(() => { if (data) setForm(editableFields(data)) }, [data])
  const isDirty = useMemo(() => data ? JSON.stringify(form) !== JSON.stringify(editableFields(data)) : false, [data, form])
  const save = useMutation({
    mutationFn: () => api.updateObject(id, form),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['object', id] })
  })
  if (isLoading) return <div className="page"><button className="icon-button page-back-button" onClick={onBack}><ArrowLeft size={18} />Назад</button><LoadingState title="Загрузка карточки объекта..." rows={6} /></div>
  if (isError || !data) return <div className="page"><button className="icon-button page-back-button" onClick={onBack}><ArrowLeft size={18} />Назад</button><ErrorState error={error} onRetry={() => void refetch()} /></div>
  function setField(key: keyof RegistryObject, nextValue: string) {
    setForm((prev) => ({ ...prev, [key]: nextValue || null }))
  }
  const canonicalColumns = ['Попытка', 'Дата', 'Исполнители', 'Источник', 'Комментарий', 'Детали']
  return (
    <div className="page">
      <header className="page-header">
        <button className="icon-button" onClick={onBack}><ArrowLeft size={18} />Назад</button>
        <h1>{data.rcsme_reg_no || data.decree_no || `Объект ${data.id}`}</h1>
        {canEdit && <button className="primary compact" disabled={!isDirty || save.isPending} onClick={() => save.mutate()}><Save size={18} />{save.isPending ? 'Сохранение...' : 'Сохранить'}</button>}
      </header>
      <div className="tabs">{tabs.map((item) => <button key={item} className={tab === item ? 'active' : ''} onClick={() => setTab(item)}>{item}</button>)}</div>
      {tab === 'Обзор' ? (
        <section className="section">
          <div className="overview-grid">
            <div><span>Партия</span><strong>{data.party_no || '—'}</strong></div>
            <div><span>№ постановления</span><strong>{data.decree_no || '—'}</strong></div>
            <div><span>Тип</span><strong>{data.object_type || '—'}</strong></div>
            <div><span>Статус</span><strong>{statusLabels[data.status || 'new'] || data.status || 'новый'}</strong></div>
          </div>
          <h2>Timeline</h2>
          <div className="timeline">
            {events.map((event) => (
              <div className="timeline-row" key={event.id}>
                <span>{event.event_date || event.created_at.slice(0, 10)}</span>
                <strong>{stageLabels[event.stage_type] || event.stage_type} #{event.attempt_no}</strong>
                <em>{performerText(event)}</em>
              </div>
            ))}
            {!events.length && <EmptyStage title="История работы пока отсутствует" description="События этапов появятся здесь после первого заполнения." />}
          </div>
        </section>
      ) : tab === 'Регистрация' ? (
        <section className="form-grid">
          {data.party_no && <div className="wide inline-summary"><span>Партия</span><button className="link-button" onClick={() => onPartyOpen(data.party_no!)}>{data.party_no}</button></div>}
          <label>Партия<input disabled={!canEdit} value={form.party_no || ''} onChange={(e) => setField('party_no', e.target.value)} /></label>
          <label>№ рег РЦСМЭ<input disabled={!canEdit} value={form.rcsme_reg_no || ''} onChange={(e) => setField('rcsme_reg_no', e.target.value)} /></label>
          <label>№ постановления<input disabled={!canEdit} value={form.decree_no || ''} onChange={(e) => setField('decree_no', e.target.value)} /></label>
          <label>Следователь<input disabled={!canEdit} value={form.investigator || ''} onChange={(e) => setField('investigator', e.target.value)} /></label>
          <label>Коробка<input disabled={!canEdit} value={form.box_no || ''} onChange={(e) => setField('box_no', e.target.value)} /></label>
          <label>Тип объекта<input disabled={!canEdit} value={form.object_type || ''} onChange={(e) => setField('object_type', e.target.value)} /></label>
          <label>Статус
            <select disabled={!canEdit} value={form.status || 'new'} onChange={(e) => setField('status', e.target.value)}>
              {['new', 'active', 'archived'].map((item) => <option value={item} key={item}>{statusLabels[item] || item}</option>)}
            </select>
          </label>
          <label className="wide">Описание<textarea disabled={!canEdit} value={form.object_description || ''} onChange={(e) => setField('object_description', e.target.value)} /></label>
          {data.rcsme_reg_no_is_manual && <div className="wide alert">№ рег РЦСМЭ отмечен как ручной.</div>}
        </section>
      ) : tab === 'Пробоподготовка' ? (
        <section className="section">
          <h2>Пробоподготовка</h2>
          {canonicalRows(events, 'sample_prep').length ? (
            <StageTable columns={canonicalColumns} rows={canonicalRows(events, 'sample_prep')} />
          ) : (
            <StageTable
              columns={['Этап', 'Дата', 'Исполнитель', 'Помощник', 'Комментарий']}
              rows={[...(data.prep_events || [])]
                .filter((event) => event.stage_type !== 'mill_grinding')
                .map((event) => [stageLabels[event.stage_type] || event.stage_type, event.event_date, event.performer, event.assistant, event.comment])}
            />
          )}
        </section>
      ) : tab === 'Измельчение' ? (
        <section className="section">
          <h2>Измельчение</h2>
          {canonicalRows(events, 'milling').length ? (
            <StageTable columns={canonicalColumns} rows={canonicalRows(events, 'milling')} />
          ) : (
            <StageTable
              columns={['Этап', 'Дата', 'Исполнитель', 'Комментарий']}
              rows={[...(data.prep_events || [])]
                .filter((event) => event.stage_type === 'mill_grinding')
                .map((event) => [stageLabels[event.stage_type] || event.stage_type, event.event_date, event.performer, event.comment])}
            />
          )}
        </section>
      ) : tab === 'Выделение' ? (
        <section className="section">
          <h2>Выделение</h2>
          {canonicalRows(events, 'dna_extraction').length ? (
            <StageTable columns={canonicalColumns} rows={canonicalRows(events, 'dna_extraction')} />
          ) : (
            <StageTable
              columns={['№', 'Дата', 'Исполнитель', 'Метод', 'Комментарий']}
              rows={[...(data.dna_extractions || [])].sort((a, b) => a.extraction_no - b.extraction_no).map((event) => [event.extraction_no, event.extraction_date, event.performer, event.extraction_method, event.comment])}
            />
          )}
        </section>
      ) : tab === 'RealTime' ? (
        <section className="section">
          <h2>RealTime</h2>
          <StageTable
            columns={['Источник', 'Дата', 'Метод/мишень', 'Исполнитель', 'Длинная', 'Короткая', 'Y']}
            rows={[
              ...events
                .filter((event) => !event.is_cancelled && event.stage_type === 'realtime')
                .sort((a, b) => a.attempt_no - b.attempt_no || (a.event_date || '').localeCompare(b.event_date || ''))
                .map((event) => {
                  const detail = (event.realtime_detail || {}) as Record<string, string | number | null | undefined>
                  return [
                    `Повтор ${event.attempt_no}`,
                    event.event_date,
                    detail.quant_method,
                    detail.quant_performer || performerText(event),
                    detail.long_quantity,
                    detail.small_quantity,
                    detail.y_quantity
                  ]
                }),
              ...(data.rt_results || []).map((event) => [
                event.sample_name_raw || event.normalized_sample_name,
                null,
                event.target,
                event.well,
                event.quantity_ng_ul ?? event.mean_quantity_ng_ul,
                null,
                null
              ])
            ]}
          />
        </section>
      ) : tab === 'ПЦР' ? (
        <section className="section">
          <h2>ПЦР</h2>
          {canonicalRows(events, 'pcr').length ? (
            <StageTable columns={canonicalColumns} rows={canonicalRows(events, 'pcr')} />
          ) : (
            <StageTable
              columns={['Дата', 'Панель', 'Раскапывание', 'Нормализация', 'Постановка', 'Комментарий']}
              rows={(data.pcr_events || []).map((event) => [event.pcr_date, event.locus_panel, event.pipetting_method, event.normalization_performer, event.pcr_performer, event.comment])}
            />
          )}
        </section>
      ) : tab === 'Электрофорез' ? (
        <section className="section">
          <h2>Электрофорез</h2>
          {canonicalRows(events, 'electrophoresis').length ? (
            <StageTable columns={canonicalColumns} rows={canonicalRows(events, 'electrophoresis')} />
          ) : (
            <StageTable
              columns={['Дата', 'Секвенатор', 'Раскапывание', 'Исполнитель 1', 'Исполнитель 2', 'Генотип']}
              rows={(data.electrophoresis_events || []).map((event) => [event.electrophoresis_date, event.sequencer, event.pipetting_method, event.performer_1, event.performer_2, event.genotype])}
            />
          )}
        </section>
      ) : tab === 'Анализ' ? (
        <section className="section">
          <h2>Анализ</h2>
          {canonicalRows(events, 'analysis').length ? (
            <StageTable columns={canonicalColumns} rows={canonicalRows(events, 'analysis')} />
          ) : (
            <StageTable
              columns={['Попытка', 'Дата', 'Исполнитель', 'Статус', 'Комментарий']}
              rows={[...(data.electrophoresis_analysis_events || [])].sort((a, b) => a.attempt_no - b.attempt_no).map((event) => [event.attempt_no, event.analysis_date, event.performer, event.result_status, event.comment])}
            />
          )}
        </section>
      ) : tab === 'Файлы' ? (
        <section className="section">
          <h2>Файлы</h2>
          {(data.electrophoresis_result_files || []).length ? (
            <StageTable
              columns={['Файл', 'Тип', 'Дата загрузки', 'Образец']}
              rows={(data.electrophoresis_result_files || []).map((file) => [
                file.filename,
                file.file_type,
                file.uploaded_at?.slice(0, 10),
                String(file.raw_json?.sample_name_raw || file.raw_json?.sample_object_no || '')
              ])}
            />
          ) : <EmptyStage title="Файлы пока не добавлены" description="PDF фореза и связанные файлы появятся здесь после импорта." />}
        </section>
      ) : (
        <section className="section">
          <h2>{tab}</h2>
          <EmptyStage title="История изменений пока отсутствует" description="Аудит действий появится здесь, когда для объекта будут сохранены изменения." />
        </section>
      )}
    </div>
  )
}
