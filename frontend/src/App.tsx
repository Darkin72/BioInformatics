import { useEffect, useMemo, useState } from 'react'
import { DashboardPage } from './features/dashboard/DashboardPage'
import { LatestPredictionPage } from './features/predictions/LatestPredictionPage'
import { RequestStatusPage } from './features/requests/RequestStatusPage'
import { SubmitProteinPage } from './features/submitProtein/SubmitProteinPage'
import './App.css'

type Route =
  | { name: 'dashboard' }
  | { name: 'submit' }
  | { name: 'request'; requestId: string }
  | { name: 'latestPrediction'; proteinId?: string }

const navItems = [
  { label: 'Overview', path: '/' },
  { label: 'Submit', path: '/submit' },
  { label: 'Requests', path: '/requests/demo-processing-001' },
  { label: 'Predictions', path: '/proteins/P12345/latest' },
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

  const route = useMemo(() => parseRoute(pathname), [pathname])

  function navigate(path: string) {
    window.history.pushState(null, '', path)
    setPathname(window.location.pathname)
  }

  useEffect(() => {
    function handlePopState() {
      setPathname(window.location.pathname)
    }

    window.addEventListener('popstate', handlePopState)
    return () => window.removeEventListener('popstate', handlePopState)
  }, [])

  return (
    <div className="app-shell">
      <aside className="sidebar" aria-label="Main navigation">
        <div className="brand">
          <span className="brand-mark">PF</span>
          <div>
            <strong>Protein Function RT</strong>
            <span>Realtime prediction console</span>
          </div>
        </div>

        <nav className="main-nav">
          {navItems.map((item) => (
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
          <button
            className="secondary-button"
            onClick={() => navigate('/submit')}
            type="button"
          >
            New request
          </button>
        </header>

        {route.name === 'dashboard' && <DashboardPage navigate={navigate} />}
        {route.name === 'submit' && <SubmitProteinPage navigate={navigate} />}
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
