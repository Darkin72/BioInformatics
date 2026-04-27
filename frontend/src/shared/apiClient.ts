const API_BASE_URL = import.meta.env.VITE_API_BASE_URL as string | undefined

export const isMockApi = !API_BASE_URL

export async function apiRequest<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  if (!API_BASE_URL) {
    throw new Error('API base URL is not configured')
  }

  const response = await fetch(`${API_BASE_URL}${path}`, {
    headers: {
      'Content-Type': 'application/json',
      ...options.headers,
    },
    ...options,
  })

  if (!response.ok) {
    const message = await response.text()
    throw new Error(message || `Request failed with ${response.status}`)
  }

  return response.json() as Promise<T>
}
