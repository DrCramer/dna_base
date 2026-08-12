import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useCallback, useEffect, useState } from 'react'
import { api } from './api/client'
import { Shell } from './components/Shell'
import { LoadingState } from './components/ui'
import { DashboardPage } from './pages/DashboardPage'
import { ExportPage } from './pages/ExportPage'
import { LoginPage } from './pages/LoginPage'
import { ObjectDetailPage } from './pages/ObjectDetailPage'
import { ObjectsPage } from './pages/ObjectsPage'
import { PartiesPage } from './pages/PartiesPage'
import { PrintPage } from './pages/PrintPage'
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

function clearReportUrlParams() {
  if (typeof window === 'undefined') return
  const params = new URLSearchParams(window.location.search)
  if (!params.has('report_tab')) return
  window.history.replaceState(null, '', window.location.pathname)
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

  useEffect(() => {
    let returnFocus: HTMLElement | null = null
    let lastOutsideFocus: HTMLElement | null = document.activeElement instanceof HTMLElement ? document.activeElement : null
    let activeModal: HTMLElement | null = null
    function rememberOutsideFocus(event: FocusEvent) {
      const target = event.target
      if (target instanceof HTMLElement && !target.closest('.modal-backdrop')) lastOutsideFocus = target
    }
    const observer = new MutationObserver(() => {
      const backdrops = document.querySelectorAll<HTMLElement>('.modal-backdrop')
      const modal = backdrops.item(backdrops.length - 1)?.querySelector<HTMLElement>('[role="dialog"]')
      if (modal && modal !== activeModal) {
        returnFocus = lastOutsideFocus
        activeModal = modal
      }
      if (modal && !modal.contains(document.activeElement)) {
        window.setTimeout(() => {
          const target = modal.querySelector<HTMLElement>('[autofocus], input:not(:disabled), select:not(:disabled), textarea:not(:disabled), button:not(:disabled), [tabindex]:not([tabindex="-1"])')
          target?.focus()
        }, 0)
      } else if (!modal && returnFocus) {
        returnFocus.focus()
        returnFocus = null
        activeModal = null
      }
    })
    observer.observe(document.body, { childList: true, subtree: true })
    window.addEventListener('focusin', rememberOutsideFocus)
    function closeTopModal(event: KeyboardEvent) {
      const backdrops = document.querySelectorAll<HTMLElement>('.modal-backdrop')
      const backdrop = backdrops.item(backdrops.length - 1)
      if (!backdrop) return
      const modal = backdrop.querySelector<HTMLElement>('[role="dialog"]')
      if (event.key === 'Tab' && modal) {
        const focusable = Array.from(modal.querySelectorAll<HTMLElement>('button:not(:disabled), input:not(:disabled), select:not(:disabled), textarea:not(:disabled), a[href], [tabindex]:not([tabindex="-1"])'))
          .filter((element) => element.offsetParent !== null)
        if (!focusable.length) return
        const first = focusable[0]
        const last = focusable[focusable.length - 1]
        if (event.shiftKey && document.activeElement === first) {
          event.preventDefault()
          last.focus()
        } else if (!event.shiftKey && document.activeElement === last) {
          event.preventDefault()
          first.focus()
        }
        return
      }
      if (event.key !== 'Escape') return
      event.preventDefault()
      backdrop.dispatchEvent(new MouseEvent('mousedown', { bubbles: true }))
    }
    window.addEventListener('keydown', closeTopModal)
    return () => {
      observer.disconnect()
      window.removeEventListener('focusin', rememberOutsideFocus)
      window.removeEventListener('keydown', closeTopModal)
    }
  }, [])

  useEffect(() => {
    if (view !== 'reports' || objectId !== null) {
      clearReportUrlParams()
    }
  }, [objectId, view])

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
  const openReports = useCallback((tab = 'overview', extraParams?: Record<string, string | number | boolean | null | undefined>) => {
    setObjectId(null)
    if (typeof window !== 'undefined') {
      const params = new URLSearchParams()
      params.set('report_tab', tab)
      Object.entries(extraParams || {}).forEach(([key, value]) => {
        if (value === undefined || value === null || value === '') return
        params.set(key, String(value))
      })
      window.history.replaceState(null, '', `${window.location.pathname}?${params.toString()}`)
    }
    setView('reports')
  }, [])
  if (isLoading) return <main className="app-bootstrap-state"><LoadingState title="Запуск ДНК-реестра..." rows={4} /></main>
  if (!user) return <LoginPage onLogin={(username, password) => login.mutateAsync({ username, password }).then(() => undefined)} />
  let page = <DashboardPage onPartyOpen={openParty} onReportsOpen={openReports} />
  if (objectId) page = <ObjectDetailPage id={objectId} user={user} onBack={() => setObjectId(null)} onPartyOpen={openParty} />
  else if (view === 'dashboard') page = <DashboardPage onPartyOpen={openParty} onReportsOpen={openReports} />
  else if (view === 'parties') page = <PartiesPage user={user} onObjectOpen={setObjectId} onReportsOpen={openReports} initialPartyNo={partySelect} onInitialPartyHandled={() => setPartySelect(null)} />
  else if (view === 'objects') page = <ObjectsPage initialQuery={objectsQuery} partyFilter={partyFilter} onQueryChange={setObjectsQuery} onPartyFilterChange={setPartyFilter} onOpen={setObjectId} onPartyOpen={openParty} />
  else if (view === 'work-sessions') page = <WorkSessionsPage user={user} />
  else if (view === 'search') page = <SearchPage onObjectOpen={setObjectId} onPartyOpen={openPartyInParties} />
  else if (view === 'reports') page = <ReportsPage user={user} onPartyOpen={openPartyInParties} />
  else if (view === 'employees') page = <EmployeesPage user={user} />
  else if (view === 'print') page = <PrintPage />
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
