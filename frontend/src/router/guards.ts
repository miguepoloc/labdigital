import type { Pinia } from 'pinia'
import type { RouteLocationRaw, Router } from 'vue-router'
import { configureApi } from '@/api/client'
import { absoluteFromRouter, browserNav, isSpaPath, nextOrDefault, toRouterPath } from '@/lib/next'
import { useSessionStore } from '@/stores/session'

const isSSR = import.meta.env.SSR

/** Navega a `next` (validado): dentro de la SPA con el router, fuera (p. ej. `/labdigital/fpga/`) con recarga. */
export function goToNext(router: Router, rawNext: unknown): Promise<unknown> | void {
  const target = nextOrDefault(rawNext)
  const routerPath = isSpaPath(target) ? toRouterPath(target) : null
  if (routerPath) return router.replace(routerPath)
  browserNav.assign(target)
}

function loginRedirect(fullPath: string, extra?: Record<string, string>): RouteLocationRaw {
  return { name: 'login', query: { next: absoluteFromRouter(fullPath), ...extra } }
}

/** Guardias de navegación: área privada y páginas sólo para visitantes. */
export function installGuards(router: Router, pinia: Pinia): void {
  router.beforeEach(async (to) => {
    if (isSSR) return true
    const session = useSessionStore(pinia)

    if (to.name === 'shell') return { path: '/app', replace: true }

    if (to.matched.some((r) => r.meta.requiresAuth)) {
      const me = await session.ensureLoaded()
      if (!me) return loginRedirect(to.fullPath)
      return true
    }

    if (to.meta.guestOnly) {
      const me = await session.ensureLoaded()
      if (me) {
        const target = nextOrDefault(to.query.next)
        const routerPath = isSpaPath(target) ? toRouterPath(target) : null
        if (routerPath) return { path: routerPath, replace: true }
        browserNav.assign(target)
        return false
      }
    }
    return true
  })
}

/** Conecta el cliente API con la sesión: si el refresh falla, limpia `me` y manda a `/entrar?next=`. */
export function installSessionExpiry(router: Router, pinia: Pinia): void {
  configureApi({
    onSessionExpired: () => {
      const session = useSessionStore(pinia)
      session.clear()
      const current = router.currentRoute.value
      if (current.matched.some((r) => r.meta.requiresAuth)) {
        void router.replace(loginRedirect(current.fullPath, { expired: '1' }))
      }
    },
  })
}
