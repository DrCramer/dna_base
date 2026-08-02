import { useQuery } from '@tanstack/react-query'
import { BarChart3, Download, ExternalLink, FilterX } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { api } from '../api/client'
import type { PartyControlReportRow, PeriodStatisticsRow, ReportPartyRow, User } from '../api/types'

type ReportsTab = 'overview' | 'control' | 'progress' | 'statistics' | 'performers'
type StatsMode = 'weekly' | 'monthly' | 'yearly'

const stageColumns = [
  ['sample_prep', 'Пробоподготовка'],
  ['milling', 'Измельчение'],
  ['dna_extraction', 'Выделение'],
  ['realtime', 'RealTime'],
  ['pcr', 'ПЦР'],
  ['electrophoresis', 'Электрофорез'],
  ['analysis', 'Анализ']
] as const

const kpiLabels: Record<string, string> = {
  active_parties: 'Всего активных партий',
  total_objects: 'Всего объектов',
  objects_in_work: 'Объектов в работе',
  problem_parties: 'Проблемных партий',
  parties_without_control: 'Партий с незаполненным контролем',
  objects_without_sample_prep: 'Объектов без пробоподготовки',
  objects_without_milling: 'Объектов без измельчения',
  objects_without_extraction: 'Объектов без выделения',
  objects_without_realtime: 'Объектов без RealTime',
  objects_without_pcr: 'Объектов без ПЦР',
  objects_without_electrophoresis: 'Объектов без электрофореза',
  objects_without_analysis: 'Объектов без анализа',
  objects_with_repeat_stages: 'Объектов с повторными этапами',
  objects_no_object: 'Объектов "Нет объекта"',
  objects_no_decree: 'Объектов "Нет постановления"',
  objects_no_biomaterial: 'Объектов "Нет биоматериала"',
  objects_burnt_bone: 'Объектов "Горелая кость"'
}

const controlColumns = [
  ['control_actual_decrees', 'Фактическое количество постановлений'],
  ['control_decree_without_object', 'Есть постановление, но нет объекта'],
  ['control_object_without_decree', 'Есть объект, но нет постановления'],
  ['control_unidentified_rostov_no', 'Неидентифицируемый ростовский номер'],
  ['control_need_recall', 'Надо отозвать'],
  ['control_recalled', 'Отозваны']
] as const

function readInitialParams() {
  const params = new URLSearchParams(window.location.search)
  return {
    tab: (params.get('report_tab') as ReportsTab) || 'overview',
    stats: (params.get('stats') as StatsMode) || 'monthly',
    case_year: params.get('case_year') || '',
    period: params.get('period') || 'year',
    date_from: params.get('date_from') || '',
    date_to: params.get('date_to') || '',
    party_ids: params.get('party_ids') || '',
    stage_type: params.get('stage_type') || '',
    employee_id: params.get('employee_id') || '',
    object_type: params.get('object_type') || '',
    box_no: params.get('box_no') || '',
    include_archived: params.get('include_archived') === 'true',
    include_empty_parties: params.get('include_empty_parties') !== 'false',
    only_problematic: params.get('only_problematic') === 'true',
    quick: params.get('quick') || ''
  }
}

function compactDate(value: string | null) {
  if (!value) return '—'
  return value.slice(0, 10).split('-').reverse().join('.')
}

function text(value: unknown) {
  const normalized = String(value ?? '').trim()
  return normalized || '—'
}

function stageProgress(row: ReportPartyRow, stage: string) {
  const progress = row.stage_progress?.[stage]
  if (!progress) return '0 / 0 · 0%'
  return `${progress.done} / ${progress.total} · ${progress.percent}%`
}

function statusClass(status: string) {
  if (status === 'Критично') return 'report-status critical'
  if (status === 'Есть замечания') return 'report-status warning'
  if (status === 'Без проблем') return 'report-status good'
  return 'report-status muted'
}

function percentClass(percent: number) {
  if (percent >= 100) return 'report-progress good'
  if (percent >= 50) return 'report-progress warning'
  if (percent > 0) return 'report-progress danger'
  return 'report-progress muted'
}

export function ReportsPage({ user, onPartyOpen }: { user: User; onPartyOpen: (partyNo: string) => void }) {
  const initial = useMemo(readInitialParams, [])
  const [tab, setTab] = useState<ReportsTab>(initial.tab)
  const [statsMode, setStatsMode] = useState<StatsMode>(initial.stats)
  const [filters, setFilters] = useState(initial)
  const partyYears = useQuery({ queryKey: ['parties', 'years'], queryFn: api.partyYears, staleTime: 300_000 })
  const parties = useQuery({
    queryKey: ['reports', 'parties-filter', filters.case_year, filters.include_archived],
    queryFn: () => api.parties('', filters.include_archived, filters.case_year ? Number(filters.case_year) : null),
    staleTime: 60_000
  })
  const employees = useQuery({ queryKey: ['reports', 'employees'], queryFn: () => api.employees(''), staleTime: 60_000 })

  useEffect(() => {
    if (!filters.case_year && partyYears.data?.default_year) {
      setFilters((current) => ({ ...current, case_year: String(partyYears.data?.default_year || '') }))
    }
  }, [filters.case_year, partyYears.data?.default_year])

  const queryFilters = useMemo(() => ({
    case_year: filters.case_year || undefined,
    date_from: filters.date_from || undefined,
    date_to: filters.date_to || undefined,
    party_ids: filters.party_ids || undefined,
    stage_type: filters.stage_type || undefined,
    employee_id: filters.employee_id || undefined,
    object_type: filters.object_type || undefined,
    box_no: filters.box_no || undefined,
    include_archived: filters.include_archived,
    include_empty_parties: filters.include_empty_parties,
    only_problematic: filters.only_problematic,
    quick: filters.quick || undefined,
    page_size: 300
  }), [filters])

  useEffect(() => {
    const params = new URLSearchParams()
    params.set('report_tab', tab)
    params.set('stats', statsMode)
    Object.entries(queryFilters).forEach(([key, value]) => {
      if (value === undefined || value === null || value === '' || key === 'page_size') return
      params.set(key, String(value))
    })
    window.history.replaceState(null, '', `${window.location.pathname}?${params.toString()}`)
  }, [queryFilters, statsMode, tab])

  const overview = useQuery({ queryKey: ['reports', 'overview', queryFilters], queryFn: () => api.reportOverview(queryFilters), enabled: tab === 'overview' })
  const control = useQuery({ queryKey: ['reports', 'control', queryFilters], queryFn: () => api.reportPartyControl(queryFilters), enabled: tab === 'control' })
  const progress = useQuery({ queryKey: ['reports', 'progress', queryFilters], queryFn: () => api.reportWorkProgress(queryFilters), enabled: tab === 'progress' })
  const statistics = useQuery({ queryKey: ['reports', 'statistics', statsMode, queryFilters], queryFn: () => api.reportStatistics(statsMode, queryFilters), enabled: tab === 'statistics' })
  const performers = useQuery({ queryKey: ['reports', 'performers', queryFilters], queryFn: () => api.reportPerformers(queryFilters), enabled: tab === 'performers' })

  const selectedPartyIds = useMemo(() => new Set(filters.party_ids.split(',').map((item) => Number(item)).filter(Boolean)), [filters.party_ids])
  const exportReport = tab === 'progress'
    ? 'work-progress'
    : tab === 'control'
      ? 'party-control'
      : tab === 'statistics'
        ? `statistics-${statsMode}`
        : tab

  function updateFilter(key: keyof typeof filters, value: string | boolean) {
    setFilters((current) => ({ ...current, [key]: value }))
  }

  function setPeriod(period: string) {
    const today = new Date()
    const iso = (date: Date) => date.toISOString().slice(0, 10)
    const start = new Date(today)
    if (period === 'today') {
      updateFilter('period', period)
      setFilters((current) => ({ ...current, period, date_from: iso(today), date_to: iso(today) }))
      return
    }
    if (period === 'week') start.setDate(today.getDate() - today.getDay() + 1)
    else if (period === 'month') start.setDate(1)
    else if (period === 'year') start.setMonth(0, 1)
    setFilters((current) => ({ ...current, period, date_from: period === 'custom' ? current.date_from : iso(start), date_to: period === 'custom' ? current.date_to : iso(today) }))
  }

  function resetFilters() {
    setFilters({
      ...initial,
      tab,
      stats: statsMode,
      case_year: partyYears.data?.default_year ? String(partyYears.data.default_year) : '',
      include_archived: false,
      include_empty_parties: true,
      only_problematic: false,
      quick: ''
    })
  }

  return (
    <div className="page reports-page">
      <header className="page-header">
        <div>
          <h1>Отчёты</h1>
          <p className="muted-note">Управленческая сводка по партиям, контролю и ходу лабораторной работы.</p>
        </div>
        <a className="icon-button" href={api.reportExportUrl(exportReport, queryFilters)}>
          <Download size={18} />Экспорт
        </a>
      </header>

      <section className="section reports-filter-panel">
        <div className="reports-filter-grid">
          <label>Год
            <select value={filters.case_year} onChange={(event) => updateFilter('case_year', event.target.value)}>
              <option value="">Все годы</option>
              {(partyYears.data?.years ?? []).map((year) => <option key={year} value={year}>{year}</option>)}
            </select>
          </label>
          <label>Период
            <select value={filters.period} onChange={(event) => setPeriod(event.target.value)}>
              <option value="today">Сегодня</option>
              <option value="week">Текущая неделя</option>
              <option value="month">Текущий месяц</option>
              <option value="year">Текущий год</option>
              <option value="custom">Произвольный диапазон</option>
            </select>
          </label>
          <label>С даты
            <input type="date" value={filters.date_from} onChange={(event) => updateFilter('date_from', event.target.value)} />
          </label>
          <label>По дату
            <input type="date" value={filters.date_to} onChange={(event) => updateFilter('date_to', event.target.value)} />
          </label>
          <label>Партии
            <select
              multiple
              value={Array.from(selectedPartyIds).map(String)}
              onChange={(event) => {
                const values = Array.from(event.currentTarget.selectedOptions).map((option) => option.value)
                updateFilter('party_ids', values.join(','))
              }}
            >
              {(parties.data?.items ?? []).map((party) => (
                <option key={party.id} value={party.id}>№ {party.party_no} · {party.object_count}</option>
              ))}
            </select>
          </label>
          <label>Этап
            <select value={filters.stage_type} onChange={(event) => updateFilter('stage_type', event.target.value)}>
              <option value="">Все этапы</option>
              {stageColumns.map(([key, label]) => <option key={key} value={key}>{label}</option>)}
            </select>
          </label>
          <label>Исполнитель
            <select value={filters.employee_id} onChange={(event) => updateFilter('employee_id', event.target.value)}>
              <option value="">Все сотрудники</option>
              {(employees.data ?? []).map((employee) => <option key={employee.id} value={employee.id}>{employee.full_name}</option>)}
            </select>
          </label>
          <label>Тип объекта
            <input value={filters.object_type} onChange={(event) => updateFilter('object_type', event.target.value)} placeholder="кость, зуб..." />
          </label>
          <label>Коробка
            <input value={filters.box_no} onChange={(event) => updateFilter('box_no', event.target.value)} placeholder="номер коробки" />
          </label>
        </div>
        <div className="reports-filter-actions">
          <label className="checkbox-inline"><input type="checkbox" checked={!filters.include_archived} onChange={(event) => updateFilter('include_archived', !event.target.checked)} /> Только активные партии</label>
          <label className="checkbox-inline"><input type="checkbox" checked={filters.include_archived} onChange={(event) => updateFilter('include_archived', event.target.checked)} /> Показывать архивные</label>
          <label className="checkbox-inline"><input type="checkbox" checked={filters.include_empty_parties} onChange={(event) => updateFilter('include_empty_parties', event.target.checked)} /> Показывать пустые партии</label>
          <label className="checkbox-inline"><input type="checkbox" checked={filters.only_problematic} onChange={(event) => updateFilter('only_problematic', event.target.checked)} /> Только проблемные</label>
          <button className="icon-button" onClick={resetFilters}><FilterX size={18} />Сбросить фильтры</button>
        </div>
      </section>

      <div className="tabs report-tabs">
        <button className={tab === 'overview' ? 'active' : ''} onClick={() => setTab('overview')}>Обзор</button>
        <button className={tab === 'control' ? 'active' : ''} onClick={() => setTab('control')}>Контроль партии</button>
        <button className={tab === 'progress' ? 'active' : ''} onClick={() => setTab('progress')}>Ход работы</button>
        <button className={tab === 'statistics' ? 'active' : ''} onClick={() => setTab('statistics')}>Статистика</button>
        <button className={tab === 'performers' ? 'active' : ''} onClick={() => setTab('performers')}>Исполнители</button>
      </div>

      {tab === 'overview' && (
        <section className="section">
          {overview.isLoading ? <div className="loading">Загрузка...</div> : (
            <>
              <div className="report-kpi-grid">
                {Object.entries(kpiLabels).map(([key, label]) => (
                  <div className="report-kpi" key={key}>
                    <span>{label}</span>
                    <strong>{overview.data?.kpis?.[key] ?? 0}</strong>
                  </div>
                ))}
              </div>
              <PartyProgressTable rows={overview.data?.items ?? []} onPartyOpen={onPartyOpen} />
            </>
          )}
        </section>
      )}

      {tab === 'control' && (
        <section className="section">
          <div className="report-quick-filters">
            {[
              ['', 'Все'],
              ['problem', 'Только с проблемами'],
              ['critical', 'Только критичные'],
              ['control_decree_without_object', 'Нет объекта'],
              ['control_object_without_decree', 'Нет постановления'],
              ['control_unidentified_rostov_no', 'Неидентифицируемый номер'],
              ['control_need_recall', 'Надо отозвать'],
              ['control_recalled', 'Отозваны'],
              ['empty_control', 'Без заполненного контроля']
            ].map(([key, label]) => <button key={key} className={filters.quick === key ? 'active' : ''} onClick={() => updateFilter('quick', key)}>{label}</button>)}
          </div>
          {control.isLoading ? <div className="loading">Загрузка...</div> : <ControlTable rows={control.data?.items ?? []} onPartyOpen={onPartyOpen} />}
        </section>
      )}

      {tab === 'progress' && (
        <section className="section">
          <div className="report-quick-filters">
            {[
              ['', 'Все'],
              ['no_sample_prep', 'Без пробоподготовки'],
              ['no_extraction', 'Без выделения'],
              ['no_realtime', 'Без RealTime'],
              ['no_pcr', 'Без ПЦР'],
              ['no_electrophoresis', 'Без электрофореза'],
              ['no_analysis', 'Без анализа'],
              ['repeat_analysis', 'Повторные анализы'],
              ['pdf', 'PDF фореза'],
              ['control_pdf', 'Контрольные PDF'],
              ['no_biomaterial', 'Нет биоматериала'],
              ['burnt_bone', 'Горелая кость']
            ].map(([key, label]) => <button key={key} className={filters.quick === key ? 'active' : ''} onClick={() => updateFilter('quick', key)}>{label}</button>)}
          </div>
          {progress.isLoading ? <div className="loading">Загрузка...</div> : <PartyProgressTable rows={progress.data?.items ?? []} onPartyOpen={onPartyOpen} />}
        </section>
      )}

      {tab === 'statistics' && (
        <section className="section">
          <div className="tabs report-subtabs">
            <button className={statsMode === 'weekly' ? 'active' : ''} onClick={() => setStatsMode('weekly')}>По неделям</button>
            <button className={statsMode === 'monthly' ? 'active' : ''} onClick={() => setStatsMode('monthly')}>По месяцам</button>
            <button className={statsMode === 'yearly' ? 'active' : ''} onClick={() => setStatsMode('yearly')}>По годам</button>
          </div>
          {statistics.isLoading ? <div className="loading">Загрузка...</div> : <StatisticsTable rows={statistics.data?.items ?? []} mode={statsMode} />}
        </section>
      )}

      {tab === 'performers' && (
        <section className="section">
          <div className="alert">Вкладка подготовлена для следующего расширения отчётов по нагрузке сотрудников.</div>
          <div className="report-table-wrap">
            <table className="report-table">
              <thead><tr><th>Исполнитель</th><th>Роль</th>{stageColumns.map(([, label]) => <th key={label}>{label}</th>)}<th>Всего действий</th></tr></thead>
              <tbody>
                {(performers.data?.items ?? []).map((row) => (
                  <tr key={`${row.employee}-${row.role}`}>
                    <td>{row.employee}</td>
                    <td>{row.role}</td>
                    {stageColumns.map(([stage]) => <td key={stage}>{row.stage_counts?.[stage] ?? 0}</td>)}
                    <td><strong>{row.total_actions}</strong></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}
    </div>
  )
}

function PartyProgressTable({ rows, onPartyOpen }: { rows: ReportPartyRow[]; onPartyOpen: (partyNo: string) => void }) {
  return (
    <div className="report-table-wrap">
      <table className="report-table">
        <thead>
          <tr>
            <th>Год</th><th>Партия</th><th>Объектов</th><th>Регистрация</th>
            {stageColumns.map(([, label]) => <th key={label}>{label}</th>)}
            <th>Проблемы контроля</th><th>Отстающий этап</th><th>Готовность</th><th>Последнее изменение</th><th>Статус</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.party_id}>
              <td>{row.case_year ?? '—'}</td>
              <td><button className="link-button" onClick={() => onPartyOpen(row.party_no)}>№ {row.party_no} <ExternalLink size={13} /></button></td>
              <td><strong>{row.object_count}</strong></td>
              <td>{row.object_count} / {row.object_count} · {row.object_count ? 100 : 0}%</td>
              {stageColumns.map(([stage]) => <td key={stage}><span className={percentClass(row.stage_progress?.[stage]?.percent ?? 0)}>{stageProgress(row, stage)}</span></td>)}
              <td>{row.control_problem_count}</td>
              <td>{row.lagging_stage || '—'}</td>
              <td><span className={percentClass(row.readiness_percent)}>{row.readiness_percent}%</span></td>
              <td>{compactDate(row.latest_change)}</td>
              <td>{row.status}</td>
            </tr>
          ))}
          {!rows.length && <tr><td colSpan={15} className="empty">По текущим фильтрам данных нет</td></tr>}
        </tbody>
      </table>
    </div>
  )
}

function ControlTable({ rows, onPartyOpen }: { rows: PartyControlReportRow[]; onPartyOpen: (partyNo: string) => void }) {
  return (
    <div className="report-table-wrap">
      <table className="report-table control-report-table">
        <thead>
          <tr>
            <th>Год</th><th>Партия</th><th>Объектов</th>
            {controlColumns.map(([, label]) => <th key={label}>{label}</th>)}
            <th>Количество проблем</th><th>Статус контроля</th><th>Последнее изменение</th><th>Действия</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.party_id}>
              <td>{row.case_year ?? '—'}</td>
              <td><button className="link-button" onClick={() => onPartyOpen(row.party_no)}>№ {row.party_no}</button></td>
              <td><strong>{row.object_count}</strong></td>
              {controlColumns.map(([key]) => (
                <td key={key} className={key === 'control_need_recall' || key === 'control_recalled' ? 'report-critical-cell' : ''} title={text(row[key])}>
                  {text(row[key])}
                </td>
              ))}
              <td>{row.problem_count}</td>
              <td><span className={statusClass(row.control_status)}>{row.control_status}</span></td>
              <td>{compactDate(row.latest_change)}</td>
              <td><button className="icon-button compact" onClick={() => onPartyOpen(row.party_no)}><BarChart3 size={16} />Открыть партию</button></td>
            </tr>
          ))}
          {!rows.length && <tr><td colSpan={14} className="empty">Контрольные данные не найдены</td></tr>}
        </tbody>
      </table>
    </div>
  )
}

function StatisticsTable({ rows, mode }: { rows: PeriodStatisticsRow[]; mode: StatsMode }) {
  return (
    <div className="report-table-wrap">
      <table className="report-table">
        <thead>
          <tr>
            <th>Год</th>
            {mode === 'weekly' && <th>Неделя</th>}
            {mode === 'monthly' && <th>Месяц</th>}
            <th>Новых партий</th><th>Новых объектов</th>
            {stageColumns.map(([, label]) => <th key={label}>{label}</th>)}
            <th>Повторных этапов</th><th>Проблем контроля</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.period_key}>
              <td>{row.year ?? '—'}</td>
              {mode === 'weekly' && <td>{row.week ?? '—'}</td>}
              {mode === 'monthly' && <td>{row.month ?? '—'}</td>}
              <td>{row.new_parties}</td><td>{row.new_objects}</td>
              {stageColumns.map(([stage]) => <td key={stage}>{row.stage_counts?.[stage] ?? 0}</td>)}
              <td>{row.repeat_stage_events}</td><td>{row.control_problems}</td>
            </tr>
          ))}
          {!rows.length && <tr><td colSpan={13} className="empty">Статистика по текущим фильтрам пустая</td></tr>}
        </tbody>
      </table>
    </div>
  )
}
