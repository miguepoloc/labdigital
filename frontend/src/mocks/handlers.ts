import { projectHandlers } from './handlers.projects'
import { delay, http, HttpResponse, type HttpResponseResolver } from 'msw'
import { config } from '@/config'
import type {
  ChangePasswordRequest,
  LoginRequest,
  RegisterRequest,
  ResetPasswordRequest,
  UpdateMeRequest,
} from '@/api/types'
import {
  addUser,
  createSession,
  currentSession,
  currentUser,
  db,
  findUserByEmail,
  save,
  toMe,
  toSession,
} from './db'
import { courseHandlers } from './handlers.courses'

const A = config.apiBase

/** Latencia artificial (sólo en el navegador; los tests van sin espera). */
let latency = 0
export function setMockLatency(ms: number): void {
  latency = ms
}

function err(status: number, code: string, message: string, headers?: Record<string, string>) {
  return HttpResponse.json({ error: { code, message } }, { status, headers })
}

const unauthenticated = () => err(401, 'unauthenticated', 'No has iniciado sesión.')
const noContent = () => new HttpResponse(null, { status: 204 })
const accepted = () => new HttpResponse(null, { status: 202 })

/** Comprobación CSRF del contrato §2 (el Origin lo pone el navegador; aquí sólo la cabecera). */
function csrf(request: Request) {
  if (request.headers.get('X-Requested-With') !== 'labdigital') {
    return err(403, 'csrf_rejected', 'Petición rechazada (CSRF).')
  }
  return null
}

/** Envuelve un resolver: latencia + CSRF en mutaciones. */
function route(resolver: HttpResponseResolver): HttpResponseResolver {
  return async (info) => {
    if (latency) await delay(latency)
    if (info.request.method !== 'GET' && info.request.method !== 'HEAD') {
      const rejected = csrf(info.request)
      if (rejected) return rejected
    }
    return resolver(info)
  }
}

/** Sólo con `ld_access` vigente. */
function authed(resolver: HttpResponseResolver): HttpResponseResolver {
  return route(async (info) => {
    const user = currentUser()
    if (!user) return unauthenticated()
    const s = currentSession()
    if (s) s.last_used_at = new Date().toISOString()
    return resolver(info)
  })
}

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/
/** Correo que siempre devuelve 429 para probar `Retry-After`. */
export const RATE_LIMITED_EMAIL = 'limite@unimagdalena.edu.co'

export const handlers = [
  ...projectHandlers,
  ...courseHandlers,
  http.get(`${A}/health`, () => HttpResponse.json({ ok: true })),

  http.post(
    `${A}/auth/login`,
    route(async ({ request }) => {
      const body = (await request.json()) as LoginRequest
      if (body.email?.trim().toLowerCase() === RATE_LIMITED_EMAIL) {
        return err(429, 'rate_limited', 'Demasiados intentos.', { 'Retry-After': '30' })
      }
      const user = findUserByEmail(body.email ?? '')
      if (!user || user.password !== body.password) {
        return err(401, 'invalid_credentials', 'Correo o contraseña incorrectos.')
      }
      if (!user.active) return err(403, 'account_inactive', 'Cuenta desactivada.')
      if (!user.email_verified) return err(403, 'email_not_verified', 'Correo sin verificar.')
      createSession(user, request.headers.get('User-Agent'))
      return HttpResponse.json(toMe(user))
    }),
  ),

  http.post(
    `${A}/auth/refresh`,
    route(() => {
      db.calls.refresh++
      const s = db.refresh ? db.sessions.find((x) => x.id === db.refresh) : undefined
      if (!s) {
        db.access = null
        save()
        return unauthenticated()
      }
      db.access = s.id
      s.last_used_at = new Date().toISOString()
      save()
      return noContent()
    }),
  ),

  http.post(
    `${A}/auth/logout`,
    route(() => {
      const sid = db.access ?? db.refresh
      db.sessions = db.sessions.filter((s) => s.id !== sid)
      db.access = null
      db.refresh = null
      save()
      return noContent()
    }),
  ),

  http.post(
    `${A}/auth/register`,
    route(async ({ request }) => {
      const body = (await request.json()) as RegisterRequest
      const fields: Record<string, string> = {}
      if (!EMAIL_RE.test(body.email ?? '')) fields.email = 'Correo no válido.'
      if (!body.password || body.password.length < config.passwordMinLength)
        fields.password = 'La contraseña es demasiado corta.'
      if (!body.full_name?.trim()) fields.full_name = 'Falta el nombre.'
      if (body.accept_data_policy !== true) fields.accept_data_policy = 'Debes aceptar la política.'
      if (Object.keys(fields).length) {
        return HttpResponse.json(
          {
            error: { code: 'validation_error', message: 'Datos no válidos.', details: { fields } },
          },
          { status: 422 },
        )
      }
      if (!findUserByEmail(body.email)) {
        const u = addUser(body)
        db.verifyTokens[`verify-${u.id}`] = u.email
        save()
      }
      return accepted() // siempre igual, exista o no el correo
    }),
  ),

  http.post(
    `${A}/auth/verify-email`,
    route(async ({ request }) => {
      const { token } = (await request.json()) as { token: string }
      const email = db.verifyTokens[token]
      const user = email ? findUserByEmail(email) : undefined
      if (!user) return err(400, 'token_invalid', 'Enlace no válido o caducado.')
      user.email_verified = true
      delete db.verifyTokens[token]
      save()
      return noContent()
    }),
  ),

  http.post(
    `${A}/auth/resend-verification`,
    route(() => accepted()),
  ),
  http.post(
    `${A}/auth/forgot-password`,
    route(() => accepted()),
  ),

  http.post(
    `${A}/auth/reset-password`,
    route(async ({ request }) => {
      const body = (await request.json()) as ResetPasswordRequest
      const email = db.resetTokens[body.token]
      const user = email ? findUserByEmail(email) : undefined
      if (!user) return err(400, 'token_invalid', 'Enlace no válido o caducado.')
      user.password = body.password
      delete db.resetTokens[body.token]
      db.sessions = db.sessions.filter((s) => s.userId !== user.id) // revoca todas
      db.access = null
      db.refresh = null
      save()
      return noContent()
    }),
  ),

  http.get(
    `${A}/auth/sessions`,
    authed(() => {
      const user = currentUser()!
      return HttpResponse.json(db.sessions.filter((s) => s.userId === user.id).map(toSession))
    }),
  ),

  http.delete(
    `${A}/auth/sessions/:id`,
    authed(({ params }) => {
      const user = currentUser()!
      const target = db.sessions.find((s) => s.id === params.id && s.userId === user.id)
      if (!target) return err(404, 'not_found', 'Sesión no encontrada.')
      db.sessions = db.sessions.filter((s) => s !== target)
      if (target.id === db.access) {
        db.access = null
        db.refresh = null
      }
      save()
      return noContent()
    }),
  ),

  http.post(
    `${A}/auth/sessions/revoke-others`,
    authed(() => {
      const user = currentUser()!
      db.sessions = db.sessions.filter((s) => s.userId !== user.id || s.id === db.access)
      save()
      return noContent()
    }),
  ),

  http.get(
    `${A}/me`,
    authed(() => HttpResponse.json(toMe(currentUser()!))),
  ),

  http.patch(
    `${A}/me`,
    authed(async ({ request }) => {
      const body = (await request.json()) as UpdateMeRequest
      const user = currentUser()!
      if (!body.full_name?.trim()) {
        return HttpResponse.json(
          {
            error: {
              code: 'validation_error',
              message: 'Datos no válidos.',
              details: { fields: { full_name: 'Falta el nombre.' } },
            },
          },
          { status: 422 },
        )
      }
      user.full_name = body.full_name.trim()
      save()
      return HttpResponse.json(toMe(user))
    }),
  ),

  http.post(
    `${A}/me/password`,
    authed(async ({ request }) => {
      const body = (await request.json()) as ChangePasswordRequest
      const user = currentUser()!
      if (body.current !== user.password) {
        return err(401, 'invalid_credentials', 'La contraseña actual no es correcta.')
      }
      user.password = body.new
      save()
      return noContent()
    }),
  ),
]
