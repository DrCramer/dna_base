import { useQuery } from '@tanstack/react-query'
import { useMemo, useState } from 'react'
import { api } from '../api/client'
import type { DashboardPartyProgress } from '../api/types'
import { LoadingState, PageHeader } from '../components/ui'

const stageColumns = [
  ['sample_prep', 'Пробоподготовка'],
  ['milling', 'Измельчение'],
  ['dna_extraction', 'Выделение'],
  ['realtime', 'RealTime'],
  ['pcr', 'ПЦР'],
  ['electrophoresis', 'Электрофорез'],
  ['analysis', 'Анализ']
] as const

const controlColumns = [
  ['control_actual_decrees', 'Фактическое количество постановлений'],
  ['control_decree_without_object', 'Есть постановление, но нет объекта'],
  ['control_object_without_decree', 'Есть объект, но нет постановления'],
  ['control_unidentified_rostov_no', 'Неидентифицируемый ростовский номер'],
  ['control_need_recall', 'Надо отозвать'],
  ['control_recalled', 'Отозваны']
] as const

function controlValue(value: string | null | undefined) {
  const normalized = String(value || '').trim()
  return normalized || '—'
}

function hasControlValues(party: DashboardPartyProgress) {
  return controlColumns.some(([key]) => controlValue(party[key]) !== '—')
}

function hasCriticalControl(party: DashboardPartyProgress) {
  return controlValue(party.control_need_recall) !== '—' || controlValue(party.control_recalled) !== '—'
}

function hasStageLag(party: DashboardPartyProgress) {
  if (!party.object_count) return false
  return stageColumns.some(([key]) => (party.stage_counts[key] ?? 0) < party.object_count)
}

function stagePercent(party: DashboardPartyProgress, key: string) {
  const done = party.stage_counts[key] ?? 0
  return party.object_count ? Math.round((done / party.object_count) * 100) : 0
}

function laggingStageKeys(party: DashboardPartyProgress) {
  if (!party.object_count) return new Set<string>()
  const percents = stageColumns.map(([key]) => [key, stagePercent(party, key)] as const)
  const incomplete = percents.filter(([, percent]) => percent < 100)
  if (!incomplete.length) return new Set<string>()
  const min = Math.min(...incomplete.map(([, percent]) => percent))
  return new Set(incomplete.filter(([, percent]) => percent === min).map(([key]) => key))
}

export function DashboardPage({
  onPartyOpen,
  onReportsOpen
}: {
  onPartyOpen: (partyNo: string) => void
  onReportsOpen?: (tab?: string) => void
}) {
  const { data, isLoading } = useQuery({ queryKey: ['dashboard'], queryFn: api.dashboard })
  const [onlyWithObjects, setOnlyWithObjects] = useState(false)
  const [onlyProblematic, setOnlyProblematic] = useState(false)
  const [onlyCurrentYear, setOnlyCurrentYear] = useState(false)
  const [onlyCriticalControl, setOnlyCriticalControl] = useState(false)
  const currentYear = Math.max(...(data?.active_party_progress ?? []).map((party) => party.case_year || 0), 0) || null
  const activeParties = useMemo(() => {
    let rows = data?.active_party_progress ?? []
    if (onlyWithObjects) rows = rows.filter((party) => party.object_count > 0)
    if (onlyProblematic) rows = rows.filter((party) => hasStageLag(party) || hasControlValues(party))
    if (onlyCurrentYear && currentYear) rows = rows.filter((party) => party.case_year === currentYear)
    return rows
  }, [currentYear, data?.active_party_progress, onlyCurrentYear, onlyProblematic, onlyWithObjects])
  const partiesWithControl = useMemo(() => {
    let rows = (data?.control_party_progress ?? data?.active_party_progress ?? []).filter(hasControlValues)
    if (onlyCurrentYear && currentYear) rows = rows.filter((party) => party.case_year === currentYear)
    if (onlyCriticalControl) rows = rows.filter(hasCriticalControl)
    return rows
  }, [currentYear, data?.active_party_progress, data?.control_party_progress, onlyCriticalControl, onlyCurrentYear])
  const problemParties = partiesWithControl.length
  const withoutAnalysis = Math.max(0, (data?.active_objects ?? data?.total_objects ?? 0) - (data?.stage_summary?.analysis ?? 0))
  const withoutPcr = Math.max(0, (data?.active_objects ?? data?.total_objects ?? 0) - (data?.stage_summary?.pcr ?? 0))
  if (isLoading) return <div className="page"><LoadingState title="Загрузка главной..." /></div>
  return (
    <div className="page">
      <PageHeader
        title="Главная"
        description="Оперативная сводка по активным партиям, готовности этапов и контрольным замечаниям."
      />

      <div className="metrics dashboard-kpi">
        <div><span>Всего объектов</span><strong>{data?.total_objects ?? 0}</strong></div>
        <div><span>Активных партий</span><strong>{data?.active_parties ?? 0}</strong></div>
        <div><span>Проблемных партий</span><strong>{problemParties}</strong></div>
        <div><span>Без анализа</span><strong>{withoutAnalysis}</strong></div>
        <div><span>Без ПЦР</span><strong>{withoutPcr}</strong></div>
        <div><span>С контрольными замечаниями</span><strong>{partiesWithControl.length}</strong></div>
      </div>

      <section className="section">
        <div className="section-head">
          <div>
            <h2>Активные партии</h2>
            <p className="muted-note">Показаны последние 15 активных партий. Всего объектов: {data?.total_objects ?? 0}</p>
          </div>
          <div className="dashboard-filter-row" aria-label="Фильтры главной">
            <button className={onlyWithObjects ? 'active' : ''} onClick={() => setOnlyWithObjects((value) => !value)}>С объектами</button>
            <button className={onlyProblematic ? 'active' : ''} onClick={() => setOnlyProblematic((value) => !value)}>Проблемные</button>
            <button className={onlyCurrentYear ? 'active' : ''} onClick={() => setOnlyCurrentYear((value) => !value)} disabled={!currentYear}>Год {currentYear || '—'}</button>
          </div>
        </div>
        <div className="dashboard-party-table-wrap">
          <div className="dashboard-party-table" role="table" aria-label="Активные партии">
            <div className="dashboard-party-row dashboard-party-head" role="row">
              <div role="columnheader">Партия</div>
              <div role="columnheader">Объектов</div>
              {stageColumns.filter(([key]) => !['milling'].includes(key)).map(([, label]) => (
                <div role="columnheader" key={label}>{label}</div>
              ))}
            </div>
            {activeParties.map((party) => {
              const lagging = laggingStageKeys(party)
              return (
                <div
                  className="dashboard-party-row dashboard-clickable-row"
                  role="row"
                  tabIndex={0}
                  key={party.id}
                  onClick={() => onPartyOpen(party.party_no)}
                  onKeyDown={(event) => {
                    if (event.key === 'Enter' || event.key === ' ') {
                      event.preventDefault()
                      onPartyOpen(party.party_no)
                    }
                  }}
                >
                  <div role="cell"><button className="link-button" onClick={(event) => { event.stopPropagation(); onPartyOpen(party.party_no) }}>{party.party_no}</button></div>
                  <div role="cell"><strong>{party.object_count}</strong></div>
                  {stageColumns.filter(([key]) => !['milling'].includes(key)).map(([key]) => {
                    const done = party.stage_counts[key] ?? 0
                    const percent = stagePercent(party, key)
                    return (
                      <div className={lagging.has(key) ? 'dashboard-lagging-cell' : ''} role="cell" key={key}>
                        <span className={`mini-progress ${percent === 100 ? 'good' : percent ? 'warning' : 'danger'}`}>
                          <i style={{ width: `${percent}%` }} />
                        </span>
                        {done} / {party.object_count}
                      </div>
                    )
                  })}
                </div>
              )
            })}
            {!activeParties.length && <div className="empty">Активных партий по выбранным фильтрам нет</div>}
          </div>
        </div>
        {Boolean(data?.archived_parties) && <p className="muted-note">Архивных партий: {data?.archived_parties}</p>}
      </section>

      <section className="section">
        <div className="section-head">
          <div>
            <h2>Контроль партий</h2>
            <p>Партии, где заполнено хотя бы одно контрольное поле.</p>
          </div>
          <div className="dashboard-filter-row">
            <button className={onlyCriticalControl ? 'active' : ''} onClick={() => setOnlyCriticalControl((value) => !value)}>Только критичные</button>
            <button className="icon-button" onClick={() => onReportsOpen?.('control')} disabled={!onReportsOpen}>Открыть полный отчёт</button>
          </div>
        </div>
        <div className="dashboard-control-table-wrap">
          <div className="dashboard-control-table" role="table" aria-label="Контроль партий">
            <div className="dashboard-control-row dashboard-control-head" role="row">
              <div role="columnheader">Партия</div>
              {controlColumns.map(([, label]) => <div role="columnheader" key={label}>{label}</div>)}
            </div>
            {partiesWithControl.map((party) => (
              <div className="dashboard-control-row" role="row" key={party.id}>
                <div role="cell"><button className="link-button" onClick={() => onPartyOpen(party.party_no)}>{party.party_no}</button></div>
                {controlColumns.map(([key]) => {
                  const display = controlValue(party[key])
                  const isCritical = key === 'control_need_recall' || key === 'control_recalled'
                  return (
                    <div className={display === '—' ? '' : `dashboard-control-cell${isCritical ? ' critical' : ''}`} role="cell" title={display} key={key}>
                      {display}
                    </div>
                  )
                })}
              </div>
            ))}
            {!partiesWithControl.length && <div className="empty">Контрольные данные пока не заполнены</div>}
          </div>
        </div>
      </section>
    </div>
  )
}
