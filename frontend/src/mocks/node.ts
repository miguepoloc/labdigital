import { setupServer } from 'msw/node'
import { handlers } from './handlers'

/** Servidor MSW para Vitest (Node + jsdom). */
export const server = setupServer(...handlers)
