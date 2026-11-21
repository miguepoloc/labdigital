import { afterAll, afterEach, beforeAll, beforeEach } from 'vitest'
import { resetApiClient } from '@/api/client'
import { resetDb } from '@/mocks/db'
import { resetCoursesDb } from '@/mocks/db.courses'
import { server } from '@/mocks/node'

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }))
beforeEach(() => {
  resetDb()
  resetCoursesDb()
  resetApiClient()
})
afterEach(() => server.resetHandlers())
afterAll(() => server.close())
