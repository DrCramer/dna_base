import type { Employee, ProtocolPlateRules, ProtocolPreview, ProtocolStageSettings, ProtocolStageType } from '../../api/types'
import { ProtocolPlate } from './ProtocolPlate'

const stageLabels: Record<ProtocolStageType, string> = {
  dna_extraction: 'Выделение',
  realtime: 'RT',
  pcr: 'PCR',
  electrophoresis: 'Форез'
}

interface Props {
  protocolDate: string
  protocolNo: number
  name: string
  stages: ProtocolStageSettings[]
  selectedStageTypes: ProtocolStageType[]
  plateRules: ProtocolPlateRules
  preview: ProtocolPreview
  employees: Employee[]
}

function displayDate(value: string | null | undefined) {
  if (!value) return '—'
  const [year, month, day] = value.split('-')
  return year && month && day ? `${day}.${month}.${year}` : value
}

function snapshotPerformers(preview: ProtocolPreview, stageType: ProtocolStageType) {
  const stage = preview.stages.find((item) => item.stage_type === stageType)
  if (!stage || !Array.isArray(stage.performers)) return []
  return stage.performers.flatMap((item) => {
    if (!item || typeof item !== 'object') return []
    const performer = item as Record<string, unknown>
    return typeof performer.display_name === 'string' && performer.display_name ? [performer.display_name] : []
  })
}

export function ProtocolPrintDocument({ protocolDate, protocolNo, name, stages, selectedStageTypes, plateRules, preview, employees }: Props) {
  const orderedStageTypes = (Object.keys(stageLabels) as ProtocolStageType[]).filter((stageType) => selectedStageTypes.includes(stageType))
  const pages = orderedStageTypes.flatMap((stageType) => {
    const layout = stageType === 'pcr' ? preview.layouts.pcr : preview.layouts.source
    return layout.plates.map((plate) => ({ stageType, layout, plate }))
  })

  return (
    <div className="protocol-print-pages">
      {pages.map(({ stageType, layout, plate }, pageIndex) => {
        const stage = stages.find((item) => item.stage_type === stageType)
        const savedNames = snapshotPerformers(preview, stageType)
        const currentNames = (stage?.performer_ids || []).flatMap((id) => {
          const employee = employees.find((item) => item.id === id)
          return employee ? [employee.short_name || employee.full_name] : []
        })
        const performerNames = currentNames.length ? currentNames : savedNames
        const controls = new Set(plate.wells.map((well) => well.kind))
        return (
          <div className="protocol-print-page-shell" key={`${stageType}-${plate.plate_index}`}>
            <div className="protocol-print-page-label">Страница {pageIndex + 1} · {stageLabels[stageType]} · плашка {plate.plate_index}</div>
            <article className="protocol-print-page">
              <h1>ЕДИНЫЙ ПРОТОКОЛ ПЛАШКИ: ВЫДЕЛЕНИЕ / RT / PCR / ФОРЕЗ</h1>
              <div className="protocol-print-meta">
                <div><span>Дата</span><strong>{displayDate(protocolDate)}</strong></div>
                <div><span>№</span><strong>{protocolNo}</strong></div>
                <div className="protocol-print-name"><span>Название</span><strong>{name || '—'}</strong></div>
                <div><span>Объектов / максимум</span><strong>{plate.sample_count} / {layout.capacity}</strong></div>
              </div>
              <section className="protocol-print-stage">
                <h2>{stageLabels[stageType]}</h2>
                <div><span>Дата</span><strong>{displayDate(stage?.work_date)}</strong></div>
                <div><span>Набор</span><strong>{stage?.kit_name || '—'}</strong></div>
                <div><span>Исполнители</span><strong>{performerNames.join(', ') || '—'}</strong></div>
                {stageType === 'electrophoresis' ? <div><span>Секвенатор</span><strong>{stage?.sequencer_name || '—'}</strong></div> : null}
                <div className="protocol-print-comment"><span>Комментарий</span><strong>{stage?.comment || '—'}</strong></div>
              </section>
              <div className="protocol-print-controls">
                <span>Заполнение: по колонкам</span>
                <span>Лестницы: {controls.has('ladder') ? 'да' : 'нет'}</span>
                <span>PC: {controls.has('pc') ? 'да' : 'нет'}</span>
                <span>NC: {controls.has('nc') ? 'да' : 'нет'}</span>
                <span>Профиль: {plateRules.rows} × {plateRules.columns}</span>
              </div>
              <ProtocolPlate plate={plate} title={`${stageLabels[stageType]} · плашка ${plate.plate_index}`} />
            </article>
          </div>
        )
      })}
    </div>
  )
}
