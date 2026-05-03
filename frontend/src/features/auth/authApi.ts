import {
  apiRequest,
  getAccessToken,
  isMockApi,
  setAccessToken,
} from '../../shared/apiClient'
import { mockGetCurrentUser, mockLogin, mockLogout } from '../../shared/mockApi'
import type {
  AuthUser,
  LoginCredentials,
  LoginResponse,
} from '../../shared/types'

export async function login(credentials: LoginCredentials) {
  const response = isMockApi
    ? await mockLogin(credentials)
    : await apiRequest<LoginResponse>('/api/auth/login', {
        method: 'POST',
        body: JSON.stringify(credentials),
      })

  setAccessToken(response.access_token)
  return response
}

export async function logout() {
  try {
    if (isMockApi) {
      await mockLogout()
    } else if (getAccessToken()) {
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
    return isMockApi
      ? await mockGetCurrentUser(token)
      : await apiRequest<AuthUser>('/api/auth/me')
  } catch {
    setAccessToken(null)
    return null
  }
}

export function canCreateInferenceRequest(user: AuthUser) {
  return user.roles.some((role) => role === 'operator' || role === 'admin')
}
