import { useLayoutEffect, useMemo, useState } from 'react'
import type { Employee, ProtocolDilutionSettings, ProtocolPlateRules, ProtocolPreview, ProtocolStageSettings, ProtocolStageType } from '../../api/types'
import { ProtocolPlate } from './ProtocolPlate'
import { protocolObjectIds } from './protocolSelection'
import { protocolDilutionTolerance } from './ProtocolDilutionOptions'
import { ProtocolDilutionPrintPages } from './ProtocolDilutionPrintPages'
import {
  ProtocolCalculationTables,
  protocolReagentRows,
  visibleDilutions,
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
  includeDilutions: boolean
  plateRules: ProtocolPlateRules
  preview: ProtocolPreview
  employees: Employee[]
  dilutionView: DilutionView
  onPageCountChange: (count: number) => void
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

export function ProtocolPrintDocument({ protocolDate, protocolNo, name, stages, selectedStageTypes, includeDilutions, plateRules, preview, employees, dilutionView, onPageCountChange }: Props) {
  const objectCount = protocolObjectIds(preview.objects).length
  const orderedStageTypes = (Object.keys(stageLabels) as ProtocolStageType[]).filter((stageType) => selectedStageTypes.includes(stageType))
  const pages = orderedStageTypes.flatMap((stageType) => {
    const layout = stageType === 'pcr' || stageType === 'electrophoresis' ? preview.layouts.pcr : preview.layouts.source
    return layout.plates.map((plate) => ({ stageType, layout, plate }))
  })
  const dilutions = useMemo(() => includeDilutions ? visibleDilutions(preview.dilutions, dilutionView) : [], [includeDilutions, preview.dilutions, dilutionView])
  const [dilutionPageCount, setDilutionPageCount] = useState(0)
  const savedDilutionSettings = preview.snapshot.dilution_settings as ProtocolDilutionSettings | undefined
  const hasCalculations = selectedStageTypes.some((stage) => (stage === 'pcr' || stage === 'electrophoresis') && protocolReagentRows(preview, stage).length > 0)
  useLayoutEffect(() => {
    onPageCountChange(pages.length + dilutionPageCount + Number(hasCalculations))
  }, [pages.length, dilutionPageCount, hasCalculations, onPageCountChange])
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
      <ProtocolDilutionPrintPages rows={dilutions} protocolDate={displayDate(protocolDate)} protocolNo={protocolNo} name={name} view={dilutionView} precedingPageCount={pages.length} onPageCountChange={setDilutionPageCount} note={preview.dilution_optimization?.enabled ? `Удобные объёмы воды · допуск: ${protocolDilutionTolerance(savedDilutionSettings)}. Отмеченные строки требуют решения сотрудника.` : null} />
      {hasCalculations ? <div className="protocol-print-page-shell" key="calculations">
        <div className="protocol-print-page-label">Страница {pages.length + dilutionPageCount + 1} · Расчёты</div>
        <article className="protocol-print-page protocol-print-data-page">
          <h1>Расчёты · {name || 'Протокол'}</h1>
          <div className="protocol-print-meta"><div><span>Дата</span><strong>{displayDate(protocolDate)}</strong></div><div><span>№</span><strong>{protocolNo}</strong></div><div className="protocol-print-name"><span>Название</span><strong>{name || '—'}</strong></div><div><span>Объектов</span><strong>{objectCount}</strong></div></div>
          <ProtocolCalculationTables preview={preview} selectedStageTypes={selectedStageTypes} />
        </article>
      </div> : null}
    </div>
  )
}

export function protocolPrintPageCount(preview: ProtocolPreview, selectedStageTypes: ProtocolStageType[], dilutionView: DilutionView, includeDilutions: boolean, measuredDilutionPageCount = 1) {
  const plates = selectedStageTypes.reduce((total, stageType) => total + (stageType === 'pcr' || stageType === 'electrophoresis' ? preview.layouts.pcr.plates.length : preview.layouts.source.plates.length), 0)
  const dilutionPages = includeDilutions && visibleDilutions(preview.dilutions, dilutionView).length ? measuredDilutionPageCount : 0
  const calculations = selectedStageTypes.some((stage) => (stage === 'pcr' || stage === 'electrophoresis') && protocolReagentRows(preview, stage).length > 0) ? 1 : 0
  return plates + dilutionPages + calculations
}
