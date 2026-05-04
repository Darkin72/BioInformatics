import { useState } from 'react'
import type { FormEvent } from 'react'
import { ErrorState } from '../../components/ErrorState'
import type { AuthUser } from '../../shared/types'
import { login, register } from './authApi'

interface AuthPageProps {
  onAuthenticated: (user: AuthUser) => void
}

export function AuthPage({ onAuthenticated }: AuthPageProps) {
  const [mode, setMode] = useState<'signIn' | 'createAccount'>('signIn')
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [repeatPassword, setRepeatPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [isSubmitting, setIsSubmitting] = useState(false)

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setError(null)
    setIsSubmitting(true)

    try {
      if (mode === 'createAccount' && password !== repeatPassword) {
        throw new Error('Passwords do not match.')
      }

      const response =
        mode === 'signIn'
          ? await login({ username, password })
          : await register({
              username,
              password,
            })
      onAuthenticated(response.user)
    } catch (authError) {
      setError(
        authError instanceof Error ? authError.message : 'Unable to authenticate.',
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
          <h1 id="login-title">
            {mode === 'signIn' ? 'Sign in' : 'Create user account'}
          </h1>
        </div>

        <div className="auth-mode-switch" role="tablist" aria-label="Authentication mode">
          <button
            aria-selected={mode === 'signIn'}
            className={mode === 'signIn' ? 'active' : ''}
            onClick={() => {
              setMode('signIn')
              setError(null)
            }}
            role="tab"
            type="button"
          >
            Sign in
          </button>
          <button
            aria-selected={mode === 'createAccount'}
            className={mode === 'createAccount' ? 'active' : ''}
            onClick={() => {
              setMode('createAccount')
              setError(null)
            }}
            role="tab"
            type="button"
          >
            Create account
          </button>
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
              autoComplete={mode === 'signIn' ? 'current-password' : 'new-password'}
              onChange={(event) => setPassword(event.target.value)}
              type="password"
              value={password}
            />
          </label>

          {mode === 'createAccount' ? (
            <label>
              Repeat password
              <input
                autoComplete="new-password"
                onChange={(event) => setRepeatPassword(event.target.value)}
                type="password"
                value={repeatPassword}
              />
            </label>
          ) : null}

          {error ? <ErrorState message={error} /> : null}

          <button className="primary-button" disabled={isSubmitting} type="submit">
            {isSubmitting
              ? mode === 'signIn'
                ? 'Signing in...'
                : 'Creating account...'
              : mode === 'signIn'
                ? 'Sign in'
                : 'Create account'}
          </button>
        </form>

        <div className="demo-accounts">
          <span>Access model</span>
          <code>New accounts are created as user.</code>
          <code>Admin credentials are loaded from .env.</code>
        </div>
      </section>
    </main>
  )
}
