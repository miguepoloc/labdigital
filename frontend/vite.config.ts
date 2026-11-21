import { fileURLToPath, URL } from 'node:url'
import { defineConfig, loadEnv } from 'vite'
import vue from '@vitejs/plugin-vue'
import type {} from 'vitest/config'
import type {} from 'vite-ssg'

/**
 * Rutas que se prerenderizan a HTML estático (vite-ssg).
 * - `/` es la landing pública (debe indexarse).
 * - Las páginas de cuenta se prerenderizan para un primer pintado rápido; el cliente las monta de nuevo.
 * - `/_shell` es el "cascarón" de la SPA: nginx lo sirve como fallback para `/labdigital/app/**`.
 */
export const PRERENDERED_ROUTES = [
  '/',
  '/entrar',
  '/registro',
  '/verificar',
  '/recuperar',
  '/restablecer',
  '/sesion',
  '/_shell',
]

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  return {
    base: '/labdigital/',
    plugins: [vue()],
    resolve: {
      alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) },
    },
    server: {
      host: '0.0.0.0',
      port: 5173,
      proxy:
        env.VITE_API_MOCK === '0'
          ? {
              '/labdigital/api': {
                target: env.LD_API_PROXY ?? 'http://127.0.0.1:8088',
                changeOrigin: false,
              },
            }
          : undefined,
    },
    ssgOptions: {
      includedRoutes: () => PRERENDERED_ROUTES,
      dirStyle: 'flat',
      formatting: 'none',
      mock: true,
    },
    test: {
      environment: 'jsdom',
      setupFiles: ['./src/test/setup.ts'],
      include: ['src/**/*.spec.ts'],
      restoreMocks: true,
    },
  }
})
