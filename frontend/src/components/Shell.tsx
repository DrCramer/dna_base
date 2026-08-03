import { BarChart3, ChevronDown, ChevronRight, ClipboardList, Database, FileDown, FileText, Home, LogOut, Minus, Monitor, Moon, PanelLeftClose, PanelLeftOpen, Plus, Printer, RotateCcw, Search, Sun, Upload, Users, Waves } from 'lucide-react'
import { useEffect, useState } from 'react'
import type { ReactNode } from 'react'
import type { User } from '../api/types'

interface ShellProps {
  user: User
  active: string
  onNavigate: (view: string) => void
  onLogout: () => void
  theme: 'light' | 'dark'
  themeMode: 'auto' | 'light' | 'dark'
  onTheme: () => void
  uiScale: number
  onScaleDown: () => void
  onScaleUp: () => void
  onScaleReset: () => void
  children: ReactNode
}

const sidebarStorageKey = 'dna_registry.sidebar_collapsed'

function storedSidebarCollapsed() {
  if (typeof window === 'undefined') return false
  return window.localStorage.getItem(sidebarStorageKey) === 'true'
}

export function Shell({ user, active, onNavigate, onLogout, theme, themeMode, onTheme, uiScale, onScaleDown, onScaleUp, onScaleReset, children }: ShellProps) {
  const canEdit = user.role !== 'viewer'
  const [isSidebarCollapsed, setIsSidebarCollapsed] = useState(storedSidebarCollapsed)
  const importViews = ['registry-import', 'rt-import', 'electrophoresis-import']
  const [isImportOpen, setIsImportOpen] = useState(() => importViews.includes(active))
  const ThemeIcon = themeMode === 'auto' ? Monitor : theme === 'light' ? Moon : Sun
  const themeLabel = themeMode === 'auto' ? 'Тема: авто' : theme === 'light' ? 'Тема: светлая' : 'Тема: тёмная'
  const CollapseIcon = isSidebarCollapsed ? PanelLeftOpen : PanelLeftClose
  const collapseTitle = isSidebarCollapsed ? 'Развернуть меню' : 'Свернуть меню'
  useEffect(() => {
    window.localStorage.setItem(sidebarStorageKey, String(isSidebarCollapsed))
  }, [isSidebarCollapsed])
  useEffect(() => {
    if (importViews.includes(active)) setIsImportOpen(true)
  }, [active])
  const workItems = [
    { id: 'dashboard', label: 'Главная', icon: Home, visible: true },
    { id: 'parties', label: 'Партии', icon: ClipboardList, visible: true },
    { id: 'objects', label: 'Объекты', icon: Database, visible: true },
    { id: 'work-sessions', label: 'Массовое заполнение', icon: ClipboardList, visible: canEdit },
    { id: 'search', label: 'Поиск', icon: Search, visible: true }
  ]
  const controlItems = [
    { id: 'reports', label: 'Отчёты', icon: BarChart3, visible: true },
    { id: 'print', label: 'Печать DOCX', icon: Printer, visible: true }
  ]
  const adminItems = [
    { id: 'employees', label: 'Справочники', icon: Users, visible: true }
  ]
  const importItems = [
    { id: 'registry-import', label: 'Реестр', icon: Upload },
    { id: 'rt-import', label: 'RT', icon: Waves },
    { id: 'electrophoresis-import', label: 'Форез', icon: FileText }
  ]
  const ImportToggleIcon = isImportOpen ? ChevronDown : ChevronRight
  const isImportActive = importViews.includes(active)
  function toggleImportGroup() {
    if (isSidebarCollapsed) {
      setIsSidebarCollapsed(false)
      setIsImportOpen(true)
      return
    }
    setIsImportOpen((value) => !value)
  }
  return (
    <div className={`app-shell${isSidebarCollapsed ? ' sidebar-collapsed' : ''}`}>
      <aside className="sidebar">
        <div className="brand">
          <div className="brand-main">
            <Search size={22} />
            <div>
              <strong>ДНК реестр</strong>
              <span>{user.username} · {user.role}</span>
            </div>
          </div>
          <button
            type="button"
            className="sidebar-collapse"
            onClick={() => setIsSidebarCollapsed((value) => !value)}
            aria-label={collapseTitle}
            title={collapseTitle}
          >
            <CollapseIcon size={18} />
          </button>
        </div>
        <nav>
          <span className="sidebar-caption">Работа</span>
          {workItems.filter((item) => item.visible).map((item) => {
            const Icon = item.icon
            return (
              <button key={item.id} className={active === item.id ? 'active' : ''} onClick={() => onNavigate(item.id)} title={item.label}>
                <Icon size={18} />
                <span>{item.label}</span>
              </button>
            )
          })}
          <span className="sidebar-caption">Контроль</span>
          {controlItems.filter((item) => item.visible).map((item) => {
            const Icon = item.icon
            return (
              <button key={item.id} className={active === item.id ? 'active' : ''} onClick={() => onNavigate(item.id)} title={item.label}>
                <Icon size={18} />
                <span>{item.label}</span>
              </button>
            )
          })}
          <span className="sidebar-caption">Администрирование</span>
          {adminItems.filter((item) => item.visible).map((item) => {
            const Icon = item.icon
            return (
              <button key={item.id} className={active === item.id ? 'active' : ''} onClick={() => onNavigate(item.id)} title={item.label}>
                <Icon size={18} />
                <span>{item.label}</span>
              </button>
            )
          })}
          {canEdit && (
            <div className={`sidebar-nav-group${isImportOpen ? ' is-open' : ''}${isImportActive ? ' is-active' : ''}`}>
              <button
                type="button"
                className={`sidebar-group-toggle${isImportActive ? ' active' : ''}`}
                onClick={toggleImportGroup}
                title="Импорт"
                aria-expanded={isImportOpen && !isSidebarCollapsed}
              >
                <Upload size={18} />
                <span>Импорт</span>
                <ImportToggleIcon className="sidebar-group-chevron" size={16} />
              </button>
              {isImportOpen && !isSidebarCollapsed && (
                <div className="sidebar-subnav">
                  {importItems.map((item) => {
                    const Icon = item.icon
                    return (
                      <button key={item.id} className={active === item.id ? 'active' : ''} onClick={() => onNavigate(item.id)} title={`Импорт ${item.label}`}>
                        <Icon size={16} />
                        <span>{item.label}</span>
                      </button>
                    )
                  })}
                </div>
              )}
            </div>
          )}
          <button className={active === 'export' ? 'active' : ''} onClick={() => onNavigate('export')} title="Экспорт">
            <FileDown size={18} />
            <span>Экспорт</span>
          </button>
        </nav>
        <div className="sidebar-actions">
          <div className="sidebar-scale" aria-label="Масштаб интерфейса">
            <button type="button" onClick={onScaleDown} title="Уменьшить масштаб" aria-label="Уменьшить масштаб"><Minus size={16} /></button>
            <button type="button" onClick={onScaleReset} title={`Сбросить масштаб (${Math.round(uiScale * 100)}%)`}><RotateCcw size={16} /><span>{Math.round(uiScale * 100)}%</span></button>
            <button type="button" onClick={onScaleUp} title="Увеличить масштаб" aria-label="Увеличить масштаб"><Plus size={16} /></button>
          </div>
          <button onClick={onTheme} title={themeLabel}><ThemeIcon size={18} /><span>{themeLabel}</span></button>
          <button onClick={onLogout} title="Выйти"><LogOut size={18} /><span>Выйти</span></button>
        </div>
      </aside>
      <main>{children}</main>
    </div>
  )
}
