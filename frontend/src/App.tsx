import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useCallback, useEffect, useState } from 'react'
import { api } from './api/client'
import { Shell } from './components/Shell'
import { DashboardPage } from './pages/DashboardPage'
import { ExportPage } from './pages/ExportPage'
import { LoginPage } from './pages/LoginPage'
import { ObjectDetailPage } from './pages/ObjectDetailPage'
import { ObjectsPage } from './pages/ObjectsPage'
import { PartiesPage } from './pages/PartiesPage'
import { ReportsPage } from './pages/ReportsPage'
import { SearchPage } from './pages/SearchPage'
import { EmployeesPage } from './pages/EmployeesPage'
import { ElectrophoresisImportPage, RegistryImportPage, RtImportPage } from './pages/ImportPage'
import { WorkSessionsPage } from './pages/WorkSessionsPage'

type ThemeMode = 'auto' | 'light' | 'dark'
type EffectiveTheme = 'light' | 'dark'

const themeStorageKey = 'dna_registry.theme'
const uiScaleStorageKey = 'dna_registry.ui_scale'
const minUiScale = 1
const maxUiScale = 1.35
const uiScaleStep = 0.1

function initialView() {
  if (typeof window !== 'undefined' && new URLSearchParams(window.location.search).has('report_tab')) return 'reports'
  return 'dashboard'
}

function systemTheme(): EffectiveTheme {
  if (typeof window === 'undefined') return 'light'
  return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
}

function storedThemeMode(): ThemeMode {
  if (typeof window === 'undefined') return 'auto'
  const stored = window.localStorage.getItem(themeStorageKey)
  return stored === 'light' || stored === 'dark' || stored === 'auto' ? stored : 'auto'
}

function nextThemeMode(mode: ThemeMode): ThemeMode {
  if (mode === 'auto') return 'light'
  if (mode === 'light') return 'dark'
  return 'auto'
}

function storedUiScale() {
  if (typeof window === 'undefined') return 1
  const parsed = Number(window.localStorage.getItem(uiScaleStorageKey))
  if (!Number.isFinite(parsed)) return 1
  return Math.min(maxUiScale, Math.max(minUiScale, parsed))
}

export function App() {
  const queryClient = useQueryClient()
  const [view, setView] = useState(initialView)
  const [objectId, setObjectId] = useState<number | null>(null)
  const [objectsQuery, setObjectsQuery] = useState('')
  const [partyFilter, setPartyFilter] = useState<string | null>(null)
  const [partySelect, setPartySelect] = useState<string | null>(null)
  const [themeMode, setThemeMode] = useState<ThemeMode>(storedThemeMode)
  const [effectiveTheme, setEffectiveTheme] = useState<EffectiveTheme>(() => themeMode === 'auto' ? systemTheme() : themeMode)
  const [uiScale, setUiScale] = useState(storedUiScale)
  const { data: user, isLoading } = useQuery({ queryKey: ['me'], queryFn: api.me, retry: false })
  const login = useMutation({
    mutationFn: ({ username, password }: { username: string; password: string }) => api.login(username, password),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['me'] })
  })
  const logout = useMutation({
    mutationFn: api.logout,
    onSuccess: () => queryClient.setQueryData(['me'], null)
  })
  useEffect(() => {
    window.localStorage.setItem(themeStorageKey, themeMode)
    if (themeMode !== 'auto') {
      setEffectiveTheme(themeMode)
      return
    }
    const query = window.matchMedia('(prefers-color-scheme: dark)')
    const update = () => setEffectiveTheme(query.matches ? 'dark' : 'light')
    update()
    query.addEventListener('change', update)
    return () => query.removeEventListener('change', update)
  }, [themeMode])

  useEffect(() => {
    document.documentElement.dataset.theme = effectiveTheme
    document.documentElement.style.colorScheme = effectiveTheme
  }, [effectiveTheme])

  useEffect(() => {
    const rounded = Math.round(uiScale * 10) / 10
    window.localStorage.setItem(uiScaleStorageKey, String(rounded))
    document.documentElement.style.setProperty('--ui-scale', String(rounded))
  }, [uiScale])

  function changeUiScale(direction: -1 | 1) {
    setUiScale((value) => Math.min(maxUiScale, Math.max(minUiScale, Math.round((value + direction * uiScaleStep) * 10) / 10)))
  }
  const openParty = useCallback((partyNo: string) => {
    if (view === 'objects' && partyFilter === partyNo && objectId === null && objectsQuery === '') return
    setObjectId(null)
    setObjectsQuery('')
    setPartyFilter(partyNo)
    setView('objects')
  }, [objectId, objectsQuery, partyFilter, view])
  const openPartyInParties = useCallback((partyNo: string) => {
    setObjectId(null)
    setPartySelect(partyNo)
    setView('parties')
  }, [])
  if (isLoading) return <div className="loading">Загрузка...</div>
  if (!user) return <LoginPage onLogin={(username, password) => login.mutateAsync({ username, password }).then(() => undefined)} />
  let page = <DashboardPage onPartyOpen={openParty} />
  if (objectId) page = <ObjectDetailPage id={objectId} user={user} onBack={() => setObjectId(null)} onPartyOpen={openParty} />
  else if (view === 'dashboard') page = <DashboardPage onPartyOpen={openParty} />
  else if (view === 'parties') page = <PartiesPage user={user} onObjectOpen={setObjectId} initialPartyNo={partySelect} onInitialPartyHandled={() => setPartySelect(null)} />
  else if (view === 'objects') page = <ObjectsPage initialQuery={objectsQuery} partyFilter={partyFilter} onQueryChange={setObjectsQuery} onPartyFilterChange={setPartyFilter} onOpen={setObjectId} onPartyOpen={openParty} />
  else if (view === 'work-sessions') page = <WorkSessionsPage user={user} />
  else if (view === 'search') page = <SearchPage onObjectOpen={setObjectId} />
  else if (view === 'reports') page = <ReportsPage user={user} onPartyOpen={openPartyInParties} />
  else if (view === 'employees') page = <EmployeesPage user={user} />
  else if (view === 'registry-import') page = <RegistryImportPage />
  else if (view === 'rt-import') page = <RtImportPage />
  else if (view === 'electrophoresis-import') page = <ElectrophoresisImportPage />
  else if (view === 'export') page = <ExportPage />
  return (
    <Shell
      user={user}
      active={view}
      onNavigate={(next) => { setObjectId(null); setView(next) }}
      onLogout={() => logout.mutate()}
      theme={effectiveTheme}
      themeMode={themeMode}
      onTheme={() => setThemeMode((mode) => nextThemeMode(mode))}
      uiScale={uiScale}
      onScaleDown={() => changeUiScale(-1)}
      onScaleUp={() => changeUiScale(1)}
      onScaleReset={() => setUiScale(1)}
    >
      {page}
    </Shell>
  )
}
