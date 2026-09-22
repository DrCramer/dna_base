import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Check, Plus, Search, X } from 'lucide-react'
import type { KeyboardEvent } from 'react'
import { useState } from 'react'
import { api } from '../api/client'
import type { Employee, ProtocolProfile, ProtocolStageType, ReferenceItem, User } from '../api/types'
import { EmptyState, ErrorState, LoadingState, PageHeader } from '../components/ui'

const categories = [
  ['extraction_method', 'Выделение_наборы'],
  ['quant_method', 'RT_наборы'],
  ['pcr_panel', 'PCR_наборы'],
  ['electrophoresis_kit', 'Форез_наборы'],
  ['sequencer', 'Секвенатор']
]

const employeeRoles = ['эксперт', 'лаборант']
const employeeStages = [
  ['preparation', 'Пробоподготовка'],
  ['milling', 'Измельчение'],
  ['extraction', 'Выделение'],
  ['realtime', 'RealTime'],
  ['pcr', 'ПЦР'],
  ['electrophoresis', 'Электрофорез'],
  ['analysis', 'Анализ']
] as const

type EmployeePatch = Partial<Omit<Employee, 'stage_roles'>> & { stage_roles?: string[] }
type ReferencePatch = Partial<Pick<ReferenceItem, 'name' | 'short_name' | 'comment' | 'is_active'>>

function categoryLabel(value: string) {
  return categories.find(([key]) => key === value)?.[1] || value
}

export function EmployeesPage({ user }: { user: User }) {
  const queryClient = useQueryClient()
  const [tab, setTab] = useState<'employees' | 'references' | 'profiles'>('employees')
  const [q, setQ] = useState('')
  const [fullName, setFullName] = useState('')
  const [shortName, setShortName] = useState('')
  const [role, setRole] = useState('лаборант')
  const [stageRoles, setStageRoles] = useState<string[]>([])
  const [refQ, setRefQ] = useState('')
  const [category, setCategory] = useState('extraction_method')
  const [refName, setRefName] = useState('')
  const [refShortName, setRefShortName] = useState('')
  const [refComment, setRefComment] = useState('')
  const [employeeError, setEmployeeError] = useState<string | null>(null)
  const [referenceError, setReferenceError] = useState<string | null>(null)
  const [showInactiveEmployees, setShowInactiveEmployees] = useState(false)
  const [showInactiveReferences, setShowInactiveReferences] = useState(false)
  const [roleFilter, setRoleFilter] = useState('all')
  const [profileStage, setProfileStage] = useState<ProtocolStageType>('pcr')
  const [profileName, setProfileName] = useState('')
  const [profileEdit, setProfileEdit] = useState<ProtocolProfile | null>(null)
  const [profileReagents, setProfileReagents] = useState('{}')
  const [profileInstruments, setProfileInstruments] = useState('{}')
  const canEdit = user.role !== 'viewer'
  const employees = useQuery({
    queryKey: ['employees', q, roleFilter, showInactiveEmployees],
    queryFn: () => api.employees(q, undefined, undefined, roleFilter === 'all' ? undefined : roleFilter, showInactiveEmployees),
    staleTime: 30_000
  })
  const references = useQuery({
    queryKey: ['reference-items', category, refQ, showInactiveReferences],
    queryFn: () => api.referenceItems(category, refQ, showInactiveReferences),
    staleTime: 30_000
  })
  const profiles = useQuery({
    queryKey: ['protocol-profiles', 'admin'],
    queryFn: () => api.protocolProfiles(undefined, true),
    staleTime: 30_000
  })
  function refreshEmployeeData() {
    queryClient.invalidateQueries({ queryKey: ['employees'] })
    queryClient.invalidateQueries({ queryKey: ['party-stage-table'] })
  }
  function refreshReferenceData() {
    queryClient.invalidateQueries({ queryKey: ['reference-items'] })
    queryClient.invalidateQueries({ queryKey: ['party-stage-table'] })
  }
  const create = useMutation({
    mutationFn: () => api.createEmployee({ full_name: fullName, short_name: shortName || null, role, stage_roles: stageRoles, is_verified: true }),
    onMutate: () => setEmployeeError(null),
    onSuccess: () => {
      setEmployeeError(null)
      setFullName('')
      setShortName('')
      setRole('лаборант')
      setStageRoles([])
      refreshEmployeeData()
    },
    onError: (error) => setEmployeeError(error instanceof Error ? error.message : 'Не удалось добавить сотрудника')
  })
  const update = useMutation({
    mutationFn: ({ id, patch }: { id: number; patch: EmployeePatch }) => api.updateEmployee(id, patch),
    onMutate: () => setEmployeeError(null),
    onSuccess: () => refreshEmployeeData(),
    onError: (error) => setEmployeeError(error instanceof Error ? error.message : 'Не удалось сохранить сотрудника')
  })
  const createReference = useMutation({
    mutationFn: () => api.createReferenceItem({ category, name: refName, short_name: refShortName || null, comment: refComment || null, is_active: true }),
    onSuccess: () => {
      setRefName('')
      setRefShortName('')
      setRefComment('')
      refreshReferenceData()
    }
  })
  const updateReference = useMutation({
    mutationFn: ({ id, patch }: { id: number; patch: ReferencePatch }) => api.updateReferenceItem(id, patch),
    onMutate: () => setReferenceError(null),
    onSuccess: () => refreshReferenceData(),
    onError: (error) => setReferenceError(error instanceof Error ? error.message : 'Не удалось сохранить значение')
  })
  const createProfile = useMutation({
    mutationFn: () => api.createProtocolProfile({ stage_type: profileStage, name: profileName.trim(), reference_item_id: null, active: true, plate_rules_json: {}, reagent_config_json: {}, instrument_config_json: {} }),
    onSuccess: () => { setProfileName(''); queryClient.invalidateQueries({ queryKey: ['protocol-profiles'] }) }
  })
  const updateProfile = useMutation({
    mutationFn: ({ id, patch }: { id: number; patch: Partial<ProtocolProfile> }) => api.updateProtocolProfile(id, patch),
    onSuccess: () => { setProfileEdit(null); queryClient.invalidateQueries({ queryKey: ['protocol-profiles'] }) }
  })
  function editProfile(item: ProtocolProfile) {
    setProfileEdit(item)
    setProfileReagents(JSON.stringify(item.reagent_config_json, null, 2))
    setProfileInstruments(JSON.stringify(item.instrument_config_json, null, 2))
  }
  function saveProfileConfig() {
    if (!profileEdit) return
    try {
      updateProfile.mutate({ id: profileEdit.id, patch: { reagent_config_json: JSON.parse(profileReagents), instrument_config_json: JSON.parse(profileInstruments) } })
    } catch {
      setReferenceError('Конфигурация профиля должна быть корректным JSON')
    }
  }
  function toggleCreateStage(stage: string) {
    setStageRoles((prev) => prev.includes(stage) ? prev.filter((item) => item !== stage) : [...prev, stage])
  }
  function employeeStageKeys(employee: Employee) {
    return (employee.stage_roles || []).filter((item) => item.is_active).map((item) => item.stage_type)
  }
  function toggleEmployeeStage(employee: Employee, stage: string) {
    const current = employeeStageKeys(employee)
    const next = current.includes(stage) ? current.filter((item) => item !== stage) : [...current, stage]
    update.mutate({ id: employee.id, patch: { stage_roles: next } })
  }
  function employeeBusy(employee: Employee) {
    return update.isPending && update.variables?.id === employee.id
  }
  function referenceBusy(item: ReferenceItem) {
    return updateReference.isPending && updateReference.variables?.id === item.id
  }
  function patchReference(item: ReferenceItem, patch: ReferencePatch) {
    updateReference.mutate({ id: item.id, patch })
  }
  function saveReferenceText(item: ReferenceItem, key: 'name' | 'short_name' | 'comment', value: string) {
    const next = key === 'name' ? value.trim() : value.trim() || null
    const current = item[key] || ''
    if (next === current) return
    if (key === 'name' && !next) return
    patchReference(item, { [key]: next } as ReferencePatch)
  }
  function submitReferenceInput(event: KeyboardEvent<HTMLInputElement>) {
    if (event.key === 'Enter') {
      event.currentTarget.blur()
    }
  }
  return (
    <div className="page">
      <PageHeader
        title="Справочники"
        description="Сотрудники, роли по этапам и справочные значения, которые используются в таблицах и массовом заполнении."
      />
      <div className="tabs">
        <button className={tab === 'employees' ? 'active' : ''} onClick={() => setTab('employees')}>Сотрудники</button>
        <button className={tab === 'references' ? 'active' : ''} onClick={() => setTab('references')}>Реактивы / значения</button>
        <button className={tab === 'profiles' ? 'active' : ''} onClick={() => setTab('profiles')}>Профили протоколов</button>
      </div>
      {tab === 'employees' ? (
        <section className="section">
          <div className="section-head">
            <div>
              <h2>Сотрудники</h2>
              <p>{employees.isLoading ? 'Загрузка...' : `${employees.data?.length ?? 0} сотрудников`}</p>
            </div>
          </div>
          <div className="toolbar">
            <div className="searchbox"><Search size={18} /><input value={q} onChange={(event) => setQ(event.target.value)} placeholder="Поиск сотрудника" /></div>
            <select className="compact-select" value={roleFilter} onChange={(event) => setRoleFilter(event.target.value)}>
              <option value="all">Все роли</option>
              {employeeRoles.map((item) => <option value={item} key={item}>{item}</option>)}
            </select>
            <label className="inline-check">
              <input type="checkbox" checked={showInactiveEmployees} onChange={(event) => setShowInactiveEmployees(event.target.checked)} />
              <span>Показать отключённых</span>
            </label>
          </div>
          {canEdit && (
            <div className="employee-create-row">
              <input value={fullName} onChange={(event) => setFullName(event.target.value)} placeholder="ФИО" />
              <input value={shortName} onChange={(event) => setShortName(event.target.value)} placeholder="Кратко" />
              <select value={role} onChange={(event) => setRole(event.target.value)}>
                {employeeRoles.map((item) => <option value={item} key={item}>{item}</option>)}
              </select>
              <div className="employee-create-stages">
                {employeeStages.map(([stage, label]) => (
                  <label key={stage} title={label}>
                    <input type="checkbox" checked={stageRoles.includes(stage)} onChange={() => toggleCreateStage(stage)} />
                    <span>{label}</span>
                  </label>
                ))}
              </div>
              <button className="icon-button" disabled={!fullName.trim() || create.isPending} onClick={() => create.mutate()}><Plus size={18} />Добавить</button>
            </div>
          )}
          {employeeError && <div className="alert danger">{employeeError}</div>}
          {employees.isLoading && <LoadingState title="Загрузка сотрудников..." rows={4} />}
          {employees.isError && <ErrorState error={employees.error} onRetry={() => employees.refetch()} />}
          <div className="employee-table-wrap">
            <table className="employee-table">
              <thead>
                <tr>
                  <th>ФИО</th>
                  <th>Роль</th>
                  <th>Активен</th>
                  {employeeStages.map(([stage, label]) => <th key={stage}>{label}</th>)}
                  <th>Действия</th>
                </tr>
              </thead>
              <tbody>
                {!employees.isLoading && (employees.data ?? []).map((employee) => {
                  const busy = employeeBusy(employee)
                  return (
                    <tr key={employee.id} className={`${busy ? 'is-busy' : ''} ${!employee.is_active ? 'is-inactive' : ''}`}>
                      <td>
                        <strong>{employee.full_name}</strong>
                        <span>{employee.initials || employee.short_name || '—'} · {employee.is_verified ? 'подтвержден' : 'импортирован'}</span>
                      </td>
                      <td>
                        <select
                          value={employee.role || ''}
                          disabled={!canEdit || busy}
                          onChange={(event) => update.mutate({ id: employee.id, patch: { role: event.target.value } })}
                        >
                          <option value="">—</option>
                          {employeeRoles.map((item) => <option value={item} key={item}>{item}</option>)}
                        </select>
                      </td>
                      <td className="center-cell">
                        <input
                          type="checkbox"
                          checked={employee.is_active}
                          disabled={!canEdit || busy}
                          onChange={() => update.mutate({ id: employee.id, patch: { is_active: !employee.is_active } })}
                          aria-label={`Активен: ${employee.full_name}`}
                        />
                      </td>
                      {employeeStages.map(([stage, label]) => (
                        <td key={stage} className="center-cell">
                          <input
                            type="checkbox"
                            checked={employeeStageKeys(employee).includes(stage)}
                            disabled={!canEdit || busy}
                            onChange={() => toggleEmployeeStage(employee, stage)}
                            aria-label={`${label}: ${employee.full_name}`}
                          />
                        </td>
                      ))}
                      <td>
                        <div className="employee-row-actions">
                          {!employee.is_verified && canEdit && (
                            <button className="tiny-button" disabled={busy} onClick={() => update.mutate({ id: employee.id, patch: { is_verified: true } })}>
                              <Check size={14} />Подтвердить
                            </button>
                          )}
                          {canEdit && (
                            <button className="tiny-button" disabled={busy} onClick={() => update.mutate({ id: employee.id, patch: { is_active: !employee.is_active } })}>
                              {employee.is_active ? <X size={14} /> : <Check size={14} />}{employee.is_active ? 'Отключить' : 'Включить'}
                            </button>
                          )}
                          {!canEdit && <span className="muted-cell">только чтение</span>}
                        </div>
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
            {!employees.isLoading && !employees.data?.length && (
              <EmptyState title="Сотрудники не найдены">Измените поиск, роль или фильтр активности.</EmptyState>
            )}
          </div>
        </section>
      ) : tab === 'references' ? (
        <section className="section">
          <h2>Реактивы / значения</h2>
          <div className="toolbar">
            <select value={category} onChange={(event) => setCategory(event.target.value)}>
              {categories.map(([value, label]) => <option value={value} key={value}>{label}</option>)}
            </select>
            <div className="searchbox"><Search size={18} /><input value={refQ} onChange={(event) => setRefQ(event.target.value)} placeholder="Поиск значения" /></div>
            <label className="inline-check">
              <input type="checkbox" checked={showInactiveReferences} onChange={(event) => setShowInactiveReferences(event.target.checked)} />
              <span>Показать отключённые</span>
            </label>
          </div>
          {canEdit && (
            <div className="reference-create-row">
              <input value={refName} onChange={(event) => setRefName(event.target.value)} placeholder="Название" />
              <input value={refShortName} onChange={(event) => setRefShortName(event.target.value)} placeholder="Кратко" />
              <input value={refComment} onChange={(event) => setRefComment(event.target.value)} placeholder="Комментарий" />
              <button className="icon-button" disabled={!refName.trim() || createReference.isPending} onClick={() => createReference.mutate()}><Plus size={18} />Добавить</button>
            </div>
          )}
          {referenceError && <div className="alert danger">{referenceError}</div>}
          {references.isLoading && <LoadingState title="Загрузка справочника..." rows={4} />}
          {references.isError && <ErrorState error={references.error} onRetry={() => references.refetch()} />}
          <div className="reference-table-wrap">
            <table className="reference-table">
              <thead>
                <tr>
                  <th>Название</th>
                  <th>Кратко</th>
                  <th>Комментарий</th>
                  <th>Активно</th>
                  <th>Действия</th>
                </tr>
              </thead>
              <tbody>
                {!references.isLoading && (references.data ?? []).map((item) => {
                  const busy = referenceBusy(item)
                  return (
                    <tr key={item.id} className={`${busy ? 'is-busy' : ''} ${!item.is_active ? 'is-inactive' : ''}`}>
                      <td>
                        <input
                          defaultValue={item.name}
                          disabled={!canEdit || busy}
                          onBlur={(event) => saveReferenceText(item, 'name', event.target.value)}
                          onKeyDown={submitReferenceInput}
                          aria-label={`Название: ${item.name}`}
                        />
                      </td>
                      <td>
                        <input
                          defaultValue={item.short_name || ''}
                          disabled={!canEdit || busy}
                          onBlur={(event) => saveReferenceText(item, 'short_name', event.target.value)}
                          onKeyDown={submitReferenceInput}
                          aria-label={`Кратко: ${item.name}`}
                        />
                      </td>
                      <td>
                        <input
                          defaultValue={item.comment || ''}
                          disabled={!canEdit || busy}
                          onBlur={(event) => saveReferenceText(item, 'comment', event.target.value)}
                          onKeyDown={submitReferenceInput}
                          aria-label={`Комментарий: ${item.name}`}
                        />
                      </td>
                      <td className="center-cell">
                        <input
                          type="checkbox"
                          checked={item.is_active}
                          disabled={!canEdit || busy}
                          onChange={() => patchReference(item, { is_active: !item.is_active })}
                          aria-label={`Активно: ${item.name}`}
                        />
                      </td>
                      <td>
                        {canEdit ? (
                          <button className="tiny-button" disabled={busy} onClick={() => patchReference(item, { is_active: !item.is_active })}>
                            {item.is_active ? <X size={14} /> : <Check size={14} />}{item.is_active ? 'Отключить' : 'Включить'}
                          </button>
                        ) : (
                          <span className="muted-cell">только чтение</span>
                        )}
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
            {!references.isLoading && !references.data?.length && (
              <EmptyState title="Значения не найдены">Проверьте категорию, поиск или фильтр отключённых значений.</EmptyState>
            )}
          </div>
        </section>
      ) : (
        <section className="section">
          <div className="section-head"><div><h2>Профили PCR / Фореза</h2><p>Рецептуры и параметры приборов из единого Excel-протокола.</p></div></div>
          {user.role === 'admin' ? <div className="reference-create-row protocol-profile-create"><select value={profileStage} onChange={(event) => setProfileStage(event.target.value as ProtocolStageType)}><option value="pcr">ПЦР</option><option value="electrophoresis">Форез</option></select><input value={profileName} onChange={(event) => setProfileName(event.target.value)} placeholder="Название профиля" /><span /><button className="icon-button" disabled={!profileName.trim() || createProfile.isPending} onClick={() => createProfile.mutate()}><Plus size={18} />Добавить</button></div> : null}
          {profiles.isLoading ? <LoadingState title="Загрузка профилей..." rows={5} /> : null}
          {profiles.isError ? <ErrorState error={profiles.error} onRetry={() => profiles.refetch()} /> : null}
          <div className="reference-table-wrap"><table className="reference-table"><thead><tr><th>Этап</th><th>Название</th><th>Рецептура</th><th>Параметры прибора</th><th>Активен</th><th /></tr></thead><tbody>{(profiles.data || []).map((item) => <tr key={item.id} className={!item.active ? 'is-inactive' : ''}><td>{item.stage_type === 'pcr' ? 'ПЦР' : 'Форез'}</td><td><strong>{item.name}</strong></td><td>{Object.keys(item.reagent_config_json).length} параметров</td><td>{Object.values(item.instrument_config_json).filter((value) => value !== null).length} параметров</td><td className="center-cell"><input type="checkbox" checked={item.active} disabled={user.role !== 'admin'} onChange={() => updateProfile.mutate({ id: item.id, patch: { active: !item.active } })} /></td><td>{user.role === 'admin' ? <button type="button" className="tiny-button" onClick={() => editProfile(item)}>Настроить</button> : <span className="muted-cell">только чтение</span>}</td></tr>)}</tbody></table></div>
          {profileEdit ? <div className="modal-backdrop" onMouseDown={() => setProfileEdit(null)}><div className="modal protocol-profile-modal" role="dialog" aria-modal="true" onMouseDown={(event) => event.stopPropagation()}><h2>{profileEdit.name}</h2><label>Рецептура<textarea rows={12} value={profileReagents} onChange={(event) => setProfileReagents(event.target.value)} /></label><label>Параметры прибора<textarea rows={12} value={profileInstruments} onChange={(event) => setProfileInstruments(event.target.value)} /></label>{referenceError ? <div className="alert danger">{referenceError}</div> : null}<div className="modal-actions"><button className="icon-button" onClick={() => setProfileEdit(null)}>Отмена</button><button className="primary compact" onClick={saveProfileConfig} disabled={updateProfile.isPending}><Check size={17} />Сохранить</button></div></div></div> : null}
        </section>
      )}
    </div>
  )
}
