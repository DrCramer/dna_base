import { AlertTriangle, ArrowDown, ArrowUp, ArrowUpDown } from 'lucide-react'
import type { ProtocolDilutionOptimization, ProtocolPreview } from '../../api/types'

export type DilutionSortKey = 'first' | 'second' | null
export type DilutionSortDirection = 'asc' | 'desc'

export interface DilutionView {
  hideNoDilution: boolean
  sortKey: DilutionSortKey
  directions: { first: DilutionSortDirection; second: DilutionSortDirection }
}

export interface DilutionRow {
  object_id: number
  display_name?: string | null
  plate_index?: number | null
  well?: string | null
  source_concentration?: number | null
  target_concentration?: number | null
  total_factor?: number | null
  available?: boolean
  minimum_volume_available?: boolean
  minimum_volume_warning?: string | null
  steps?: Array<{ dna_volume?: number | null; water_volume?: number | null }>
  baseline_steps?: Array<{ dna_volume?: number | null; water_volume?: number | null }>
  optimization?: ProtocolDilutionOptimization | null
}

export const dilutionPageSize = 24

export function visibleDilutions(rows: Array<Record<string, unknown> | DilutionRow>, view: DilutionView): DilutionRow[] {
  const normalized = rows.map((row) => {
    const source = row as Record<string, unknown>
    const legacyWell = typeof source.well === 'string' ? source.well.match(/^(\d+):(.*)$/) : null
    return {
      ...source,
      plate_index: typeof source.plate_index === 'number' ? source.plate_index : legacyWell ? Number(legacyWell[1]) : null,
      well: legacyWell ? legacyWell[2] : typeof source.well === 'string' ? source.well : null,
      steps: Array.isArray(source.steps) ? source.steps as DilutionRow['steps'] : [],
    } as DilutionRow
  })
  const filtered = view.hideNoDilution
    ? normalized.filter((row) => (row.steps?.length || 0) > 0)
    : normalized
  if (!view.sortKey) return filtered
  const stepIndex = view.sortKey === 'first' ? 0 : 1
  const direction = view.directions[view.sortKey] === 'asc' ? 1 : -1
  return filtered
    .map((row, index) => ({ row, index }))
    .sort((left, right) => {
      const leftValue = left.row.steps?.[stepIndex]?.water_volume
      const rightValue = right.row.steps?.[stepIndex]?.water_volume
      const leftMissing = typeof leftValue !== 'number'
      const rightMissing = typeof rightValue !== 'number'
      if (leftMissing !== rightMissing) return leftMissing ? 1 : -1
      if (leftMissing) return left.index - right.index
      return ((leftValue as number) - (rightValue as number)) * direction || left.index - right.index
    })
    .map(({ row }) => row)
}

export function dilutionSupplementPageCount(rows: Array<Record<string, unknown> | DilutionRow>, view: DilutionView) {
  return Math.ceil(visibleDilutions(rows, view).length / dilutionPageSize)
}

export function formatProtocolValue(value: unknown) {
  return value === null || value === undefined || value === '' ? '—' : String(value)
}

export function formatDilutionVolume(value: unknown) {
  return typeof value === 'number'
    ? new Intl.NumberFormat('ru-RU', { maximumFractionDigits: 3 }).format(value)
    : formatProtocolValue(value)
}

export function dilutionWaterTooltip(row: DilutionRow, index: number) {
  const optimization = row.optimization
  if (!optimization?.enabled || row.steps?.[index]?.water_volume === undefined) return undefined
  return [
    `До округления: ${formatDilutionVolume(row.baseline_steps?.[index]?.water_volume)} мкл`,
    `Для работы: ${formatDilutionVolume(row.steps?.[index]?.water_volume)} мкл`,
    `Расчётная концентрация: ${new Intl.NumberFormat('ru-RU', { maximumSignificantDigits: 6 }).format(optimization.actual_final_concentration)} нг/мкл`,
    `Отклонение от цели: ${formatDilutionVolume(optimization.relative_error_percent)}%`,
    optimization.reason,
  ].filter(Boolean).join('\n')
}

type Reagent = { key: string; label: string; per_reaction: unknown; total: unknown }

export function protocolReagentRows(preview: ProtocolPreview, stage: 'pcr' | 'electrophoresis'): Reagent[] {
  const calculations = preview.calculations as ProtocolPreview['calculations'] & { pcr_total?: Record<string, unknown> }
  const section = stage === 'pcr'
    ? calculations.pcr_total as { components?: Reagent[] } | undefined
      || aggregateLegacyPcr(calculations.pcr)
    : calculations.electrophoresis as { components?: Reagent[] }
  return (section.components || []).filter((item) => item.per_reaction !== null && item.per_reaction !== undefined && item.total !== null && item.total !== undefined)
}

function aggregateLegacyPcr(blocks: Array<Record<string, unknown>>) {
  const components = new Map<string, Reagent>()
  blocks.forEach((block) => {
    const items = Array.isArray(block.components) ? block.components as Reagent[] : []
    items.forEach((item) => {
      const current = components.get(item.key)
      const total = typeof item.total === 'number' ? item.total : null
      components.set(item.key, {
        ...item,
        total: total === null ? current?.total ?? null : (typeof current?.total === 'number' ? current.total : 0) + total,
      })
    })
  })
  return { components: Array.from(components.values()) }
}

function SortButton({ active, direction, onClick }: { active: boolean; direction: DilutionSortDirection; onClick: () => void }) {
  const Icon = active ? direction === 'asc' ? ArrowUp : ArrowDown : ArrowUpDown
  return <button type="button" className="protocol-dilution-sort print-hide" title={`Сортировать ${direction === 'asc' ? 'по возрастанию' : 'по убыванию'} по H₂O`} aria-label={`Сортировка ${direction === 'asc' ? 'по возрастанию' : 'по убыванию'}`} onClick={onClick}><Icon size={14} /></button>
}

export function ProtocolDilutionsTable({ rows, view, onHideNoDilution, onSort, print = false }: {
  rows: Array<Record<string, unknown> | DilutionRow>
  view: DilutionView
  onHideNoDilution?: (value: boolean) => void
  onSort?: (key: Exclude<DilutionSortKey, null>) => void
  print?: boolean
}) {
  const shown = visibleDilutions(rows, view)
  return (
    <section className={`protocol-dilution-section${print ? ' is-print' : ''}`}>
      {print ? <h2>Разведения</h2> : onHideNoDilution ? <div className="protocol-dilution-heading"><label><input type="checkbox" checked={view.hideNoDilution} onChange={(event) => onHideNoDilution(event.target.checked)} />Скрыть объекты без разведения</label></div> : null}
      {shown.length ? <div className="protocol-dilution-wrap"><table>
        <thead>
          <tr>
            <th className="protocol-dilution-col-plate" rowSpan={2}>Плашка</th><th className="protocol-dilution-col-well" rowSpan={2}>Лунка</th><th rowSpan={2}>Объект</th><th rowSpan={2}>Исх. конц.</th><th rowSpan={2}>Кон. конц.</th><th rowSpan={2}>Фактор</th>
            <th colSpan={2}>I разведение <SortButton active={view.sortKey === 'first'} direction={view.directions.first} onClick={() => onSort?.('first')} /></th>
            <th colSpan={2}>II разведение <SortButton active={view.sortKey === 'second'} direction={view.directions.second} onClick={() => onSort?.('second')} /></th>
          </tr>
          <tr><th>ДНК</th><th>H₂O</th><th>ДНК</th><th>H₂O</th></tr>
        </thead>
        <tbody>{shown.map((item) => <tr key={item.object_id}>
          <td className="protocol-dilution-col-plate">{formatProtocolValue(item.plate_index)}</td><td className="protocol-dilution-col-well">{formatProtocolValue(item.well)}</td><td>{formatProtocolValue(item.display_name)}{item.minimum_volume_available === false && item.minimum_volume_warning ? <span className="protocol-dilution-warning" role="img" aria-label={item.minimum_volume_warning} title={item.minimum_volume_warning}><AlertTriangle size={14} aria-hidden="true" /></span> : null}{item.optimization?.needs_review ? <span className="protocol-dilution-warning" title={item.optimization.reason || 'Требует проверки'}><AlertTriangle size={14} aria-hidden="true" /><span className="protocol-dilution-review-label">Требует проверки</span></span> : null}</td>
          <td>{formatProtocolValue(item.source_concentration)}</td><td>{formatProtocolValue(item.target_concentration)}</td><td>{formatProtocolValue(item.total_factor)}</td>
          <td>{formatDilutionVolume(item.steps?.[0]?.dna_volume)}</td><td title={dilutionWaterTooltip(item, 0)} className={item.optimization?.status === 'optimized' ? 'protocol-water-optimized' : undefined}>{formatDilutionVolume(item.steps?.[0]?.water_volume)}</td>
          <td>{formatDilutionVolume(item.steps?.[1]?.dna_volume)}</td><td title={dilutionWaterTooltip(item, 1)} className={item.optimization?.status === 'optimized' ? 'protocol-water-optimized' : undefined}>{formatDilutionVolume(item.steps?.[1]?.water_volume)}</td>
        </tr>)}</tbody>
      </table></div> : <div className="protocol-supplement-empty">Нет строк для отображения.</div>}
    </section>
  )
}

export function ProtocolDilutionAuditTable({ rows }: { rows: Array<Record<string, unknown> | DilutionRow> }) {
  const shown = visibleDilutions(rows, { hideNoDilution: false, sortKey: null, directions: { first: 'asc', second: 'asc' } }).filter((row) => row.optimization?.enabled)
  const reasons: Record<string, string> = { source_volume_limit: 'Лимит исходной ДНК', dna_not_measurable: 'Диапазон или шаг ДНК', water_not_measurable: 'Диапазон или шаг H₂O', minimum_volume_limit: 'Минимальный объём смеси', insufficient_first_dilution: 'Не хватает продукта I этапа', baseline_out_of_tolerance: 'Концентрация вне допуска' }
  return <div className="protocol-dilution-audit"><table><thead><tr><th>Плашка</th><th>Лунка</th><th>Объект</th><th>H₂O I до / после</th><th>H₂O II до / после</th><th>Факт., нг/мкл</th><th>Ошибка, %</th><th>Статус</th></tr></thead><tbody>{shown.map((row) => <tr key={`${row.object_id}-${row.plate_index}-${row.well}`}>
    <td>{formatProtocolValue(row.plate_index)}</td><td>{formatProtocolValue(row.well)}</td><td>{formatProtocolValue(row.display_name)}</td>
    <td>{formatDilutionVolume(row.baseline_steps?.[0]?.water_volume)} / {formatDilutionVolume(row.steps?.[0]?.water_volume)}</td>
    <td>{formatDilutionVolume(row.baseline_steps?.[1]?.water_volume)} / {formatDilutionVolume(row.steps?.[1]?.water_volume)}</td>
    <td>{new Intl.NumberFormat('ru-RU', { maximumSignificantDigits: 6 }).format(row.optimization!.actual_final_concentration)}</td><td>{formatDilutionVolume(row.optimization?.relative_error_percent)}</td>
    <td title={row.optimization?.reason || undefined}>{row.optimization?.status === 'blocked' ? `Требует проверки: ${reasons[row.optimization.reason_code || ''] || 'нет допустимого варианта'}` : row.optimization?.status === 'optimized' ? 'Оптимизировано' : 'Исходный расчёт'}</td>
  </tr>)}</tbody></table></div>
}

export function ProtocolCalculationTables({ preview }: { preview: ProtocolPreview }) {
  const pcr = protocolReagentRows(preview, 'pcr')
  const forez = protocolReagentRows(preview, 'electrophoresis')
  return <div className="protocol-calculation-columns">
    <table><thead><tr><th colSpan={3}>Протокол PCR</th></tr><tr><th>Компонент</th><th>На реакцию</th><th>Всего</th></tr></thead><tbody>{pcr.map((item) => <tr key={item.key}><td>{item.label}</td><td>{formatProtocolValue(item.per_reaction)}</td><td>{formatProtocolValue(item.total)}</td></tr>)}</tbody></table>
    <table><thead><tr><th colSpan={3}>Протокол ЭФ</th></tr><tr><th>Компонент</th><th>На реакцию</th><th>Всего</th></tr></thead><tbody>{forez.map((item) => <tr key={item.key}><td>{item.label}</td><td>{formatProtocolValue(item.per_reaction)}</td><td>{formatProtocolValue(item.total)}</td></tr>)}</tbody></table>
  </div>
}
