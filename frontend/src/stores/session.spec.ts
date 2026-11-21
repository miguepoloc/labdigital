import { http, HttpResponse } from 'msw'
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it } from 'vitest'
import { db, DEMO_PASSWORD, expireAccess, signIn } from '@/mocks/db'
import { server } from '@/mocks/node'
import { useSessionStore } from './session'

describe('store de sesión', () => {
  beforeEach(() => setActivePinia(createPinia()))

  it('load() sin sesión deja me=null sin error', async () => {
    const s = useSessionStore()
    await expect(s.load()).resolves.toBeNull()
    expect(s.me).toBeNull()
    expect(s.status).toBe('ready')
    expect(s.loadError).toBeNull()
    expect(s.isAuthenticated).toBe(false)
  })

  it('load() con sesión carga GET /me', async () => {
    signIn()
    const s = useSessionStore()
    await s.load()
    expect(s.me?.email).toBe('estudiante@unimagdalena.edu.co')
    expect(s.isAuthenticated).toBe(true)
  })

  it('load() con access caducado renueva y carga', async () => {
    signIn()
    expireAccess()
    const s = useSessionStore()
    await s.load()
    expect(s.me?.full_name).toBe('Ana María Estudiante')
    expect(db.calls.refresh).toBe(1)
  })

  it('load() guarda errores que no son 401 (p. ej. red)', async () => {
    server.use(http.get('/labdigital/api/v1/me', () => HttpResponse.error()))
    const s = useSessionStore()
    await s.load()
    expect(s.me).toBeNull()
    expect(s.loadError).toMatchObject({ code: 'network_error' })
  })

  it('ensureLoaded() sólo pide /me una vez', async () => {
    signIn()
    let calls = 0
    server.events.on('request:start', ({ request }) => {
      if (request.url.endsWith('/api/v1/me')) calls++
    })
    const s = useSessionStore()
    await Promise.all([s.ensureLoaded(), s.ensureLoaded()])
    await s.ensureLoaded()
    expect(calls).toBe(1)
    server.events.removeAllListeners()
  })

  it('login() fija me; logout() cierra en el servidor y limpia', async () => {
    const s = useSessionStore()
    await s.login({
      email: 'estudiante@unimagdalena.edu.co',
      password: DEMO_PASSWORD,
      remember: true,
    })
    expect(s.me?.role).toBe('user')
    expect(db.access).not.toBeNull()
    await s.logout()
    expect(s.me).toBeNull()
    expect(db.access).toBeNull()
    expect(db.refresh).toBeNull()
  })

  it('logout() limpia aunque el servidor falle', async () => {
    signIn()
    const s = useSessionStore()
    await s.load()
    server.use(http.post('/labdigital/api/v1/auth/logout', () => HttpResponse.error()))
    await s.logout()
    expect(s.me).toBeNull()
  })
})
