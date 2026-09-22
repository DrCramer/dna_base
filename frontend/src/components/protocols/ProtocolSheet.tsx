import { X } from 'lucide-react'
import type { Employee, ProtocolPlateRules, ProtocolPreview, ProtocolProfile, ProtocolStageSettings, ReferenceItem } from '../../api/types'
import { ProtocolPlate } from './ProtocolPlate'

const stageLabels: Record<string, string> = { dna_extraction: 'Выделение', realtime: 'Real Time', pcr: 'PCR', electrophoresis: 'Форез' }

interface Props {
  protocolDate: string
  protocolNo: number
  name: string
  selectedCount: number
  stages: ProtocolStageSettings[]
  plateRules: ProtocolPlateRules
  preview: ProtocolPreview | null
  profiles: ProtocolProfile[]
  employees: Employee[]
  sequencers: ReferenceItem[]
  readOnly?: boolean
  onHeader: (patch: { protocolDate?: string; protocolNo?: number; name?: string }) => void
  onStage: (stageType: ProtocolStageSettings['stage_type'], patch: Partial<ProtocolStageSettings>) => void
  onRules: (patch: Partial<ProtocolPlateRules>) => void
}

export function ProtocolSheet({ protocolDate, protocolNo, name, selectedCount, stages, plateRules, preview, profiles, employees, sequencers, readOnly, onHeader, onStage, onRules }: Props) {
  const sourcePlates = preview?.layouts.source.plates || []
  const pcrPlates = preview?.layouts.pcr.plates || []
  return (
    <article className="protocol-sheet">
      <h2>ЕДИНЫЙ ПРОТОКОЛ ПЛАШКИ: ВЫДЕЛЕНИЕ / RT / PCR / ФОРЕЗ</h2>
      <div className="protocol-document-meta">
        <label><span>Дата</span><input type="date" value={protocolDate} disabled={readOnly} onChange={(event) => onHeader({ protocolDate: event.target.value })} /></label>
        <label><span>№</span><input type="number" min="1" value={protocolNo} disabled={readOnly} onChange={(event) => onHeader({ protocolNo: Number(event.target.value) || 1 })} /></label>
        <label className="protocol-name-field"><span>Название</span><input value={name} disabled={readOnly} onChange={(event) => onHeader({ name: event.target.value })} /></label>
        <label><span>Объектов / максимум</span><output>{selectedCount} / {preview?.capacity ?? (96 - Number(plateRules.nc_enabled) - Number(plateRules.pc_enabled) - (plateRules.ladder_enabled ? 6 : 0))}</output></label>
      </div>
      <div className="protocol-stage-grid">
        {stages.map((stage) => {
          const stageProfiles = profiles.filter((item) => item.stage_type === stage.stage_type)
          const eligible = employees.filter((employee) => employee.is_active).sort((left, right) => {
            const leftPreferred = left.stage_roles.some((item) => item.is_active && item.stage_type === (stage.stage_type === 'dna_extraction' ? 'extraction' : stage.stage_type))
            const rightPreferred = right.stage_roles.some((item) => item.is_active && item.stage_type === (stage.stage_type === 'dna_extraction' ? 'extraction' : stage.stage_type))
            return Number(rightPreferred) - Number(leftPreferred) || left.full_name.localeCompare(right.full_name, 'ru')
          })
          return (
            <section className="protocol-stage" key={stage.stage_type}>
              <h3>{stageLabels[stage.stage_type]}</h3>
              <label><span>Дата</span><input type="date" value={stage.work_date || ''} disabled={readOnly} onChange={(event) => onStage(stage.stage_type, { work_date: event.target.value || null })} /></label>
              <label><span>Набор</span><select value={stage.profile_id || ''} disabled={readOnly} onChange={(event) => { const id = Number(event.target.value) || null; const profile = stageProfiles.find((item) => item.id === id); onStage(stage.stage_type, { profile_id: id, kit_name: profile?.name || null }) }}><option value="">—</option>{stageProfiles.map((item) => <option value={item.id} key={item.id}>{item.name}</option>)}</select></label>
              <label className="protocol-performer-select"><span>Исполнители</span><select value="" disabled={readOnly} onChange={(event) => { const id = Number(event.target.value); if (id && !stage.performer_ids.includes(id)) onStage(stage.stage_type, { performer_ids: [...stage.performer_ids, id] }) }}><option value="">Добавить...</option>{eligible.map((employee) => <option key={employee.id} value={employee.id}>{employee.short_name || employee.full_name}</option>)}</select></label>
              <div className="protocol-performer-chips">{stage.performer_ids.map((id) => { const employee = employees.find((item) => item.id === id); return <span key={id}>{employee?.short_name || employee?.full_name || `#${id}`}{!readOnly ? <button type="button" title="Убрать исполнителя" onClick={() => onStage(stage.stage_type, { performer_ids: stage.performer_ids.filter((item) => item !== id) })}><X size={12} /></button> : null}</span> })}</div>
              {stage.stage_type === 'electrophoresis' ? <label><span>Секвенатор</span><select value={stage.sequencer_name || ''} disabled={readOnly} onChange={(event) => onStage(stage.stage_type, { sequencer_name: event.target.value || null })}><option value="">—</option>{sequencers.map((item) => <option value={item.name} key={item.id}>{item.name}</option>)}</select></label> : null}
              <label><span>Комментарий</span><textarea rows={2} value={stage.comment || ''} disabled={readOnly} onChange={(event) => onStage(stage.stage_type, { comment: event.target.value || null })} /></label>
            </section>
          )
        })}
      </div>
      <div className="protocol-controls print-hide">
        <strong>Плашка</strong>
        <label><input type="checkbox" checked={plateRules.ladder_enabled} disabled={readOnly} onChange={(event) => onRules({ ladder_enabled: event.target.checked })} />Аллельные лестницы</label>
        <label><input type="checkbox" checked={plateRules.pc_enabled} disabled={readOnly} onChange={(event) => onRules({ pc_enabled: event.target.checked })} />PC</label>
        <label><input type="checkbox" checked={plateRules.nc_enabled} disabled={readOnly} onChange={(event) => onRules({ nc_enabled: event.target.checked })} />NC</label>
        <span>Заполнение: по колонкам</span>
      </div>
      {!preview ? <div className="protocol-sheet-empty">Выберите объекты, чтобы построить плашку.</div> : null}
      {sourcePlates.map((plate) => <ProtocolPlate key={`source-${plate.plate_index}`} plate={plate} title={sourcePlates.length > 1 ? `Исходная плашка ${plate.plate_index}` : 'Исходная плашка'} />)}
      {pcrPlates.map((plate) => <ProtocolPlate key={`pcr-${plate.plate_index}`} plate={plate} title={`PCR · плашка ${plate.plate_index}`} />)}
      {preview ? <ProtocolCalculations preview={preview} /> : null}
    </article>
  )
}

function display(value: unknown) {
  return value === null || value === undefined || value === '' ? '—' : String(value)
}

function ProtocolCalculations({ preview }: { preview: ProtocolPreview }) {
  const pcr = preview.calculations.pcr as Array<{ plate_index?: number; components?: Array<{ key: string; label: string; per_reaction: unknown; total: unknown }> }>
  const forez = preview.calculations.electrophoresis as { components?: Array<{ key: string; label: string; per_reaction: unknown; total: unknown }> }
  return (
    <div className="protocol-details-blocks">
      <details><summary>Расчёты</summary><div className="protocol-calculation-columns">
        <table><thead><tr><th>PCR</th><th>На реакцию</th><th>Всего</th></tr></thead><tbody>{pcr.flatMap((block) => (block.components || []).map((item) => <tr key={`${block.plate_index}-${item.key}`}><td>{pcr.length > 1 ? `${item.label} · ${block.plate_index}` : item.label}</td><td>{display(item.per_reaction)}</td><td>{display(item.total)}</td></tr>))}</tbody></table>
        <table><thead><tr><th>Форез</th><th>На реакцию</th><th>Всего</th></tr></thead><tbody>{(forez.components || []).map((item) => <tr key={item.key}><td>{item.label}</td><td>{display(item.per_reaction)}</td><td>{display(item.total)}</td></tr>)}</tbody></table>
      </div></details>
      {preview.dilutions.length ? <details><summary>Разведения</summary><div className="protocol-dilution-wrap"><table><thead><tr><th>Лунка</th><th>Объект</th><th>Исх. конц.</th><th>Кон. конц.</th><th>Фактор</th><th>I разведение</th><th>II разведение</th></tr></thead><tbody>{preview.dilutions.map((item) => { const steps = (item.steps || []) as Array<Record<string, unknown>>; return <tr key={String(item.object_id)}><td>{display(item.well)}</td><td>{display(item.display_name)}</td><td>{display(item.source_concentration)}</td><td>{display(item.target_concentration)}</td><td>{display(item.total_factor)}</td><td>{steps[0] ? `${display(steps[0].factor)} · ДНК ${display(steps[0].dna_volume)} / вода ${display(steps[0].water_volume)}` : '—'}</td><td>{steps[1] ? `${display(steps[1].factor)} · ДНК ${display(steps[1].dna_volume)} / вода ${display(steps[1].water_volume)}` : '—'}</td></tr> })}</tbody></table></div></details> : null}
    </div>
  )
}
