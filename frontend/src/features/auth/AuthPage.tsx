import { useState } from 'react'
import type { FormEvent } from 'react'
import { ErrorState } from '../../components/ErrorState'
import type { AuthUser } from '../../shared/types'
import { login } from './authApi'

interface AuthPageProps {
  onAuthenticated: (user: AuthUser) => void
}

export function AuthPage({ onAuthenticated }: AuthPageProps) {
  const [username, setUsername] = useState('operator')
  const [password, setPassword] = useState('operator123')
  const [error, setError] = useState<string | null>(null)
  const [isSubmitting, setIsSubmitting] = useState(false)

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setError(null)
    setIsSubmitting(true)

    try {
      const response = await login({ username, password })
      onAuthenticated(response.user)
    } catch (loginError) {
      setError(
        loginError instanceof Error ? loginError.message : 'Unable to sign in.',
      )
    } finally {
      setIsSubmitting(false)
    }
  }

  return (
    <main className="auth-shell">
      <section className="auth-panel" aria-labelledby="login-title">
        <div className="brand auth-brand">
          <span className="brand-logo-frame">
            <img
              alt="Protein Function RT logo"
              className="brand-logo"
              src="/logo.svg"
            />
          </span>
          <div>
            <strong>Protein Function RT</strong>
            <span>Secure prediction console</span>
          </div>
        </div>

        <div>
          <p className="eyebrow">JWT access control</p>
          <h1 id="login-title">Sign in</h1>
        </div>

        <form className="auth-form" onSubmit={handleSubmit}>
          <label>
            Username
            <input
              autoComplete="username"
              onChange={(event) => setUsername(event.target.value)}
              value={username}
            />
          </label>

          <label>
            Password
            <input
              autoComplete="current-password"
              onChange={(event) => setPassword(event.target.value)}
              type="password"
              value={password}
            />
          </label>

          {error ? <ErrorState message={error} /> : null}

          <button className="primary-button" disabled={isSubmitting} type="submit">
            {isSubmitting ? 'Signing in...' : 'Sign in'}
          </button>
        </form>

        <div className="demo-accounts">
          <span>Demo accounts</span>
          <code>viewer/viewer123</code>
          <code>operator/operator123</code>
          <code>admin/admin123</code>
        </div>
      </section>
    </main>
  )
}
