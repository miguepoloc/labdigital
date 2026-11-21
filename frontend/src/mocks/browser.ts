import { setupWorker } from 'msw/browser'
import { config } from '@/config'
import * as mockDb from './db'
import { handlers, setMockLatency } from './handlers'
import { enableProjectsPersistence, setProjectsMockLatency } from './handlers.projects'

/** Arranca la API simulada en el navegador (sólo `npm run dev` con VITE_API_MOCK distinto de "0"). */
export async function startMockApi(): Promise<void> {
  mockDb.enablePersistence()
  setMockLatency(350)
  enableProjectsPersistence()
  setProjectsMockLatency(350)
  const worker = setupWorker(...handlers)
  await worker.start({
    serviceWorker: { url: `${config.basePath}mockServiceWorker.js` },
    onUnhandledRequest: 'bypass',
    quiet: true,
  })
  // Atajos de consola: __ldMock.expireAccess(), __ldMock.expireAll(), __ldMock.resetDb()
  ;(window as unknown as { __ldMock: typeof mockDb }).__ldMock = mockDb
  console.info(
    '[LabDigital] API simulada con MSW. Usuario demo: estudiante@unimagdalena.edu.co / %s',
    mockDb.DEMO_PASSWORD,
  )
}
