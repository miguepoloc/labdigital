import { afterAll, afterEach, beforeAll, beforeEach } from 'vitest'
import { resetApiClient } from '@/api/client'
import { resetDb } from '@/mocks/db'
import { server } from '@/mocks/node'

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }))
beforeEach(() => {
  resetDb()
  resetApiClient()
})
afterEach(() => server.resetHandlers())
afterAll(() => server.close())
