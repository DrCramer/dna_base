import { ArrowDown, ArrowUp, ArrowUpDown } from 'lucide-react'
import type { ProtocolPreview } from '../../api/types'

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
  steps?: Array<{ dna_volume?: number | null; water_volume?: number | null }>
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
    ? normalized.filter((row) => row.available === false || (row.steps?.length || 0) > 0)
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
            <th rowSpan={2}>Плашка</th><th rowSpan={2}>Лунка</th><th rowSpan={2}>Объект</th><th rowSpan={2}>Исх. конц.</th><th rowSpan={2}>Кон. конц.</th><th rowSpan={2}>Фактор</th>
            <th colSpan={2}>I разведение <SortButton active={view.sortKey === 'first'} direction={view.directions.first} onClick={() => onSort?.('first')} /></th>
            <th colSpan={2}>II разведение <SortButton active={view.sortKey === 'second'} direction={view.directions.second} onClick={() => onSort?.('second')} /></th>
          </tr>
          <tr><th>ДНК</th><th>H₂O</th><th>ДНК</th><th>H₂O</th></tr>
        </thead>
        <tbody>{shown.map((item) => <tr key={item.object_id}>
          <td>{formatProtocolValue(item.plate_index)}</td><td>{formatProtocolValue(item.well)}</td><td>{formatProtocolValue(item.display_name)}</td>
          <td>{formatProtocolValue(item.source_concentration)}</td><td>{formatProtocolValue(item.target_concentration)}</td><td>{formatProtocolValue(item.total_factor)}</td>
          <td>{formatProtocolValue(item.steps?.[0]?.dna_volume)}</td><td>{formatProtocolValue(item.steps?.[0]?.water_volume)}</td>
          <td>{formatProtocolValue(item.steps?.[1]?.dna_volume)}</td><td>{formatProtocolValue(item.steps?.[1]?.water_volume)}</td>
        </tr>)}</tbody>
      </table></div> : <div className="protocol-supplement-empty">Нет строк для отображения.</div>}
    </section>
  )
}

export function ProtocolCalculationTables({ preview }: { preview: ProtocolPreview }) {
  const pcr = protocolReagentRows(preview, 'pcr')
  const forez = protocolReagentRows(preview, 'electrophoresis')
  return <div className="protocol-calculation-columns">
    <table><thead><tr><th colSpan={3}>Протокол PCR</th></tr><tr><th>Компонент</th><th>На реакцию</th><th>Всего</th></tr></thead><tbody>{pcr.map((item) => <tr key={item.key}><td>{item.label}</td><td>{formatProtocolValue(item.per_reaction)}</td><td>{formatProtocolValue(item.total)}</td></tr>)}</tbody></table>
    <table><thead><tr><th colSpan={3}>Протокол ЭФ</th></tr><tr><th>Компонент</th><th>На реакцию</th><th>Всего</th></tr></thead><tbody>{forez.map((item) => <tr key={item.key}><td>{item.label}</td><td>{formatProtocolValue(item.per_reaction)}</td><td>{formatProtocolValue(item.total)}</td></tr>)}</tbody></table>
  </div>
}
