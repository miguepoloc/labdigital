// Limpia del build de producción lo que no debe servirse:
// - mockServiceWorker.js (MSW, sólo desarrollo)
// - .vite/ (ssr-manifest de vite-ssg, sólo para el prerender)
import { rmSync } from 'node:fs'
import { fileURLToPath } from 'node:url'

for (const rel of ['../dist/mockServiceWorker.js', '../dist/.vite']) {
  rmSync(fileURLToPath(new URL(rel, import.meta.url)), { force: true, recursive: true })
}
console.log('postbuild: eliminados mockServiceWorker.js y .vite/ de dist/')
