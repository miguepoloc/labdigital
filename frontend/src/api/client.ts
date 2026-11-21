/**
 * Cliente HTTP de la API v1.
 * - Cookies HttpOnly (`credentials: "include"`); el frontend nunca ve los tokens.
 * - CSRF: `X-Requested-With: labdigital` en toda petición que no sea GET/HEAD (contrato §2).
 * - Errores normalizados a `ApiError` (contrato §6).
 * - Renovación: ante un 401 se llama UNA vez a `POST /auth/refresh` (candado compartido: las peticiones
 *   concurrentes esperan la misma promesa) y se reintenta la petición original. Si la renovación falla,
 *   se notifica `onSessionExpired` (la app limpia la sesión y redirige a `/entrar?next=`).
 */
import { config } from '@/config'
import { ApiError, errorFromResponse } from './errors'

export type HttpMethod = 'GET' | 'HEAD' | 'POST' | 'PUT' | 'PATCH' | 'DELETE'

export interface RequestOptions {
  method?: HttpMethod
  /** Se serializa como JSON (salvo `FormData`, que se envía tal cual). */
  body?: unknown
  query?: Record<string, string | number | boolean | undefined | null>
  headers?: Record<string, string>
  signal?: AbortSignal
  /** `false` en endpoints de autenticación: un 401 no dispara la renovación (por defecto `true`). */
  refreshOn401?: boolean
  /** `false` para no redirigir al login si la sesión no se puede renovar (por defecto `true`). */
  redirectOnExpired?: boolean
}

export interface ApiClientHooks {
  /** Se llama cuando un 401 no se pudo resolver con `/auth/refresh`. */
  onSessionExpired?: () => void
}

const CSRF_HEADER = 'X-Requested-With'
const CSRF_VALUE = 'labdigital'
const SAFE_METHODS: ReadonlySet<string> = new Set(['GET', 'HEAD'])

let hooks: ApiClientHooks = {}
let refreshInFlight: Promise<boolean> | null = null
/** Se incrementa con cada renovación exitosa; sirve para no renovar dos veces por la misma caducidad. */
let refreshGeneration = 0

export function configureApi(next: ApiClientHooks): void {
  hooks = { ...hooks, ...next }
}

/** Sólo para tests. */
export function resetApiClient(): void {
  hooks = {}
  refreshInFlight = null
  refreshGeneration = 0
}

function origin(): string {
  return typeof window !== 'undefined' && window.location
    ? window.location.origin
    : 'http://localhost'
}

export function apiUrl(path: string, query?: RequestOptions['query']): string {
  const url = new URL(config.apiBase + (path.startsWith('/') ? path : `/${path}`), origin())
  if (query) {
    for (const [k, v] of Object.entries(query)) {
      if (v !== undefined && v !== null) url.searchParams.set(k, String(v))
    }
  }
  return url.toString()
}

async function send(path: string, opts: RequestOptions): Promise<Response> {
  const method = opts.method ?? 'GET'
  const headers: Record<string, string> = { Accept: 'application/json', ...opts.headers }
  let body: BodyInit | undefined
  if (opts.body !== undefined) {
    if (opts.body instanceof FormData) {
      body = opts.body
    } else {
      headers['Content-Type'] = 'application/json'
      body = JSON.stringify(opts.body)
    }
  }
  if (!SAFE_METHODS.has(method)) headers[CSRF_HEADER] = CSRF_VALUE
  try {
    return await fetch(apiUrl(path, opts.query), {
      method,
      headers,
      body,
      credentials: 'include',
      signal: opts.signal,
    })
  } catch (e) {
    if (e instanceof DOMException && e.name === 'AbortError') throw e
    throw new ApiError({ status: 0, code: 'network_error', message: 'network_error' })
  }
}

/**
 * Serializa la renovación entre pestañas con Web Locks (`ld-refresh`, contrato §6.1); sin Web Locks, sólo el
 * candado por pestaña (`refreshInFlight`).
 */
function withRefreshLock<T>(fn: () => Promise<T>): Promise<T> {
  const locks = typeof navigator !== 'undefined' ? navigator.locks : undefined
  if (locks && typeof locks.request === 'function')
    return locks.request('ld-refresh', fn) as unknown as Promise<T>
  return fn()
}

/**
 * Renueva la sesión con `POST /auth/refresh`. Las llamadas concurrentes comparten la misma promesa.
 * Devuelve `true` si el servidor emitió cookies nuevas.
 */
export function refreshSession(): Promise<boolean> {
  if (!refreshInFlight) {
    refreshInFlight = withRefreshLock(() => send('/auth/refresh', { method: 'POST' }))
      .then((res) => {
        if (res.ok) refreshGeneration++
        return res.ok
      })
      .catch(() => false)
      .finally(() => {
        refreshInFlight = null
      })
  }
  return refreshInFlight
}

/**
 * Un 401 con un código de dominio (p. ej. contraseña actual incorrecta en `POST /me/password`) no es una
 * sesión caducada: no debe disparar la renovación. PROPUESTA AL CONTRATO: fijar el código del 401 por
 * sesión ausente/caducada (p. ej. `unauthenticated`) y usar 400/403 para credenciales incorrectas
 * fuera del login.
 */
const NON_SESSION_401_CODES: ReadonlySet<string> = new Set(['invalid_credentials'])

async function isSessionExpired401(res: Response): Promise<boolean> {
  if (res.status !== 401) return false
  try {
    const body = (await res.clone().json()) as { error?: { code?: unknown } }
    const code = body?.error?.code
    return !(typeof code === 'string' && NON_SESSION_401_CODES.has(code))
  } catch {
    return true
  }
}

async function parse<T>(res: Response): Promise<T> {
  if (res.status === 204 || res.status === 202 || res.headers.get('Content-Length') === '0') {
    // 202 del contrato no trae cuerpo útil; si lo trae y es JSON, se devuelve igualmente.
    const text = await res.text()
    return (text ? JSON.parse(text) : undefined) as T
  }
  const type = res.headers.get('Content-Type') ?? ''
  if (type.includes('application/json')) return (await res.json()) as T
  return (await res.text()) as unknown as T
}

/** Petición genérica. Lanza `ApiError` si la respuesta no es 2xx. */
export async function request<T = unknown>(path: string, opts: RequestOptions = {}): Promise<T> {
  const generation = refreshGeneration
  let res = await send(path, opts)

  if (opts.refreshOn401 !== false && (await isSessionExpired401(res))) {
    // Si otra petición ya renovó la sesión después de que saliera ésta, basta con reintentar.
    const renewed = generation !== refreshGeneration || (await refreshSession())
    if (renewed) res = await send(path, opts)
    if (opts.redirectOnExpired !== false && (await isSessionExpired401(res))) {
      hooks.onSessionExpired?.()
    }
  }

  if (!res.ok) throw await errorFromResponse(res)
  return parse<T>(res)
}

export const api = {
  get: <T>(path: string, opts?: Omit<RequestOptions, 'method' | 'body'>) =>
    request<T>(path, { ...opts, method: 'GET' }),
  post: <T>(path: string, body?: unknown, opts?: Omit<RequestOptions, 'method' | 'body'>) =>
    request<T>(path, { ...opts, method: 'POST', body }),
  put: <T>(path: string, body?: unknown, opts?: Omit<RequestOptions, 'method' | 'body'>) =>
    request<T>(path, { ...opts, method: 'PUT', body }),
  patch: <T>(path: string, body?: unknown, opts?: Omit<RequestOptions, 'method' | 'body'>) =>
    request<T>(path, { ...opts, method: 'PATCH', body }),
  delete: <T>(path: string, opts?: Omit<RequestOptions, 'method' | 'body'>) =>
    request<T>(path, { ...opts, method: 'DELETE' }),
}
