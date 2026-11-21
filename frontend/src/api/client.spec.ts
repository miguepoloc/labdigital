import { http, HttpResponse } from 'msw'
import { describe, expect, it, vi } from 'vitest'
import { db, expireAccess, expireAll, signIn } from '@/mocks/db'
import { server } from '@/mocks/node'
import { api, configureApi, refreshSession, request } from './client'
import { ApiError, parseRetryAfter } from './errors'

const A = '/labdigital/api/v1'

describe('cliente API: transporte', () => {
  it('envía credentials=include y la cabecera CSRF sólo en mutaciones', async () => {
    const seen: { method: string; csrf: string | null; credentials: string }[] = []
    server.use(
      http.all(`${A}/echo`, ({ request }) => {
        seen.push({
          method: request.method,
          csrf: request.headers.get('X-Requested-With'),
          credentials: request.credentials,
        })
        return HttpResponse.json({ ok: true })
      }),
    )
    await api.get('/echo')
    await api.post('/echo', { a: 1 })
    await api.delete('/echo')
    expect(seen).toEqual([
      { method: 'GET', csrf: null, credentials: 'include' },
      { method: 'POST', csrf: 'labdigital', credentials: 'include' },
      { method: 'DELETE', csrf: 'labdigital', credentials: 'include' },
    ])
  })

  it('serializa query y cuerpo JSON', async () => {
    server.use(
      http.post(`${A}/echo`, async ({ request }) =>
        HttpResponse.json({
          q: new URL(request.url).searchParams.get('module'),
          body: await request.json(),
        }),
      ),
    )
    const res = await api.post<{ q: string; body: unknown }>(
      '/echo',
      { x: 1 },
      { query: { module: 'fpga' } },
    )
    expect(res).toEqual({ q: 'fpga', body: { x: 1 } })
  })

  it('devuelve undefined en 204', async () => {
    server.use(http.post(`${A}/echo`, () => new HttpResponse(null, { status: 204 })))
    await expect(api.post('/echo')).resolves.toBeUndefined()
  })
})

describe('cliente API: errores §6', () => {
  it('parsea {error:{code,message,details}} y Retry-After', async () => {
    server.use(
      http.post(`${A}/echo`, () =>
        HttpResponse.json(
          { error: { code: 'rate_limited', message: 'Espera', details: { scope: 'login' } } },
          { status: 429, headers: { 'Retry-After': '42' } },
        ),
      ),
    )
    const e = await api.post('/echo').catch((x: unknown) => x)
    expect(e).toBeInstanceOf(ApiError)
    expect(e).toMatchObject({
      status: 429,
      code: 'rate_limited',
      message: 'Espera',
      retryAfter: 42,
    })
    expect((e as ApiError).details).toEqual({ scope: 'login' })
  })

  it('cuerpo no conforme ⇒ código por status', async () => {
    server.use(http.get(`${A}/echo`, () => new HttpResponse('<html>', { status: 404 })))
    await expect(api.get('/echo')).rejects.toMatchObject({ status: 404, code: 'not_found' })
  })

  it('fallo de red ⇒ network_error', async () => {
    server.use(http.get(`${A}/echo`, () => HttpResponse.error()))
    await expect(api.get('/echo')).rejects.toMatchObject({ status: 0, code: 'network_error' })
  })

  it('parseRetryAfter acepta segundos y fecha HTTP', () => {
    expect(parseRetryAfter('10')).toBe(10)
    const now = Date.parse('2026-11-21T10:00:00Z')
    expect(parseRetryAfter('Sat, 21 Nov 2026 10:00:30 GMT', now)).toBe(30)
    expect(parseRetryAfter('basura')).toBeUndefined()
    expect(parseRetryAfter(null)).toBeUndefined()
  })
})

describe('cliente API: renovación ante 401', () => {
  it('renueva y reintenta de forma transparente', async () => {
    signIn()
    expireAccess()
    const me = await api.get<{ email: string }>('/me')
    expect(me.email).toBe('estudiante@unimagdalena.edu.co')
    expect(db.calls.refresh).toBe(1)
  })

  it('peticiones concurrentes comparten UN solo refresh', async () => {
    signIn()
    expireAccess()
    const results = await Promise.all([
      api.get('/me'),
      api.get('/auth/sessions'),
      api.get('/me'),
      api.patch('/me', { full_name: 'Ana Renovada' }),
    ])
    expect(results).toHaveLength(4)
    expect(db.calls.refresh).toBe(1)
  })

  it('el candado se libera: una caducidad posterior vuelve a renovar', async () => {
    signIn()
    expireAccess()
    await api.get('/me')
    expireAccess()
    await api.get('/me')
    expect(db.calls.refresh).toBe(2)
  })

  it('refreshSession() concurrente devuelve la misma promesa', async () => {
    signIn()
    expireAccess()
    const [a, b] = [refreshSession(), refreshSession()]
    expect(a).toBe(b)
    await expect(a).resolves.toBe(true)
    expect(db.calls.refresh).toBe(1)
  })

  it('si el refresh falla: lanza 401 y avisa a onSessionExpired (sin bucles)', async () => {
    const onSessionExpired = vi.fn()
    configureApi({ onSessionExpired })
    signIn()
    expireAll()
    const errors = await Promise.all([
      api.get('/me').catch((e: unknown) => e),
      api.get('/auth/sessions').catch((e: unknown) => e),
    ])
    for (const e of errors) expect(e).toMatchObject({ status: 401 })
    expect(db.calls.refresh).toBe(1)
    expect(onSessionExpired).toHaveBeenCalled()
  })

  it('redirectOnExpired:false no avisa', async () => {
    const onSessionExpired = vi.fn()
    configureApi({ onSessionExpired })
    await expect(api.get('/me', { redirectOnExpired: false })).rejects.toMatchObject({
      status: 401,
    })
    expect(onSessionExpired).not.toHaveBeenCalled()
  })

  it('refreshOn401:false no intenta renovar (endpoints de auth)', async () => {
    await expect(
      request('/auth/login', {
        method: 'POST',
        body: { email: 'x@y.co', password: 'malamalamala', remember: false },
        refreshOn401: false,
      }),
    ).rejects.toMatchObject({ status: 401, code: 'invalid_credentials' })
    expect(db.calls.refresh).toBe(0)
  })

  it('un 401 que llega después de una renovación ajena reintenta sin volver a renovar', async () => {
    signIn()
    expireAccess()
    // /slow responde 401 tarde, cuando /me ya renovó la sesión.
    let release!: () => void
    const gate = new Promise<void>((r) => (release = r))
    let first = true
    server.use(
      http.get(`${A}/slow`, async () => {
        if (first) {
          first = false
          await gate
          return HttpResponse.json(
            { error: { code: 'unauthenticated', message: 'x' } },
            { status: 401 },
          )
        }
        return HttpResponse.json({ ok: true })
      }),
    )
    const slow = api.get('/slow')
    await api.get('/me') // renueva
    release()
    await expect(slow).resolves.toEqual({ ok: true })
    expect(db.calls.refresh).toBe(1)
  })
})

describe('cliente API: 401 de dominio', () => {
  it('invalid_credentials en una ruta autenticada no renueva ni expulsa', async () => {
    const onSessionExpired = vi.fn()
    configureApi({ onSessionExpired })
    signIn()
    await expect(
      api.post('/me/password', { current: 'mal', new: 'nueva-clave-12' }),
    ).rejects.toMatchObject({
      status: 401,
      code: 'invalid_credentials',
    })
    expect(db.calls.refresh).toBe(0)
    expect(onSessionExpired).not.toHaveBeenCalled()
  })
})
