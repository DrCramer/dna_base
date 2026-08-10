import { LockKeyhole } from 'lucide-react'
import { FormEvent, useState } from 'react'

function staticPreviewWarning(): string | null {
  const { hostname, pathname } = window.location
  if (hostname.includes('codex-remote.invalid') || pathname.includes('codex-localhost-preview') || pathname.startsWith('/read/')) {
    return 'Открыта статическая preview-страница Codex без доступа к API. Откройте живой сервис: http://192.168.1.16:4001 или http://localhost:4001 на сервере.'
  }
  return null
}

export function LoginPage({ onLogin }: { onLogin: (username: string, password: string) => Promise<void> }) {
  const [username, setUsername] = useState('admin')
  const [password, setPassword] = useState('admin123')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const previewWarning = staticPreviewWarning()

  async function submit(event: FormEvent) {
    event.preventDefault()
    setLoading(true)
    setError('')
    try {
      await onLogin(username, password)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Не удалось войти')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="login-screen">
      <form className="login-panel" onSubmit={submit}>
        <div className="login-title"><LockKeyhole size={24} /><div><h1>Лабораторный реестр ДНК</h1><p>Система учёта объектов генетической лаборатории</p></div></div>
        {previewWarning && <div className="alert error">{previewWarning}</div>}
        <label>Логин<input value={username} onChange={(event) => setUsername(event.target.value)} autoComplete="username" /></label>
        <label>Пароль<input value={password} onChange={(event) => setPassword(event.target.value)} type="password" autoComplete="current-password" /></label>
        {error && <div className="alert error">{error}</div>}
        <button className="primary" disabled={loading}>{loading ? 'Вход...' : 'Войти'}</button>
      </form>
    </div>
  )
}
