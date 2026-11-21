import { createPinia } from 'pinia'
import { ViteSSG } from 'vite-ssg'
import App from './App.vue'
import { installGuards, installSessionExpiry } from './router/guards'
import { routes } from './router/routes'
import './styles/tokens.css'
import './styles/base.css'
import './styles/forms.css'

/**
 * Punto de entrada (vite-ssg): en build se prerenderizan las rutas de `PRERENDERED_ROUTES`
 * (vite.config.ts); en el navegador se monta la SPA normal.
 */
export const createApp = ViteSSG(
  App,
  {
    routes,
    base: import.meta.env.BASE_URL,
    // En el prerender no hay ventana real: sin scrollBehavior.
    scrollBehavior: import.meta.env.SSR
      ? undefined
      : (to, _from, saved) => saved ?? (to.hash ? { el: to.hash } : { top: 0 }),
  },
  async ({ app, router, isClient }) => {
    // No se transfiere estado de Pinia desde el prerender: nada se carga en build (y así no hay
    // <script> en línea, compatible con la CSP de nginx.conf).
    const pinia = createPinia()
    app.use(pinia)

    installGuards(router, pinia)

    if (isClient) {
      installSessionExpiry(router, pinia)
      if (import.meta.env.DEV && import.meta.env.VITE_API_MOCK !== '0') {
        const { startMockApi } = await import('./mocks/browser')
        await startMockApi()
      }
    }
  },
)
