// Limpia del build de producción lo que no debe servirse:
// - mockServiceWorker.js (MSW, sólo desarrollo)
// - .vite/ (ssr-manifest de vite-ssg, sólo para el prerender)
// - dev-fpga-stub.* (módulo FPGA falso para desarrollar el envoltorio, LD-9)
import { rmSync } from 'node:fs'
import { fileURLToPath } from 'node:url'

for (const rel of [
  '../dist/mockServiceWorker.js',
  '../dist/.vite',
  '../dist/dev-fpga-stub.html',
  '../dist/dev-fpga-stub.js',
]) {
  rmSync(fileURLToPath(new URL(rel, import.meta.url)), { force: true, recursive: true })
}
console.log('postbuild: eliminados mockServiceWorker.js, dev-fpga-stub.* y .vite/ de dist/')
