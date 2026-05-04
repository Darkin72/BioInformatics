export const API_BASE_URL =
  (import.meta.env.VITE_API_BASE_URL as string | undefined) ||
  'http://localhost:8000'
export const EVENTS_BASE_URL =
  (import.meta.env.VITE_EVENTS_BASE_URL as string | undefined) ||
  'http://localhost:8003'
const TOKEN_STORAGE_KEY = 'protein-function.access-token'

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
  const headers = new Headers(options.headers)
  if (!headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json')
  }

  if (accessToken && !headers.has('Authorization')) {
    headers.set('Authorization', `Bearer ${accessToken}`)
  }

  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...options,
    headers,
  })

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
