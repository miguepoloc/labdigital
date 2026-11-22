import { createHead } from '@unhead/vue/client'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createMemoryHistory, createRouter } from 'vue-router'
import App from '@/App.vue'
import { installGuards, installSessionExpiry } from '@/router/guards'
import { routes } from '@/router/routes'

/** Router + Pinia reales (con guardias) sobre historia en memoria. */
export function createTestApp() {
  const pinia = createPinia()
  setActivePinia(pinia)
  const router = createRouter({ history: createMemoryHistory('/labdigital/'), routes })
  installGuards(router, pinia)
  installSessionExpiry(router, pinia)
  return { pinia, router }
}

/** Monta la app completa en `path` y espera a que cargue la ruta (y sus peticiones iniciales). */
export async function renderAt(path: string) {
  const { pinia, router } = createTestApp()
  await router.push(path)
  await router.isReady()
  const wrapper = mount(App, {
    global: { plugins: [pinia, router, createHead()] },
    attachTo: document.body,
  })
  await settle()
  return { wrapper, router, pinia }
}

/** Deja correr promesas, peticiones MSW y re-renderizados. */
export async function settle(times = 4) {
  for (let i = 0; i < times; i++) {
    await flushPromises()
    await new Promise((r) => setTimeout(r, 0))
  }
}
