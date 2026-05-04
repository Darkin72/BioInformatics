import { apiRequest, getAccessToken, setAccessToken } from '../../shared/apiClient'
import type {
  AuthUser,
  LoginCredentials,
  LoginResponse,
  RegisterCredentials,
} from '../../shared/types'

export async function login(credentials: LoginCredentials) {
  const response = await apiRequest<LoginResponse>('/api/auth/login', {
    method: 'POST',
    body: JSON.stringify(credentials),
  })

  setAccessToken(response.access_token)
  return response
}

export async function register(credentials: RegisterCredentials) {
  const response = await apiRequest<LoginResponse>('/api/auth/register', {
    method: 'POST',
    body: JSON.stringify(credentials),
  })

  setAccessToken(response.access_token)
  return response
}

export async function logout() {
  try {
    if (getAccessToken()) {
      await apiRequest<{ status: string }>('/api/auth/logout', {
        method: 'POST',
      })
    }
  } finally {
    setAccessToken(null)
  }
}

export async function getCurrentUser(): Promise<AuthUser | null> {
  const token = getAccessToken()

  if (!token) {
    return null
  }

  try {
    return await apiRequest<AuthUser>('/api/auth/me')
  } catch {
    setAccessToken(null)
    return null
  }
}

export function canCreateInferenceRequest(user: AuthUser) {
  return user.roles.some((role) => role === 'user' || role === 'admin')
}
