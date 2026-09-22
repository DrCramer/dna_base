import type { ProtocolPlate as Plate } from '../../api/types'

const rows = 'ABCDEFGH'.split('')
const columns = Array.from({ length: 12 }, (_, index) => index + 1)

export function ProtocolPlate({ plate, title }: { plate: Plate; title: string }) {
  const cells = new Map(plate.wells.map((item) => [item.well, item]))
  return (
    <div className="protocol-plate-block">
      <div className="protocol-plate-title"><strong>{title}</strong><span>{plate.sample_count} объектов</span></div>
      <div className="protocol-plate-grid" role="grid" aria-label={title}>
        <div className="protocol-well-axis" />
        {columns.map((column) => <div className="protocol-well-axis" key={column}>{column}</div>)}
        {rows.flatMap((row) => [
          <div className="protocol-well-axis" key={`${row}-axis`}>{row}</div>,
          ...columns.map((column) => {
            const well = cells.get(`${row}${column}`)
            const snapshot = well?.object_snapshot || {}
            const tooltip = [well?.well, well?.display_name, snapshot.party_no ? `Партия ${snapshot.party_no}` : null, snapshot.object_type].filter(Boolean).join('\n')
            return (
              <div
                role="gridcell"
                key={`${row}${column}`}
                className={`protocol-well protocol-well-${well?.kind || 'empty'}`}
                title={tooltip}
              >
                <span>{well?.display_name || ''}</span>
              </div>
            )
          })
        ])}
      </div>
    </div>
  )
}
