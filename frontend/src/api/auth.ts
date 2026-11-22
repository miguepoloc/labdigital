import { api, refreshSession } from './client'
import type {
  ChangePasswordRequest,
  LoginRequest,
  Me,
  RegisterRequest,
  ResetPasswordRequest,
  Session,
  UpdateMeRequest,
} from './types'

/** Endpoints públicos de autenticación: un 401 aquí es una respuesta, no una sesión caducada. */
const PUBLIC = { refreshOn401: false, redirectOnExpired: false } as const

export const authApi = {
  register: (body: RegisterRequest) => api.post<void>('/auth/register', body, PUBLIC),
  verifyEmail: (token: string) => api.post<void>('/auth/verify-email', { token }, PUBLIC),
  login: (body: LoginRequest) => api.post<Me>('/auth/login', body, PUBLIC),
  refresh: refreshSession,
  logout: () => api.post<void>('/auth/logout', undefined, PUBLIC),
  forgotPassword: (email: string) => api.post<void>('/auth/forgot-password', { email }, PUBLIC),
  resetPassword: (body: ResetPasswordRequest) =>
    api.post<void>('/auth/reset-password', body, PUBLIC),
  resendVerification: (email: string) =>
    api.post<void>('/auth/resend-verification', { email }, PUBLIC),
  listSessions: () => api.get<Session[]>('/auth/sessions'),
  revokeSession: (id: string) => api.delete<void>(`/auth/sessions/${encodeURIComponent(id)}`),
  revokeOtherSessions: () => api.post<void>('/auth/sessions/revoke-others'),
}

export const meApi = {
  /** `redirectOnExpired: false`: la carga inicial no debe sacar de una página pública. */
  get: (opts?: { redirectOnExpired?: boolean }) =>
    api.get<Me>('/me', { redirectOnExpired: opts?.redirectOnExpired ?? true }),
  update: (body: UpdateMeRequest) => api.patch<Me>('/me', body),
  changePassword: (body: ChangePasswordRequest) => api.post<void>('/me/password', body),
}
