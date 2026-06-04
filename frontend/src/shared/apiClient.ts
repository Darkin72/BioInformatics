export const API_BASE_URL =
  (import.meta.env.VITE_API_BASE_URL as string | undefined) ||
  'http://localhost:8001'
export const EVENTS_BASE_URL =
  (import.meta.env.VITE_EVENTS_BASE_URL as string | undefined) ||
  'http://localhost:8004'
const TOKEN_STORAGE_KEY = 'protein-function.access-token'
const DEFAULT_REQUEST_TIMEOUT_MS = 10000

let accessToken = window.localStorage.getItem(TOKEN_STORAGE_KEY)

export function getAccessToken() {
  return accessToken
}

export function setAccessToken(token: string | null) {
  accessToken = token

  if (token) {
    window.localStorage.setItem(TOKEN_STORAGE_KEY, token)
  } else {
    window.localStorage.removeItem(TOKEN_STORAGE_KEY)
  }
}

export async function apiRequest<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const controller = new AbortController()
  const timeoutId = window.setTimeout(
    () => controller.abort(),
    DEFAULT_REQUEST_TIMEOUT_MS,
  )

  if (options.signal) {
    options.signal.addEventListener('abort', () => controller.abort(), { once: true })
  }

  const headers = new Headers(options.headers)
  if (!headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json')
  }

  if (accessToken && !headers.has('Authorization')) {
    headers.set('Authorization', `Bearer ${accessToken}`)
  }

  let response: Response
  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      ...options,
      headers,
      signal: controller.signal,
    })
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') {
      throw new Error('Request timed out. Please check the API service.')
    }
    throw error
  } finally {
    window.clearTimeout(timeoutId)
  }

  if (!response.ok) {
    if (response.status === 401) {
      setAccessToken(null)
    }

    let message = await response.text()
    try {
      const payload = JSON.parse(message) as { detail?: string }
      message = payload.detail ?? message
    } catch {
      // Keep the plain-text response body.
    }

    throw new Error(message || `Request failed with ${response.status}`)
  }

  return response.json() as Promise<T>
}
