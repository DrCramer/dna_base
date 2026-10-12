import type { ProtocolDilutionSettings, ProtocolPipettingConstraints, ProtocolPreview } from '../../api/types'
import { useEffect, useState } from 'react'
import { formatProtocolValue, ProtocolDilutionAuditTable } from './ProtocolSupplementTables'

export const defaultProtocolDilution: ProtocolDilutionSettings = {
  enabled: true, target_concentration: 0.1, source_dna_volume: 3,
  dilution_one_volume: 10, threshold: 100, minimum_final_volume_enabled: false,
  minimum_final_volume: 15, source_available_volume: 50,
  optimize_water_volumes: false, allowed_concentration_error_percent: 5,
  preferred_water_step_ul: 10, optimization_priority: 'fewest_volumes', pipetting: {},
}

const instrumentFields: Array<[keyof ProtocolPipettingConstraints, string]> = [
  ['water_increment_ul', 'Дискретность H₂O, мкл'], ['water_min_ul', 'Минимум H₂O, мкл'], ['water_max_ul', 'Максимум H₂O, мкл'],
  ['dna_increment_ul', 'Дискретность ДНК, мкл'], ['dna_min_ul', 'Минимум ДНК, мкл'], ['dna_max_ul', 'Максимум ДНК, мкл'],
  ['first_dilution_reserve_ul', 'Резерв после I разведения, мкл'],
]

function number(value: number) {
  return new Intl.NumberFormat('ru-RU', { maximumFractionDigits: 2 }).format(value)
}

function SettingNumberInput({ value, disabled, required = false, positive = false, maximum, step = 'any', onValue }: {
  value: number | null | undefined
  disabled?: boolean
  required?: boolean
  positive?: boolean
  maximum?: number
  step?: string
  onValue: (value: number | null) => void
}) {
  const [text, setText] = useState(value === null || value === undefined ? '' : String(value))
  useEffect(() => setText(value === null || value === undefined ? '' : String(value)), [value])
  const valid = (input: string) => input === '' ? !required : Number.isFinite(Number(input)) && (positive ? Number(input) > 0 : Number(input) >= 0) && (maximum === undefined || Number(input) < maximum)
  return <input type="number" min="0" max={maximum === undefined ? undefined : maximum - 0.001} step={step} disabled={disabled} value={text} placeholder={required ? undefined : 'Не задано'} aria-invalid={!valid(text)} onChange={(event) => {
    const next = event.target.value
    setText(next)
    if (valid(next)) onValue(next === '' ? null : Number(next))
  }} onBlur={() => { if (!valid(text)) setText(value === null || value === undefined ? '' : String(value)) }} />
}

export function protocolDilutionTolerance(settings?: ProtocolDilutionSettings) {
  const symmetric = settings?.allowed_concentration_error_percent ?? 5
  if (settings?.max_under_target_pct === null || settings?.max_under_target_pct === undefined) {
    if (settings?.max_over_target_pct === null || settings?.max_over_target_pct === undefined) return `${number(symmetric)}%`
  }
  return `−${number(settings?.max_under_target_pct ?? symmetric)}% / +${number(settings?.max_over_target_pct ?? symmetric)}%`
}

export function ProtocolDilutionOptions({ settings, preview, readOnly, onChange }: {
  settings: ProtocolDilutionSettings
  preview: ProtocolPreview
  readOnly?: boolean
  onChange: (patch: Partial<ProtocolDilutionSettings>) => void
}) {
  const summary = preview.dilution_optimization
  if (!settings.optimize_water_volumes) return null
  return <div className="protocol-water-optimization">
    {summary?.enabled ? <div className="protocol-water-summary" role="status">
      <span>Вариантов объёма воды: <strong>{summary.unique_water_volumes_before} → {summary.unique_water_volumes_after}</strong></span>
      <span>Оптимизировано: <strong>{summary.optimized_object_count} из {summary.object_count} объектов</strong></span>
      <span>Максимальное отклонение: <strong>{number(summary.max_absolute_error_percent)}%</strong></span>
      {summary.blocked_object_count ? <span className="protocol-water-review">Требуют проверки: <strong>{summary.blocked_object_count}</strong></span> : null}
      <span>Без изменения: {summary.unchanged_object_count}</span>
    </div> : <div className="muted">Перерасчёт объёмов воды...</div>}
    <p className="protocol-lab-notice">Допуск {protocolDilutionTolerance(settings)} — настройка планирования, не лабораторный норматив. Допуск, диапазоны и дискретность дозаторов требуют утверждения лабораторией.</p>
    <details className="protocol-rounding-settings">
      <summary>Настройки округления</summary>
      <div className="protocol-rounding-fields">
        <label>Допуск концентрации, %<SettingNumberInput required maximum={100} step="0.5" disabled={readOnly} value={settings.allowed_concentration_error_percent ?? 5} onValue={(value) => { if (value !== null) onChange({ allowed_concentration_error_percent: value }) }} /></label>
        <label>Предпочтительный шаг воды, мкл<select disabled={readOnly} value={settings.preferred_water_step_ul ?? 10} onChange={(event) => onChange({ preferred_water_step_ul: Number(event.target.value) })}>{Array.from(new Set([1, 5, 10, settings.preferred_water_step_ul ?? 10])).sort((a, b) => a - b).map((step) => <option key={step} value={step}>{step}</option>)}</select></label>
        <label>Приоритет<select disabled={readOnly} value={settings.optimization_priority ?? 'fewest_volumes'} onChange={(event) => onChange({ optimization_priority: event.target.value as ProtocolDilutionSettings['optimization_priority'] })}><option value="fewest_volumes">Меньше перестановок дозатора</option><option value="minimum_error">Минимальное отклонение</option></select></label>
      </div>
      <details className="protocol-pipetting-settings"><summary>Ограничения дозирования</summary><div className="protocol-rounding-fields">
        {instrumentFields.map(([key, label]) => <label key={key}>{label}<SettingNumberInput positive={key !== 'first_dilution_reserve_ul' && key !== 'water_min_ul'} disabled={readOnly} value={settings.pipetting?.[key]} onValue={(value) => {
          onChange({ pipetting: { ...settings.pipetting, [key]: key === 'first_dilution_reserve_ul' ? value ?? 0 : value } })
        }} /></label>)}
      </div></details>
    </details>
    {summary?.enabled ? <>
      <details className="protocol-water-batches"><summary>Группы объёмов воды</summary><div className="protocol-water-stage-groups">
        {([['I разведение', summary.batch_groups_first], ['II разведение', summary.batch_groups_second]] as const).map(([title, groups]) => <section key={title}><h4>{title}</h4>{groups.length ? groups.map((group) => <details key={group.water_volume}>
          <summary>{number(group.water_volume)} мкл — {group.object_count} объектов{group.objects.some((item) => item.needs_review) ? ' · есть требующие проверки' : ''}</summary>
          <table><thead><tr><th>Плашка</th><th>Лунка</th><th>Объект</th><th /></tr></thead><tbody>{group.objects.map((item) => <tr key={`${item.object_id}-${item.plate_index}-${item.well}`}><td>{formatProtocolValue(item.plate_index)}</td><td>{formatProtocolValue(item.well)}</td><td>{formatProtocolValue(item.display_name)}</td><td>{item.needs_review ? 'Требует проверки' : ''}</td></tr>)}</tbody></table>
        </details>) : <span className="muted">Нет выполняемых шагов</span>}</section>)}
      </div></details>
      <details><summary>Подробности округления</summary><ProtocolDilutionAuditTable rows={preview.dilutions} /></details>
    </> : null}
  </div>
}
