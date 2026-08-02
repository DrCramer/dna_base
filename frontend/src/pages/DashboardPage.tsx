import { useQuery } from '@tanstack/react-query'
import { api } from '../api/client'
import type { DashboardPartyProgress } from '../api/types'

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

export function DashboardPage({ onPartyOpen }: { onPartyOpen: (partyNo: string) => void }) {
  const { data, isLoading } = useQuery({ queryKey: ['dashboard'], queryFn: api.dashboard })
  if (isLoading) return <div className="page"><div className="loading">Загрузка...</div></div>
  const partiesWithControl = (data?.control_party_progress ?? data?.active_party_progress ?? []).filter(hasControlValues)
  return (
    <div className="page">
      <header className="page-header">
        <h1>Главная</h1>
      </header>

      <section className="section">
        <h2>Активные партии</h2>
        <p className="muted-note">Показаны последние 15 активных партий. Всего объектов: {data?.total_objects ?? 0}</p>
        <div className="dashboard-party-table-wrap">
          <div className="dashboard-party-table" role="table" aria-label="Активные партии">
            <div className="dashboard-party-row dashboard-party-head" role="row">
              <div role="columnheader">Партия</div>
              <div role="columnheader">Объектов</div>
              {stageColumns.filter(([key]) => !['milling'].includes(key)).map(([, label]) => (
                <div role="columnheader" key={label}>{label}</div>
              ))}
            </div>
            {(data?.active_party_progress ?? []).map((party) => (
              <div className="dashboard-party-row" role="row" key={party.id}>
                <div role="cell"><button className="link-button" onClick={() => onPartyOpen(party.party_no)}>{party.party_no}</button></div>
                <div role="cell"><strong>{party.object_count}</strong></div>
                {stageColumns.filter(([key]) => !['milling'].includes(key)).map(([key]) => {
                  const done = party.stage_counts[key] ?? 0
                  return <div role="cell" key={key}>{done} / {party.object_count}</div>
                })}
              </div>
            ))}
            {!data?.active_party_progress?.length && <div className="empty">Активных партий нет</div>}
          </div>
        </div>
        {Boolean(data?.archived_parties) && <p className="muted-note">Архивных партий: {data?.archived_parties}</p>}
      </section>

      <section className="section">
        <h2>Контроль партий</h2>
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
                  return (
                    <div className={display === '—' ? '' : 'dashboard-control-cell'} role="cell" title={display} key={key}>
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
