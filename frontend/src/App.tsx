import { useEffect, useMemo, useState } from 'react'
import { AuthPage } from './features/auth/AuthPage'
import {
  canCreateInferenceRequest,
  getCurrentUser,
  logout,
} from './features/auth/authApi'
import { DashboardPage } from './features/dashboard/DashboardPage'
import { LatestPredictionPage } from './features/predictions/LatestPredictionPage'
import { RequestStatusPage } from './features/requests/RequestStatusPage'
import { SubmitProteinPage } from './features/submitProtein/SubmitProteinPage'
import { LoadingState } from './components/LoadingState'
import type { AuthUser } from './shared/types'
import './App.css'

type Route =
  | { name: 'dashboard' }
  | { name: 'submit' }
  | { name: 'request'; requestId: string }
  | { name: 'latestPrediction'; proteinId?: string }

const navItems = [
  { label: 'Overview', path: '/' },
  { label: 'Submit', path: '/submit' },
  { label: 'Predictions', path: '/predictions' },
]

function parseRoute(pathname: string): Route {
  const requestMatch = pathname.match(/^\/requests\/([^/]+)$/)
  if (requestMatch) {
    return { name: 'request', requestId: decodeURIComponent(requestMatch[1]) }
  }

  const latestMatch = pathname.match(/^\/proteins\/([^/]+)\/latest$/)
  if (latestMatch) {
    return {
      name: 'latestPrediction',
      proteinId: decodeURIComponent(latestMatch[1]),
    }
  }

  if (pathname === '/submit') {
    return { name: 'submit' }
  }

  if (pathname === '/predictions') {
    return { name: 'latestPrediction' }
  }

  return { name: 'dashboard' }
}

function App() {
  const [pathname, setPathname] = useState(window.location.pathname)
  const [currentUser, setCurrentUser] = useState<AuthUser | null>(null)
  const [isAuthLoading, setIsAuthLoading] = useState(true)

  const route = useMemo(() => parseRoute(pathname), [pathname])
  const canSubmit = currentUser ? canCreateInferenceRequest(currentUser) : false
  const visibleNavItems = canSubmit
    ? navItems
    : navItems.filter((item) => item.path !== '/submit')

  function navigate(path: string) {
    window.history.pushState(null, '', path)
    setPathname(window.location.pathname)
  }

  async function handleLogout() {
    await logout()
    setCurrentUser(null)
    navigate('/')
  }

  useEffect(() => {
    function handlePopState() {
      setPathname(window.location.pathname)
    }

    window.addEventListener('popstate', handlePopState)
    return () => window.removeEventListener('popstate', handlePopState)
  }, [])

  useEffect(() => {
    let isActive = true

    getCurrentUser()
      .then((user) => {
        if (isActive) {
          setCurrentUser(user)
        }
      })
      .finally(() => {
        if (isActive) {
          setIsAuthLoading(false)
        }
      })

    return () => {
      isActive = false
    }
  }, [])

  if (isAuthLoading) {
    return (
      <div className="auth-loading">
        <LoadingState message="Checking session..." />
      </div>
    )
  }

  if (!currentUser) {
    return <AuthPage onAuthenticated={setCurrentUser} />
  }

  return (
    <div className="app-shell">
      <aside className="sidebar" aria-label="Main navigation">
        <div className="brand">
          <span className="brand-logo-frame">
            <img
              alt="Protein Function RT logo"
              className="brand-logo"
              src="/logo.svg"
            />
          </span>
          <div>
            <strong>Protein Function RT</strong>
            <span>Realtime prediction console</span>
          </div>
        </div>

        <nav className="main-nav">
          {visibleNavItems.map((item) => (
            <button
              className={
                pathname === item.path ||
                (item.path !== '/' && pathname.startsWith(item.path))
                  ? 'nav-item active'
                  : 'nav-item'
              }
              key={item.path}
              onClick={() => navigate(item.path)}
              type="button"
            >
              {item.label}
            </button>
          ))}
        </nav>
      </aside>

      <main className="workspace">
        <header className="topbar">
          <div>
            <p className="eyebrow">CAFA-6 streaming inference</p>
            <h1>Operations dashboard</h1>
          </div>
          <div className="topbar-actions">
            <div className="user-summary">
              <strong>{currentUser.display_name}</strong>
              <span>{currentUser.roles.join(', ')}</span>
            </div>
            {canSubmit ? (
              <button
                className="secondary-button"
                onClick={() => navigate('/submit')}
                type="button"
              >
                New request
              </button>
            ) : null}
            <button className="secondary-button" onClick={handleLogout} type="button">
              Sign out
            </button>
          </div>
        </header>

        {route.name === 'dashboard' && <DashboardPage navigate={navigate} />}
        {route.name === 'submit' &&
          (canSubmit ? (
            <SubmitProteinPage navigate={navigate} />
          ) : (
            <section className="state-box error-state">
              You need the operator or admin role to submit inference requests.
            </section>
          ))}
        {route.name === 'request' && (
          <RequestStatusPage navigate={navigate} requestId={route.requestId} />
        )}
        {route.name === 'latestPrediction' && (
          <LatestPredictionPage
            navigate={navigate}
            proteinId={route.proteinId}
          />
        )}
      </main>
    </div>
  )
}

export default App
