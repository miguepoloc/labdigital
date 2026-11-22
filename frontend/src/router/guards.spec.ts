import { describe, expect, it, vi } from 'vitest'
import { api } from '@/api/client'
import { browserNav } from '@/lib/next'
import { expireAll, signIn } from '@/mocks/db'
import { useSessionStore } from '@/stores/session'
import { createTestApp, settle } from '@/test/utils'

describe('guardias de ruta', () => {
  it('sin sesión, /app/** redirige a /entrar?next=<ruta con prefijo>', async () => {
    const { router } = createTestApp()
    await router.push('/app/perfil?tab=1')
    expect(router.currentRoute.value.name).toBe('login')
    expect(router.currentRoute.value.query.next).toBe('/labdigital/app/perfil?tab=1')
  })

  it('con sesión, deja pasar a /app', async () => {
    signIn()
    const { router } = createTestApp()
    await router.push('/app/sesiones')
    expect(router.currentRoute.value.name).toBe('sessions')
  })

  it('páginas sólo para visitantes: con sesión van a /app', async () => {
    signIn()
    const { router } = createTestApp()
    await router.push('/entrar')
    expect(router.currentRoute.value.name).toBe('home')
  })

  it('páginas sólo para visitantes: con sesión respetan un next válido de la SPA', async () => {
    signIn()
    const { router } = createTestApp()
    await router.push('/entrar?next=/labdigital/app/perfil')
    expect(router.currentRoute.value.name).toBe('profile')
  })

  it('con sesión y next fuera de la SPA (módulo) hace navegación completa', async () => {
    signIn()
    const assign = vi.spyOn(browserNav, 'assign').mockImplementation(() => {})
    const { router } = createTestApp()
    await router.push('/registro?next=/labdigital/fpga/')
    expect(assign).toHaveBeenCalledWith('/labdigital/fpga/')
  })

  it('ignora un next externo (open redirect)', async () => {
    signIn()
    const assign = vi.spyOn(browserNav, 'assign').mockImplementation(() => {})
    const { router } = createTestApp()
    await router.push('/entrar?next=https://evil.example/')
    expect(router.currentRoute.value.name).toBe('home')
    expect(assign).not.toHaveBeenCalled()
  })

  it('/_shell (cascarón) redirige a /app', async () => {
    signIn()
    const { router } = createTestApp()
    await router.push('/_shell')
    expect(router.currentRoute.value.name).toBe('home')
  })

  it('la landing es pública y no pide /me', async () => {
    const { router, pinia } = createTestApp()
    await router.push('/')
    expect(router.currentRoute.value.name).toBe('landing')
    expect(useSessionStore(pinia).status).toBe('idle')
  })

  it('si la sesión caduca y el refresh falla en /app, limpia y va a /entrar?next=&expired=1', async () => {
    signIn()
    const { router, pinia } = createTestApp()
    await router.push('/app/perfil')
    expect(useSessionStore(pinia).isAuthenticated).toBe(true)
    expireAll()
    await api.get('/auth/sessions').catch(() => {})
    await settle()
    expect(useSessionStore(pinia).me).toBeNull()
    expect(router.currentRoute.value.name).toBe('login')
    expect(router.currentRoute.value.query).toEqual({
      next: '/labdigital/app/perfil',
      expired: '1',
    })
  })
})
