import type { Employee, ProtocolPlateRules, ProtocolPreview, ProtocolStageSettings, ProtocolStageType } from '../../api/types'
import { ProtocolPlate } from './ProtocolPlate'
import { protocolObjectIds } from './protocolSelection'
import {
  dilutionPageSize,
  dilutionSupplementPageCount,
  ProtocolCalculationTables,
  ProtocolDilutionsTable,
  protocolReagentRows,
  visibleDilutions,
  type DilutionSortKey,
  type DilutionView,
} from './ProtocolSupplementTables'

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
  dilutionView: DilutionView
  onDilutionSort: (key: Exclude<DilutionSortKey, null>) => void
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

export function ProtocolPrintDocument({ protocolDate, protocolNo, name, stages, selectedStageTypes, plateRules, preview, employees, dilutionView, onDilutionSort }: Props) {
  const objectCount = protocolObjectIds(preview.objects).length
  const orderedStageTypes = (Object.keys(stageLabels) as ProtocolStageType[]).filter((stageType) => selectedStageTypes.includes(stageType))
  const pages = orderedStageTypes.flatMap((stageType) => {
    const layout = stageType === 'pcr' || stageType === 'electrophoresis' ? preview.layouts.pcr : preview.layouts.source
    return layout.plates.map((plate) => ({ stageType, layout, plate }))
  })
  const dilutions = visibleDilutions(preview.dilutions, dilutionView)
  const dilutionPages = Array.from({ length: Math.ceil(dilutions.length / dilutionPageSize) }, (_, index) => dilutions.slice(index * dilutionPageSize, (index + 1) * dilutionPageSize))
  const hasCalculations = protocolReagentRows(preview, 'pcr').length > 0 || protocolReagentRows(preview, 'electrophoresis').length > 0
  return (
    <div className="protocol-print-pages">
      {pages.map(({ stageType, plate }, pageIndex) => {
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
                <div><span>Объектов</span><strong>{objectCount}</strong></div>
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
      {dilutionPages.map((rows, index) => {
        return <div className="protocol-print-page-shell" key={`dilutions-${index}`}>
          <div className="protocol-print-page-label">Страница {pages.length + index + 1} · Разведения · лист {index + 1}</div>
          <article className="protocol-print-page protocol-print-data-page">
            <h1>Разведения · {name || 'Протокол'}</h1>
            <div className="protocol-print-meta"><div><span>Дата</span><strong>{displayDate(protocolDate)}</strong></div><div><span>№</span><strong>{protocolNo}</strong></div><div className="protocol-print-name"><span>Название</span><strong>{name || '—'}</strong></div><div><span>Строк</span><strong>{rows.length}</strong></div></div>
            <ProtocolDilutionsTable rows={rows} view={{ ...dilutionView, hideNoDilution: false }} onSort={onDilutionSort} print />
          </article>
        </div>
      })}
      {hasCalculations ? <div className="protocol-print-page-shell" key="calculations">
        <div className="protocol-print-page-label">Страница {pages.length + dilutionPages.length + 1} · Расчёты</div>
        <article className="protocol-print-page protocol-print-data-page">
          <h1>Расчёты · {name || 'Протокол'}</h1>
          <div className="protocol-print-meta"><div><span>Дата</span><strong>{displayDate(protocolDate)}</strong></div><div><span>№</span><strong>{protocolNo}</strong></div><div className="protocol-print-name"><span>Название</span><strong>{name || '—'}</strong></div><div><span>Объектов</span><strong>{objectCount}</strong></div></div>
          <ProtocolCalculationTables preview={preview} />
        </article>
      </div> : null}
    </div>
  )
}

export function protocolPrintPageCount(preview: ProtocolPreview, selectedStageTypes: ProtocolStageType[], dilutionView: DilutionView) {
  const plates = selectedStageTypes.reduce((total, stageType) => total + (stageType === 'pcr' || stageType === 'electrophoresis' ? preview.layouts.pcr.plates.length : preview.layouts.source.plates.length), 0)
  const dilutionPages = dilutionSupplementPageCount(preview.dilutions, dilutionView)
  const calculations = protocolReagentRows(preview, 'pcr').length || protocolReagentRows(preview, 'electrophoresis').length ? 1 : 0
  return plates + dilutionPages + calculations
}
