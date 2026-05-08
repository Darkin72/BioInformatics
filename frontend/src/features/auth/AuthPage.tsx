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
      <section className="auth-hero" aria-labelledby="auth-hero-title">
        <div className="brand auth-brand auth-hero-brand">
          <span className="brand-logo-frame auth-logo-frame">
            <img alt="Protein Function RT logo" className="brand-logo" src="/logo.svg" />
          </span>
          <div>
            <strong>Protein Function RT</strong>
            <span>Realtime prediction console</span>
          </div>
        </div>

        <div className="auth-hero-copy">
          <p className="eyebrow">CAFA-6 secure inference</p>
          <h1 id="auth-hero-title">Clinical-grade protein function predictions</h1>
          <p>
            Review requests, submit protein sequences, and inspect the latest
            prediction outputs from one protected workspace.
          </p>
        </div>

        <div className="auth-insight-grid" aria-label="Platform highlights">
          <div>
            <span>JWT</span>
            <strong>Protected sessions</strong>
          </div>
          <div>
            <span>RT</span>
            <strong>Streaming inference</strong>
          </div>
          <div>
            <span>GO</span>
            <strong>Function labels</strong>
          </div>
        </div>
      </section>

      <section className="auth-panel" aria-labelledby="login-title">
        <div className="auth-panel-header">
          <p className="eyebrow">JWT access control</p>
          <h2 id="login-title">
            {mode === 'signIn' ? 'Welcome back' : 'Create user account'}
          </h2>
          <p>
            {mode === 'signIn'
              ? 'Sign in to continue to your prediction console.'
              : 'Create a standard user account for protein inference requests.'}
          </p>
        </div>

        <div
          className="auth-mode-switch"
          role="tablist"
          aria-label="Authentication mode"
        >
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
          <label className="field-label">
            <span>Username</span>
            <input
              autoComplete="username"
              onChange={(event) => setUsername(event.target.value)}
              placeholder="Enter your username"
              required
              value={username}
            />
          </label>

          <label className="field-label">
            <span>Password</span>
            <input
              autoComplete={mode === 'signIn' ? 'current-password' : 'new-password'}
              onChange={(event) => setPassword(event.target.value)}
              placeholder="Enter your password"
              required
              type="password"
              value={password}
            />
          </label>

          {mode === 'createAccount' ? (
            <label className="field-label">
              <span>Repeat password</span>
              <input
                autoComplete="new-password"
                onChange={(event) => setRepeatPassword(event.target.value)}
                placeholder="Confirm your password"
                required
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
          <p>New accounts are created as user. Admin credentials are loaded from .env.</p>
        </div>
      </section>
    </main>
  )
}
