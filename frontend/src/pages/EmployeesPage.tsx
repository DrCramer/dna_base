import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Check, Plus, Search, X } from 'lucide-react'
import type { KeyboardEvent } from 'react'
import { useState } from 'react'
import { api } from '../api/client'
import type { Employee, ReferenceItem, User } from '../api/types'

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
  const [tab, setTab] = useState<'employees' | 'references'>('employees')
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
  const canEdit = user.role !== 'viewer'
  const employees = useQuery({
    queryKey: ['employees', q, showInactiveEmployees],
    queryFn: () => api.employees(q, undefined, undefined, undefined, showInactiveEmployees),
    staleTime: 30_000
  })
  const references = useQuery({
    queryKey: ['reference-items', category, refQ, showInactiveReferences],
    queryFn: () => api.referenceItems(category, refQ, showInactiveReferences),
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
      <header className="page-header">
        <h1>Справочники</h1>
      </header>
      <div className="tabs">
        <button className={tab === 'employees' ? 'active' : ''} onClick={() => setTab('employees')}>Сотрудники</button>
        <button className={tab === 'references' ? 'active' : ''} onClick={() => setTab('references')}>Реактивы / значения</button>
      </div>
      {tab === 'employees' ? (
        <section className="section">
          <h2>Сотрудники</h2>
          <div className="toolbar">
            <div className="searchbox"><Search size={18} /><input value={q} onChange={(event) => setQ(event.target.value)} placeholder="Поиск сотрудника" /></div>
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
                {(employees.data ?? []).map((employee) => {
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
            {!employees.data?.length && <div className="empty">Нет сотрудников</div>}
          </div>
        </section>
      ) : (
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
                {(references.data ?? []).map((item) => {
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
            {!references.data?.length && <div className="empty">Нет значений</div>}
          </div>
        </section>
      )}
    </div>
  )
}
