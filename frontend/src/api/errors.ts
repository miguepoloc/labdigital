import type { ApiErrorBody, ErrorCode } from './types'

/** Error normalizado de la API (contrato §6) o del transporte. */
export class ApiError extends Error {
  readonly status: number
  readonly code: ErrorCode
  readonly details?: Record<string, unknown>
  /** Segundos a esperar si el servidor mandó `Retry-After` (p. ej. `rate_limited`). */
  readonly retryAfter?: number

  constructor(opts: {
    status: number
    code: ErrorCode
    message: string
    details?: Record<string, unknown>
    retryAfter?: number
  }) {
    super(opts.message)
    this.name = 'ApiError'
    this.status = opts.status
    this.code = opts.code
    this.details = opts.details
    this.retryAfter = opts.retryAfter
  }
}

export function isApiError(e: unknown): e is ApiError {
  return e instanceof ApiError
}

function isErrorBody(v: unknown): v is ApiErrorBody {
  if (!v || typeof v !== 'object') return false
  const err = (v as { error?: unknown }).error
  return (
    !!err &&
    typeof err === 'object' &&
    typeof (err as { code?: unknown }).code === 'string' &&
    typeof (err as { message?: unknown }).message === 'string'
  )
}

/** `Retry-After` puede ser segundos o una fecha HTTP. Devuelve segundos (≥ 0) o undefined. */
export function parseRetryAfter(
  value: string | null,
  now: number = Date.now(),
): number | undefined {
  if (!value) return undefined
  const trimmed = value.trim()
  if (/^\d+$/.test(trimmed)) return Number(trimmed)
  const date = Date.parse(trimmed)
  if (Number.isNaN(date)) return undefined
  return Math.max(0, Math.ceil((date - now) / 1000))
}

function fallbackCode(status: number): ErrorCode {
  switch (status) {
    case 401:
      return 'unauthenticated'
    case 403:
      return 'forbidden'
    case 404:
      return 'not_found'
    case 413:
      return 'payload_too_large'
    case 422:
      return 'validation_error'
    case 429:
      return 'rate_limited'
    default:
      return 'unknown'
  }
}

/** Convierte una respuesta no-OK en `ApiError` siguiendo el formato del contrato §6. */
export async function errorFromResponse(res: Response): Promise<ApiError> {
  const retryAfter = parseRetryAfter(res.headers.get('Retry-After'))
  let body: unknown = null
  try {
    const text = await res.text()
    body = text ? JSON.parse(text) : null
  } catch {
    body = null
  }
  if (isErrorBody(body)) {
    return new ApiError({
      status: res.status,
      code: body.error.code,
      message: body.error.message,
      details: body.error.details,
      retryAfter,
    })
  }
  return new ApiError({
    status: res.status,
    code: fallbackCode(res.status),
    message: `HTTP ${res.status}`,
    retryAfter,
  })
}
