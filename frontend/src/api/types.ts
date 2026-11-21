/**
 * Tipos de la API v1 escritos a mano según docs/contrato-api.md.
 * TODO(LD-7): sustituir por tipos derivados de `schema.gen.ts` (`npm run gen:api`) cuando el OpenAPI exista.
 */

export type UUID = string
/** Fecha/hora ISO 8601 (UTC). */
export type ISODateTime = string

export type Role = 'admin' | 'user'

/** `GET /api/v1/me` (contrato §4). */
export interface Me {
  id: UUID
  email: string
  full_name: string
  role: Role
  email_verified: boolean
  created_at: ISODateTime
}

/**
 * `GET /api/v1/auth/sessions` → `Session[]`.
 * PROPUESTA AL CONTRATO: §4 no fija los campos de `Session`; el frontend asume éstos
 * (plan: "dispositivo/UA, IP, creada, último uso" + marca de la sesión actual).
 */
export interface Session {
  id: UUID
  user_agent: string | null
  ip: string | null
  created_at: ISODateTime
  last_used_at: ISODateTime
  current: boolean
}

// ---- Cuerpos de petición (contrato §4) ----

export interface RegisterRequest {
  email: string
  full_name: string
  password: string
  accept_data_policy: true
}

export interface LoginRequest {
  email: string
  password: string
  remember: boolean
}

export interface VerifyEmailRequest {
  token: string
}

export interface EmailRequest {
  email: string
}

export interface ResetPasswordRequest {
  token: string
  password: string
}

export interface UpdateMeRequest {
  full_name: string
}

export interface ChangePasswordRequest {
  current: string
  new: string
}

// ---- Errores (contrato §6) ----

/** Códigos fijos que usa el frontend. El backend puede enviar otros: se tratan como desconocidos. */
export type KnownErrorCode =
  | 'invalid_credentials'
  | 'email_not_verified'
  | 'account_inactive'
  | 'rate_limited'
  | 'csrf_rejected'
  | 'token_invalid'
  | 'version_conflict'
  | 'deadline_passed'
  | 'forbidden'
  | 'not_found'
  | 'validation_error'
  | 'payload_too_large'

/** Códigos que genera el propio cliente (no vienen del servidor). */
export type ClientErrorCode = 'network_error' | 'unauthenticated' | 'unknown'

export type ErrorCode = KnownErrorCode | ClientErrorCode | (string & {})

export interface ApiErrorBody {
  error: {
    code: string
    message: string
    details?: Record<string, unknown>
  }
}
