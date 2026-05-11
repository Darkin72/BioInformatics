import { useEffect, useState } from 'react'
import type { FormEvent } from 'react'
import { ErrorState } from '../../components/ErrorState'
import { API_BASE_URL } from '../../shared/apiClient'
import type { AuthUser } from '../../shared/types'
import { login, register } from './authApi'

interface AuthPageProps {
  onAuthenticated: (user: AuthUser) => void
}

const RESEARCH_QUOTES = [
  'From sequence batches to GO terms in one continuous flow.',
  'Track every inference run before it becomes a result.',
  'Keep protein function prediction close to the data.',
]

export function AuthPage({ onAuthenticated }: AuthPageProps) {
  const [mode, setMode] = useState<'signIn' | 'createAccount'>('signIn')
  const [username, setUsername] = useState('admin')
  const [password, setPassword] = useState('')
  const [repeatPassword, setRepeatPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [showPassword, setShowPassword] = useState(false)
  const [activeQuoteIndex, setActiveQuoteIndex] = useState(0)
  const [backendStatus, setBackendStatus] = useState<
    'checking' | 'online' | 'offline'
  >('checking')

  const platformCards = [
    {
      icon: 'database',
      label: 'Cassandra',
      text: 'Sequence store',
    },
    {
      icon: 'queue',
      label: 'Kafka',
      text: 'Job queue',
    },
    {
      icon: 'spark',
      label: 'Spark',
      text: 'Inference engine',
    },
    {
      icon: 'go',
      label: 'GO Labels',
      text: 'Ontology annotations',
    },
  ]

  const pipelineSteps = [
    { icon: 'file', label: 'FASTA', sublabel: 'Upload' },
    { icon: 'queue', label: 'Kafka', sublabel: 'Queue' },
    { icon: 'spark', label: 'Spark', sublabel: 'Inference' },
    { icon: 'database', label: 'Cassandra', sublabel: 'Store' },
  ]

  useEffect(() => {
    const controller = new AbortController()
    const timeout = window.setTimeout(() => controller.abort(), 2500)

    fetch(`${API_BASE_URL}/health`, { signal: controller.signal })
      .then((response) => {
        setBackendStatus(response.ok ? 'online' : 'offline')
      })
      .catch(() => setBackendStatus('offline'))
      .finally(() => window.clearTimeout(timeout))

    return () => {
      controller.abort()
      window.clearTimeout(timeout)
    }
  }, [])

  useEffect(() => {
    const interval = window.setInterval(() => {
      setActiveQuoteIndex((index) => (index + 1) % RESEARCH_QUOTES.length)
    }, 3600)

    return () => window.clearInterval(interval)
  }, [])

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
          <p className="eyebrow auth-streaming-label">
            <span aria-hidden="true" />
            CAFA-6 streaming platform
          </p>
          <h1 id="auth-hero-title">
            Protein function prediction <span>workspace</span>
          </h1>
          <p>
            Submit FASTA batches, monitor streaming inference, and inspect
            GO-term predictions from one protected research workspace.
          </p>
          <div className="auth-quote-rotator" aria-live="polite">
            <blockquote key={RESEARCH_QUOTES[activeQuoteIndex]}>
              {RESEARCH_QUOTES[activeQuoteIndex]}
            </blockquote>
          </div>
        </div>

        <div className="auth-platform-grid" aria-label="Platform highlights">
          {platformCards.map((card) => (
            <article className="auth-platform-card" key={card.label}>
              <Icon name={card.icon} />
              <div>
                <h2>{card.label}</h2>
                <p>{card.text}</p>
              </div>
            </article>
          ))}
        </div>
      </section>

      <section className="auth-panel" aria-labelledby="login-title">
        <div className={`auth-online ${backendStatus}`}>
          <span aria-hidden="true" />
          {backendStatus === 'checking'
            ? 'Checking backend'
            : backendStatus === 'online'
              ? 'Backend online'
              : 'Backend unavailable'}
        </div>

        <div className="auth-panel-header">
          <p className="eyebrow">Secure access</p>
          <h2 id="login-title">
            {mode === 'signIn' ? 'Welcome back' : 'Create new account'}
          </h2>
          <p>
            {mode === 'signIn'
              ? 'Access protected prediction jobs, batch uploads, and streaming result monitors.'
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
              setUsername('admin')
              setPassword('')
              setRepeatPassword('')
              setError(null)
            }}
            role="tab"
            type="button"
          >
            <Icon name="shield" />
            Login
          </button>
          <button
            aria-selected={mode === 'createAccount'}
            className={mode === 'createAccount' ? 'active' : ''}
            onClick={() => {
              setMode('createAccount')
              setUsername('')
              setPassword('')
              setRepeatPassword('')
              setError(null)
            }}
            role="tab"
            type="button"
          >
            <Icon name="user" />
            Create new account
          </button>
        </div>

        <form className="auth-form" onSubmit={handleSubmit}>
          <label className="field-label">
            <span>Username</span>
            <div className="auth-input-frame">
              <Icon name="user" />
              <input
                autoComplete="username"
                onChange={(event) => setUsername(event.target.value)}
                placeholder={mode === 'signIn' ? 'admin' : 'Choose a username'}
                required
                value={username}
              />
            </div>
          </label>

          <label className="field-label">
            <span>Password</span>
            <div className="auth-input-frame">
              <Icon name="lock" />
              <input
                autoComplete={mode === 'signIn' ? 'current-password' : 'new-password'}
                onChange={(event) => setPassword(event.target.value)}
                placeholder="Enter your password"
                required
                type={showPassword ? 'text' : 'password'}
                value={password}
              />
              <button
                aria-label={showPassword ? 'Hide password' : 'Show password'}
                className="auth-icon-button"
                onClick={() => setShowPassword((value) => !value)}
                type="button"
              >
                <Icon name={showPassword ? 'eyeOff' : 'eye'} />
              </button>
            </div>
          </label>

          {mode === 'createAccount' ? (
            <label className="field-label">
              <span>Repeat password</span>
              <div className="auth-input-frame">
                <Icon name="lock" />
                <input
                  autoComplete="new-password"
                  onChange={(event) => setRepeatPassword(event.target.value)}
                  placeholder="Confirm your password"
                  required
                  type={showPassword ? 'text' : 'password'}
                  value={repeatPassword}
                />
              </div>
            </label>
          ) : null}

          {error ? <ErrorState message={error} /> : null}

          <button className="primary-button" disabled={isSubmitting} type="submit">
            <Icon name="lock" />
            {isSubmitting
              ? mode === 'signIn'
                ? 'Signing in...'
                : 'Creating account...'
              : mode === 'signIn'
                ? 'Login'
                : 'Create new account'}
          </button>
        </form>

        <div className="auth-pipeline" aria-label="Streaming pipeline">
          {pipelineSteps.map((step) => (
            <div className="auth-pipeline-step" key={step.label}>
              <Icon name={step.icon} />
              <span>
                <strong>{step.label}</strong>
                {step.sublabel}
              </span>
            </div>
          ))}
        </div>
      </section>
    </main>
  )
}

function Icon({ name }: { name: string }) {
  if (name === 'database') {
    return (
      <svg aria-hidden="true" viewBox="0 0 24 24">
        <ellipse cx="12" cy="5" rx="8" ry="3" />
        <path d="M4 5v14c0 1.7 3.6 3 8 3s8-1.3 8-3V5" />
        <path d="M4 12c0 1.7 3.6 3 8 3s8-1.3 8-3" />
      </svg>
    )
  }

  if (name === 'queue') {
    return (
      <svg aria-hidden="true" viewBox="0 0 24 24">
        <circle cx="6" cy="5" r="2.5" />
        <circle cx="18" cy="12" r="2.5" />
        <circle cx="6" cy="19" r="2.5" />
        <path d="M8.4 6.2 15.7 10.8M8.4 17.8l7.3-4.6" />
      </svg>
    )
  }

  if (name === 'spark') {
    return (
      <svg aria-hidden="true" viewBox="0 0 24 24">
        <path d="m12 3 2.8 5.7 6.2.9-4.5 4.4 1.1 6.1L12 17.2 6.4 20.1 7.5 14 3 9.6l6.2-.9L12 3Z" />
      </svg>
    )
  }

  if (name === 'go') {
    return (
      <svg aria-hidden="true" viewBox="0 0 24 24">
        <circle cx="7" cy="7" r="3" />
        <circle cx="17" cy="7" r="3" />
        <circle cx="12" cy="17" r="3" />
        <path d="M9.5 8.7 11 14.2" />
        <path d="M14.5 8.7 13 14.2" />
        <path d="M10 7h4" />
      </svg>
    )
  }

  if (name === 'shield') {
    return (
      <svg aria-hidden="true" viewBox="0 0 24 24">
        <path d="M12 3 5 6v5.6c0 4.4 2.9 7.5 7 9.4 4.1-1.9 7-5 7-9.4V6l-7-3Z" />
        <path d="m9 12 2 2 4-5" />
      </svg>
    )
  }

  if (name === 'user') {
    return (
      <svg aria-hidden="true" viewBox="0 0 24 24">
        <circle cx="12" cy="8" r="3" />
        <path d="M5 20c.8-4 3.1-6 7-6s6.2 2 7 6" />
      </svg>
    )
  }

  if (name === 'lock') {
    return (
      <svg aria-hidden="true" viewBox="0 0 24 24">
        <rect x="5" y="10" width="14" height="10" rx="2" />
        <path d="M8 10V7a4 4 0 0 1 8 0v3" />
      </svg>
    )
  }

  if (name === 'eyeOff') {
    return (
      <svg aria-hidden="true" viewBox="0 0 24 24">
        <path d="M3 3l18 18" />
        <path d="M10.6 10.6a2 2 0 0 0 2.8 2.8" />
        <path d="M7.4 7.8C5.6 8.8 4.1 10.2 3 12c2.2 3.5 5.2 5.3 9 5.3 1.2 0 2.3-.2 3.3-.6" />
        <path d="M11.1 6.8c.3 0 .6-.1.9-.1 3.8 0 6.8 1.8 9 5.3-.6 1-1.4 1.9-2.2 2.6" />
      </svg>
    )
  }

  if (name === 'file') {
    return (
      <svg aria-hidden="true" viewBox="0 0 24 24">
        <path d="M6 3h8l4 4v14H6V3Z" />
        <path d="M14 3v5h5" />
      </svg>
    )
  }

  return (
    <svg aria-hidden="true" viewBox="0 0 24 24">
      <path d="M2 12s3.5-6 10-6 10 6 10 6-3.5 6-10 6S2 12 2 12Z" />
      <circle cx="12" cy="12" r="3" />
    </svg>
  )
}
