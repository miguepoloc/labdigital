import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import { authApi, meApi } from '@/api/auth'
import { isApiError } from '@/api/errors'
import type { LoginRequest, Me } from '@/api/types'
import { hasSessionHint } from '@/lib/sessionHint'

export type SessionStatus = 'idle' | 'loading' | 'ready'

/** Estado de la sesión del usuario. Los tokens viven en cookies HttpOnly: aquí sólo está `me`. */
export const useSessionStore = defineStore('session', () => {
  const me = ref<Me | null>(null)
  const status = ref<SessionStatus>('idle')
  /** Error no relacionado con la autenticación al cargar `me` (red caída, 5xx…). */
  const loadError = ref<unknown>(null)
  let loading: Promise<Me | null> | null = null

  const isAuthenticated = computed(() => me.value !== null)
  const isAdmin = computed(() => me.value?.role === 'admin')

  /** `GET /me` (con un intento de refresh si hay 401). Nunca lanza: devuelve `null` si no hay sesión. */
  function load(): Promise<Me | null> {
    if (loading) return loading
    status.value = 'loading'
    loadError.value = null
    loading = meApi
      .get({ redirectOnExpired: false })
      .then((user) => {
        me.value = user
        return user
      })
      .catch((e: unknown) => {
        me.value = null
        if (!isApiError(e) || e.status !== 401) loadError.value = e
        return null
      })
      .finally(() => {
        status.value = 'ready'
        loading = null
      })
    return loading
  }

  /**
   * Carga `me` sólo la primera vez (lo usa la guardia de rutas). Con `optional` (páginas públicas) no pregunta
   * a la API si falta la cookie indicadora `ld_session`: sin ella no hay sesión que renovar.
   */
  async function ensureLoaded(opts: { optional?: boolean } = {}): Promise<Me | null> {
    if (status.value === 'ready') return me.value
    if (opts.optional && !loading && !hasSessionHint()) return null
    return load()
  }

  async function login(body: LoginRequest): Promise<Me> {
    const user = await authApi.login(body)
    me.value = user
    status.value = 'ready'
    return user
  }

  function setMe(user: Me | null) {
    me.value = user
    status.value = 'ready'
  }

  /** Cierra la sesión en el servidor (best effort) y limpia el estado local. */
  async function logout(): Promise<void> {
    try {
      await authApi.logout()
    } catch {
      /* aunque falle, la sesión local se limpia */
    } finally {
      clear()
    }
  }

  /** Limpia el estado sin llamar al servidor (p. ej. sesión caducada). */
  function clear() {
    me.value = null
    status.value = 'ready'
  }

  return {
    me,
    status,
    loadError,
    isAuthenticated,
    isAdmin,
    load,
    ensureLoaded,
    login,
    setMe,
    logout,
    clear,
  }
})
