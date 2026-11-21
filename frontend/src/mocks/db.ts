/**
 * Estado en memoria de la API simulada (MSW). Imita el contrato: cookies HttpOnly ⇒ aquí el "navegador"
 * sólo tiene una referencia a la sesión vigente (`access`/`refresh`), que el test puede caducar.
 */
import type { Me, Role, Session } from '@/api/types'

export interface MockUser {
  id: string
  email: string
  full_name: string
  password: string
  role: Role
  email_verified: boolean
  active: boolean
  created_at: string
}

export interface MockSession {
  id: string
  userId: string
  user_agent: string | null
  ip: string | null
  created_at: string
  last_used_at: string
}

interface State {
  users: MockUser[]
  sessions: MockSession[]
  /** Sesión a la que apunta la cookie `ld_access` vigente (null = sin cookie o caducada). */
  access: string | null
  /** Sesión a la que apunta la cookie `ld_refresh` vigente. */
  refresh: string | null
  verifyTokens: Record<string, string>
  resetTokens: Record<string, string>
  /** Contadores para los tests. */
  calls: { refresh: number }
}

export const DEMO_PASSWORD = 'labdigital123'

let seq = 0
function id(prefix: string) {
  seq++
  return `0190${prefix}-0000-7000-8000-${String(seq).padStart(12, '0')}`
}

function seed(): State {
  seq = 0
  const now = new Date('2026-11-01T14:00:00Z').toISOString()
  const users: MockUser[] = [
    {
      id: id('a'),
      email: 'estudiante@unimagdalena.edu.co',
      full_name: 'Ana María Estudiante',
      password: DEMO_PASSWORD,
      role: 'user',
      email_verified: true,
      active: true,
      created_at: now,
    },
    {
      id: id('b'),
      email: 'pendiente@unimagdalena.edu.co',
      full_name: 'Pedro Pendiente',
      password: DEMO_PASSWORD,
      role: 'user',
      email_verified: false,
      active: true,
      created_at: now,
    },
    {
      id: id('c'),
      email: 'inactivo@unimagdalena.edu.co',
      full_name: 'Iván Inactivo',
      password: DEMO_PASSWORD,
      role: 'user',
      email_verified: true,
      active: false,
      created_at: now,
    },
    {
      id: id('d'),
      email: 'admin@unimagdalena.edu.co',
      full_name: 'Admin GIDEAM',
      password: DEMO_PASSWORD,
      role: 'admin',
      email_verified: true,
      active: true,
      created_at: now,
    },
  ]
  const ana = users[0]!
  const sessions: MockSession[] = [
    {
      id: id('e'),
      userId: ana.id,
      user_agent: 'Mozilla/5.0 (Android 14; Mobile) Firefox/132.0',
      ip: '181.49.10.7',
      created_at: '2026-10-28T12:00:00Z',
      last_used_at: '2026-10-30T18:30:00Z',
    },
  ]
  return {
    users,
    sessions,
    access: null,
    refresh: null,
    verifyTokens: { 'demo-verify': 'pendiente@unimagdalena.edu.co' },
    resetTokens: { 'demo-reset': 'estudiante@unimagdalena.edu.co' },
    calls: { refresh: 0 },
  }
}

const STORAGE_KEY = 'ld-mock-db'
let persist = false
export let db: State = seed()

/** En el navegador (dev) el estado sobrevive a recargas. */
export function enablePersistence(): void {
  persist = true
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (raw) db = { ...seed(), ...(JSON.parse(raw) as Partial<State>) }
  } catch {
    /* sin almacenamiento */
  }
}

/** Imita la cookie indicadora `ld_session` (contrato §6.1): existe mientras haya refresh vigente. */
function syncSessionHint(): void {
  if (typeof document === 'undefined') return
  document.cookie = db.refresh ? 'ld_session=1; path=/' : 'ld_session=; path=/; max-age=0'
}

export function save(): void {
  syncSessionHint()
  if (!persist) return
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(db))
  } catch {
    /* sin almacenamiento */
  }
}

export function resetDb(): void {
  db = seed()
  save()
}

export function toMe(u: MockUser): Me {
  return {
    id: u.id,
    email: u.email,
    full_name: u.full_name,
    role: u.role,
    email_verified: u.email_verified,
    created_at: u.created_at,
  }
}

export function findUserByEmail(email: string): MockUser | undefined {
  const e = email.trim().toLowerCase()
  return db.users.find((u) => u.email === e)
}

export function currentSession(): MockSession | undefined {
  return db.access ? db.sessions.find((s) => s.id === db.access) : undefined
}

export function currentUser(): MockUser | undefined {
  const s = currentSession()
  return s ? db.users.find((u) => u.id === s.userId) : undefined
}

export function createSession(user: MockUser, ua: string | null): MockSession {
  const now = new Date().toISOString()
  const s: MockSession = {
    id: id('s'),
    userId: user.id,
    user_agent: ua,
    ip: '127.0.0.1',
    created_at: now,
    last_used_at: now,
  }
  db.sessions.push(s)
  db.access = s.id
  db.refresh = s.id
  save()
  return s
}

export function addUser(data: Pick<MockUser, 'email' | 'full_name' | 'password'>): MockUser {
  const u: MockUser = {
    id: id('u'),
    email: data.email.trim().toLowerCase(),
    full_name: data.full_name.trim(),
    password: data.password,
    role: 'user',
    email_verified: false,
    active: true,
    created_at: new Date().toISOString(),
  }
  db.users.push(u)
  save()
  return u
}

export function toSession(s: MockSession): Session {
  return {
    id: s.id,
    user_agent: s.user_agent,
    ip: s.ip,
    created_at: s.created_at,
    last_used_at: s.last_used_at,
    current: s.id === db.access,
  }
}

// ---- Atajos para tests y para jugar en dev desde la consola ----

/** Inicia sesión directamente (sin pasar por /auth/login). */
export function signIn(email = 'estudiante@unimagdalena.edu.co'): MockSession {
  const u = findUserByEmail(email)
  if (!u) throw new Error(`usuario mock inexistente: ${email}`)
  return createSession(u, 'Mozilla/5.0 (X11; Linux x86_64) Chrome/131.0')
}

/** Simula que `ld_access` caducó (el refresh sigue siendo válido). */
export function expireAccess(): void {
  db.access = null
  save()
}

/** Simula que también el refresh caducó o fue revocado. */
export function expireAll(): void {
  db.access = null
  db.refresh = null
  save()
}
