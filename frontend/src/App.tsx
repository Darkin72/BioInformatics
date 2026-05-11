import { useEffect, useMemo, useState } from 'react'
import { AuthPage } from './features/auth/AuthPage'
import { AdminRequestsPage } from './features/admin/AdminRequestsPage'
import { AdminUsersPage } from './features/admin/AdminUsersPage'
import {
  canCreateInferenceRequest,
  getCurrentUser,
  logout,
} from './features/auth/authApi'
import { DashboardPage } from './features/dashboard/DashboardPage'
import { LatestPredictionPage } from './features/predictions/LatestPredictionPage'
import { MyRequestsPage } from './features/requests/MyRequestsPage'
import {
  RequestProteinDetailPage,
  RequestStatusPage,
} from './features/requests/RequestStatusPage'
import { SubmitProteinPage } from './features/submitProtein/SubmitProteinPage'
import { LoadingState } from './components/LoadingState'
import type { AuthUser } from './shared/types'
import './App.css'

type Route =
  | { name: 'dashboard' }
  | { name: 'adminRequests' }
  | { name: 'adminUsers' }
  | { name: 'myRequests' }
  | { name: 'submit' }
  | { name: 'request'; requestId: string }
  | { name: 'requestProtein'; requestId: string; proteinId: string }
  | { name: 'latestPrediction'; proteinId?: string }

type IconName =
  | 'dashboard'
  | 'requests'
  | 'adminRequests'
  | 'users'
  | 'submit'
  | 'predictions'
  | 'sun'
  | 'moon'
  | 'logout'

const navItems = [
  { icon: 'dashboard', label: 'Overview', path: '/' },
  { icon: 'requests', label: 'My requests', path: '/my/requests' },
  {
    adminOnly: true,
    icon: 'adminRequests',
    label: 'Admin requests',
    path: '/admin/requests',
  },
  { adminOnly: true, icon: 'users', label: 'Admin users', path: '/admin/users' },
  { icon: 'submit', label: 'Predict', path: '/submit' },
  { icon: 'predictions', label: 'Search', path: '/predictions' },
] satisfies Array<{
  adminOnly?: boolean
  icon: IconName
  label: string
  path: string
}>

const iconPaths: Record<IconName, string[]> = {
  adminRequests: [
    'M8 7h8',
    'M8 12h8',
    'M8 17h5',
    'M5 3h14a1 1 0 0 1 1 1v16a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1Z',
  ],
  dashboard: ['M4 13h6V4H4v9Z', 'M14 20h6V4h-6v16Z', 'M4 20h6v-3H4v3Z'],
  logout: ['M10 17l5-5-5-5', 'M15 12H3', 'M21 4v16'],
  moon: ['M21 14.5A8.5 8.5 0 0 1 9.5 3a7 7 0 1 0 11.5 11.5Z'],
  predictions: [
    'M12 3 4 7v10l8 4 8-4V7l-8-4Z',
    'M4 7l8 4 8-4',
    'M12 11v10',
  ],
  requests: [
    'M7 3h10l3 3v15H7a3 3 0 0 1-3-3V6a3 3 0 0 1 3-3Z',
    'M14 3v5h6',
    'M8 13h8',
    'M8 17h5',
  ],
  submit: ['M12 19V5', 'M5 12l7-7 7 7', 'M5 21h14'],
  sun: [
    'M12 8a4 4 0 1 0 0 8 4 4 0 0 0 0-8Z',
    'M12 2v2',
    'M12 20v2',
    'M4.93 4.93l1.41 1.41',
    'M17.66 17.66l1.41 1.41',
    'M2 12h2',
    'M20 12h2',
    'M4.93 19.07l1.41-1.41',
    'M17.66 6.34l1.41-1.41',
  ],
  users: [
    'M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2',
    'M9 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8Z',
    'M22 21v-2a4 4 0 0 0-3-3.87',
    'M16 3.13a4 4 0 0 1 0 7.75',
  ],
}

function Icon({ name }: { name: IconName }) {
  return (
    <svg aria-hidden="true" className="ui-icon" viewBox="0 0 24 24">
      {iconPaths[name].map((path) => (
        <path d={path} key={path} />
      ))}
    </svg>
  )
}

function getPageTitle(route: Route) {
  const titles: Record<Route['name'], string> = {
    adminRequests: 'Admin requests',
    adminUsers: 'Admin users',
    dashboard: 'Operations dashboard',
    latestPrediction: 'Search',
    myRequests: 'My requests',
    requestProtein: 'Protein result',
    request: 'Request status',
    submit: 'Predict',
  }

  return titles[route.name]
}

function getPageEyebrow(route: Route) {
  return route.name === 'dashboard'
    ? 'CAFA-6 streaming inference'
    : 'Protein function prediction'
}

function getNavItemClass(pathname: string, path: string) {
  if (path === '/') {
    return pathname === path ? 'nav-item active' : 'nav-item'
  }

  return pathname.startsWith(path) ? 'nav-item active' : 'nav-item'
}

function parseRoute(pathname: string): Route {
  const requestProteinMatch = pathname.match(/^\/requests\/([^/]+)\/proteins\/([^/]+)$/)
  if (requestProteinMatch) {
    return {
      name: 'requestProtein',
      requestId: decodeURIComponent(requestProteinMatch[1]),
      proteinId: decodeURIComponent(requestProteinMatch[2]),
    }
  }

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

  if (pathname === '/my/requests') {
    return { name: 'myRequests' }
  }

  if (pathname === '/admin/requests') {
    return { name: 'adminRequests' }
  }

  if (pathname === '/admin/users') {
    return { name: 'adminUsers' }
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
  const [theme, setTheme] = useState<'dark' | 'light'>(() => {
    return localStorage.getItem('theme') === 'light' ? 'light' : 'dark'
  })

  const route = useMemo(() => parseRoute(pathname), [pathname])
  const canSubmit = currentUser ? canCreateInferenceRequest(currentUser) : false
  const isAdmin = currentUser?.roles.includes('admin') ?? false
  const visibleNavItems = canSubmit
    ? navItems
    : navItems.filter((item) => item.path !== '/submit')
  const roleNavItems = visibleNavItems.filter((item) => !item.adminOnly || isAdmin)

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

  useEffect(() => {
    document.documentElement.dataset.theme = theme
    localStorage.setItem('theme', theme)
  }, [theme])

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
    <div className="app-shell" data-theme={theme}>
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
          {roleNavItems.map((item) => (
            <button
              className={
                getNavItemClass(pathname, item.path)
              }
              key={item.path}
              onClick={() => navigate(item.path)}
              type="button"
            >
              <Icon name={item.icon} />
              <span>{item.label}</span>
            </button>
          ))}
        </nav>

        <div className="sidebar-footer">
          <button
            className="sidebar-action"
            onClick={() =>
              setTheme((currentTheme) =>
                currentTheme === 'dark' ? 'light' : 'dark',
              )
            }
            type="button"
          >
            <Icon name={theme === 'dark' ? 'sun' : 'moon'} />
            <span>{theme === 'dark' ? 'Light mode' : 'Dark mode'}</span>
          </button>
          <button className="sidebar-action" onClick={handleLogout} type="button">
            <Icon name="logout" />
            <span>Sign out</span>
          </button>
        </div>
      </aside>

      <main className="workspace">
        <header className="topbar">
          <div>
            <p className="eyebrow">{getPageEyebrow(route)}</p>
            <h1>{getPageTitle(route)}</h1>
          </div>
          <div className="topbar-actions">
            <div className="user-summary">
              <strong>{currentUser.username}</strong>
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
          </div>
        </header>

        {route.name === 'dashboard' && (
          <DashboardPage isAdmin={isAdmin} navigate={navigate} />
        )}
        {route.name === 'adminRequests' &&
          (isAdmin ? (
            <AdminRequestsPage navigate={navigate} />
          ) : (
            <section className="state-box error-state">
              You need the admin role to inspect all user requests.
            </section>
          ))}
        {route.name === 'adminUsers' &&
          (isAdmin ? (
            <AdminUsersPage />
          ) : (
            <section className="state-box error-state">
              You need the admin role to manage users.
            </section>
          ))}
        {route.name === 'myRequests' && <MyRequestsPage navigate={navigate} />}
        {route.name === 'submit' &&
          (canSubmit ? (
            <SubmitProteinPage navigate={navigate} />
          ) : (
            <section className="state-box error-state">
              You need the user or admin role to submit inference requests.
            </section>
          ))}
        {route.name === 'request' && (
          <RequestStatusPage
            isAdmin={isAdmin}
            navigate={navigate}
            requestId={route.requestId}
          />
        )}
        {route.name === 'requestProtein' && (
          <RequestProteinDetailPage
            navigate={navigate}
            proteinId={route.proteinId}
            requestId={route.requestId}
          />
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
