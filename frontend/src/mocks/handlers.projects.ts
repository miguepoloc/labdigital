/**
 * API simulada de proyectos (contrato §4 "Proyectos"). Estado propio, ligado al objeto `db` vigente:
 * cuando `resetDb()` crea un `db` nuevo (cada test), los proyectos vuelven a la semilla sin tocar db.ts.
 * Semántica del plan: el autoguardado sobrescribe la versión autosave abierta y abre una nueva cada ~10 min;
 * "Guardar versión" y "Restaurar" crean versiones nuevas (manual). Cada guardado sube `revision`;
 * `base_revision` (o `base_version`) ≠ actual ⇒ 409 `version_conflict` (contrato §6.1).
 */
import { delay, http, HttpResponse, type HttpResponseResolver } from 'msw'
import { config } from '@/config'
import {
  contentSize,
  FPGA_FORMAT,
  starterFpgaContent,
  type AutosaveRequest,
  type CreateProjectRequest,
  type FpgaContent,
  type Project,
  type ProjectContent,
  type ProjectSummary,
  type ProjectVersion,
  type ProjectVersionDetail,
} from '@/api/projects'
import { currentUser, db } from './db'
import { cdb } from './db.courses'

const A = config.apiBase
const MAX_BYTES = 2 * 1024 * 1024
/** Cada cuánto el autoguardado abre una versión nueva en vez de sobrescribir (plan: ~10 min). */
export const AUTOSAVE_WINDOW_MS = 10 * 60 * 1000

export interface MockVersion {
  id: string
  n: number
  kind: 'autosave' | 'manual'
  label: string | null
  content: ProjectContent
  size: number
  created_at: string
  updated_at: string
}

export interface MockProject {
  id: string
  ownerId: string
  name: string
  module: 'fpga'
  created_at: string
  updated_at: string
  deleted_at: string | null
  currentId: string
  /** Sube en cada guardado (contrato §6.1). */
  revision: number
  versions: MockVersion[]
}

interface ProjectsState {
  projects: MockProject[]
  seq: number
  /** Fallos inyectados por los tests para `PUT /autosave`: 'network' | 'server'. */
  autosaveFailures: Array<'network' | 'server'>
  calls: { autosave: AutosaveRequest[] }
}

const STORAGE_KEY = 'ld-mock-projects'
const states = new WeakMap<object, ProjectsState>()
let persist = false
let loadedFromStorage = false

function pid(st: ProjectsState, prefix: string) {
  st.seq++
  return `0190${prefix}-0000-7000-9000-${String(st.seq).padStart(12, '0')}`
}

function fpga(name: string, body: string): FpgaContent {
  const c = starterFpgaContent(name)
  c.files[0]!.text = c.files[0]!.text.replace('  led <= sw;', body)
  return c
}

function makeVersion(
  st: ProjectsState,
  p: Pick<MockProject, 'versions'>,
  kind: MockVersion['kind'],
  content: ProjectContent,
  at: string,
  label: string | null = null,
): MockVersion {
  const v: MockVersion = {
    id: pid(st, 'v'),
    n: p.versions.length + 1,
    kind,
    label,
    content: structuredClone(content),
    size: contentSize(content),
    created_at: at,
    updated_at: at,
  }
  p.versions.push(v)
  return v
}

function seed(): ProjectsState {
  const st: ProjectsState = { projects: [], seq: 0, autosaveFailures: [], calls: { autosave: [] } }
  const ana = db.users.find((u) => u.email === 'estudiante@unimagdalena.edu.co')
  if (!ana) return st
  const bcd: MockProject = {
    id: pid(st, 'p'),
    ownerId: ana.id,
    name: 'Contador BCD',
    module: 'fpga',
    created_at: '2026-11-02T13:00:00Z',
    updated_at: '2026-11-05T16:20:00Z',
    deleted_at: null,
    currentId: '',
    revision: 0,
    versions: [],
  }
  makeVersion(st, bcd, 'autosave', fpga('Contador BCD', '  led <= not sw;'), '2026-11-02T13:00:00Z')
  makeVersion(
    st,
    bcd,
    'manual',
    fpga('Contador BCD', '  led <= sw(7 downto 0) & sw(15 downto 8);'),
    '2026-11-04T10:00:00Z',
    'Antes de la síntesis',
  )
  bcd.currentId = makeVersion(
    st,
    bcd,
    'autosave',
    fpga('Contador BCD', '  led <= sw(15 downto 8) & sw(7 downto 0);'),
    '2026-11-05T16:20:00Z',
  ).id
  const sem: MockProject = {
    id: pid(st, 'p'),
    ownerId: ana.id,
    name: 'Semáforo',
    module: 'fpga',
    created_at: '2026-11-06T09:00:00Z',
    updated_at: '2026-11-06T09:30:00Z',
    deleted_at: null,
    currentId: '',
    revision: 0,
    versions: [],
  }
  sem.currentId = makeVersion(
    st,
    sem,
    'autosave',
    fpga('Semáforo', '  led <= (others => sw(0));'),
    '2026-11-06T09:30:00Z',
  ).id
  st.projects.push(bcd, sem)
  addCourseDemoProjects(st)
  return st
}

/** Los proyectos de ejemplo de los mocks de cursos (LD-8b) viven aquí también, con los mismos ids, para que
 * la lista de proyectos, el diálogo de entrega y la revisión vean los mismos datos. */
function addCourseDemoProjects(st: ProjectsState): void {
  for (const cp of cdb.projects) {
    if (st.projects.some((p) => p.id === cp.id) || cp.versions.length === 0) continue
    const versions: MockVersion[] = cp.versions.map((v) => ({
      id: v.id,
      n: v.n,
      kind: v.kind === 'autosave' ? 'autosave' : 'manual',
      label: v.label,
      content: fpga(cp.name, '  led <= sw;'),
      size: v.size,
      created_at: v.created_at,
      updated_at: v.created_at,
    }))
    st.projects.push({
      id: cp.id,
      ownerId: cp.owner_id,
      name: cp.name,
      module: 'fpga',
      created_at: versions[0]!.created_at,
      updated_at: cp.updated_at,
      deleted_at: null,
      currentId: versions[versions.length - 1]!.id,
      revision: versions.length,
      versions,
    })
  }
}

/** Estado de proyectos del `db` vigente (se crea con la semilla la primera vez). */
export function projectsState(): ProjectsState {
  let st = states.get(db)
  if (!st) {
    st = seed()
    if (persist && !loadedFromStorage) {
      loadedFromStorage = true
      try {
        const raw = localStorage.getItem(STORAGE_KEY)
        if (raw) st = { ...st, ...(JSON.parse(raw) as Partial<ProjectsState>) }
      } catch {
        /* sin almacenamiento */
      }
    }
    states.set(db, st)
  }
  return st
}

function save() {
  if (!persist) return
  try {
    const { projects, seq } = projectsState()
    localStorage.setItem(STORAGE_KEY, JSON.stringify({ projects, seq }))
  } catch {
    /* sin almacenamiento */
  }
}

/** En el navegador (dev) los proyectos sobreviven a recargas. */
export function enableProjectsPersistence(): void {
  persist = true
}

// ---- Atajos para tests ----

/** Los próximos `PUT /autosave` fallan (red caída o 500), en orden. */
export function failNextAutosaves(...kinds: Array<'network' | 'server'>): void {
  projectsState().autosaveFailures.push(...kinds)
}

/** Simula que otra pestaña/equipo guardó una versión nueva: la `base_revision` del cliente queda vieja. */
export function saveFromElsewhere(projectId: string, content?: ProjectContent): MockVersion {
  const st = projectsState()
  const p = st.projects.find((x) => x.id === projectId)
  if (!p) throw new Error(`proyecto mock inexistente: ${projectId}`)
  const now = new Date().toISOString()
  const v = makeVersion(st, p, 'manual', content ?? current(p).content, now, 'Otra pestaña')
  p.currentId = v.id
  p.updated_at = now
  p.revision++
  return v
}

export function findMockProject(id: string): MockProject | undefined {
  return projectsState().projects.find((p) => p.id === id)
}

// ---- Serialización ----

function current(p: MockProject): MockVersion {
  return p.versions.find((v) => v.id === p.currentId)!
}

function toSummary(p: MockProject): ProjectSummary {
  const v = current(p)
  return {
    id: p.id,
    name: p.name,
    module: p.module,
    current_version_id: v.id,
    current_version_n: v.n,
    revision: p.revision,
    created_at: p.created_at,
    updated_at: p.updated_at,
  }
}

function toProject(p: MockProject): Project {
  return { ...toSummary(p), content: structuredClone(current(p).content) }
}

function toVersion(v: MockVersion): ProjectVersion {
  return {
    id: v.id,
    n: v.n,
    kind: v.kind,
    label: v.label,
    size: v.size,
    created_at: v.created_at,
    updated_at: v.updated_at,
  }
}

function toVersionDetail(v: MockVersion): ProjectVersionDetail {
  return { ...toVersion(v), content: structuredClone(v.content) }
}

// ---- Respuestas ----

function err(status: number, code: string, message: string, details?: Record<string, unknown>) {
  return HttpResponse.json({ error: { code, message, details } }, { status })
}

function validation(fields: Record<string, string>) {
  return err(422, 'validation_error', 'Datos no válidos.', { fields })
}

/** Valida `content` como la API: JSON objeto, `format` conocido y ≤ 2 MB. */
function checkContent(content: unknown) {
  if (!content || typeof content !== 'object' || Array.isArray(content)) {
    return validation({ content: 'El contenido no es válido.' })
  }
  if ((content as { format?: unknown }).format !== FPGA_FORMAT) {
    return validation({ content: 'Formato de proyecto desconocido.' })
  }
  if (contentSize(content) > MAX_BYTES) {
    return err(413, 'payload_too_large', 'El proyecto supera el límite de 2 MB.')
  }
  return null
}

let latency = 0
export function setProjectsMockLatency(ms: number): void {
  latency = ms
}

/** Sesión + CSRF + proyecto propio (si la ruta lleva `:id`). */
function owned(
  resolver: (info: Parameters<HttpResponseResolver>[0], p: MockProject | null) => unknown,
): HttpResponseResolver {
  return (async (info) => {
    if (latency) await delay(latency)
    const user = currentUser()
    if (!user) return err(401, 'unauthenticated', 'No has iniciado sesión.')
    const method = info.request.method
    if (
      method !== 'GET' &&
      method !== 'HEAD' &&
      info.request.headers.get('X-Requested-With') !== 'labdigital'
    ) {
      return err(403, 'csrf_rejected', 'Petición rechazada (CSRF).')
    }
    const id = info.params.id
    if (typeof id === 'string') {
      const p = projectsState().projects.find((x) => x.id === id)
      if (!p || p.deleted_at) return err(404, 'not_found', 'Proyecto no encontrado.')
      if (p.ownerId !== user.id) return err(403, 'forbidden', 'No tienes acceso a este proyecto.')
      return resolver(info, p)
    }
    return resolver(info, null)
  }) as HttpResponseResolver
}

function cleanName(raw: unknown): string | null {
  if (typeof raw !== 'string') return null
  const name = raw.trim()
  return name && name.length <= 120 ? name : null
}

export const projectHandlers = [
  http.get(
    `${A}/projects`,
    owned(({ request }) => {
      const user = currentUser()!
      const module = new URL(request.url).searchParams.get('module')
      const list = projectsState()
        .projects.filter((p) => p.ownerId === user.id && !p.deleted_at)
        .filter((p) => !module || p.module === module)
        .sort((a, b) => b.updated_at.localeCompare(a.updated_at))
        .map(toSummary)
      return HttpResponse.json(list)
    }),
  ),

  http.post(
    `${A}/projects`,
    owned(async ({ request }) => {
      const body = (await request.json()) as Partial<CreateProjectRequest>
      const name = cleanName(body.name)
      if (!name) return validation({ name: 'Escribe un nombre (máximo 120 caracteres).' })
      if (body.module !== 'fpga') return validation({ module: 'Módulo desconocido.' })
      const bad = checkContent(body.content)
      if (bad) return bad
      const st = projectsState()
      const now = new Date().toISOString()
      const p: MockProject = {
        id: pid(st, 'p'),
        ownerId: currentUser()!.id,
        name,
        module: 'fpga',
        created_at: now,
        updated_at: now,
        deleted_at: null,
        currentId: '',
        revision: 1,
        versions: [],
      }
      p.currentId = makeVersion(st, p, 'autosave', body.content as ProjectContent, now).id
      st.projects.push(p)
      save()
      return HttpResponse.json(toProject(p), { status: 201 })
    }),
  ),

  http.get(
    `${A}/projects/:id`,
    owned((_info, p) => HttpResponse.json(toProject(p!))),
  ),

  http.patch(
    `${A}/projects/:id`,
    owned(async ({ request }, p) => {
      const body = (await request.json()) as { name?: unknown }
      const name = cleanName(body.name)
      if (!name) return validation({ name: 'Escribe un nombre (máximo 120 caracteres).' })
      p!.name = name
      p!.updated_at = new Date().toISOString()
      save()
      return HttpResponse.json(toProject(p!))
    }),
  ),

  http.delete(
    `${A}/projects/:id`,
    owned((_info, p) => {
      p!.deleted_at = new Date().toISOString()
      save()
      return new HttpResponse(null, { status: 204 })
    }),
  ),

  http.put(
    `${A}/projects/:id/autosave`,
    owned(async ({ request }, p) => {
      const st = projectsState()
      const body = (await request.json()) as AutosaveRequest
      st.calls.autosave.push(structuredClone(body))
      const failure = st.autosaveFailures.shift()
      if (failure === 'network') return HttpResponse.error()
      if (failure === 'server') return err(500, 'internal_error', 'Error interno.')
      const bad = checkContent(body.content)
      if (bad) return bad
      const cur = current(p!)
      // Como la API real: `base_version` es el `n` (entero) de la versión actual.
      if (typeof body.base_version !== 'number') {
        return err(422, 'validation_error', 'Algunos datos no son válidos.', {
          fields: { base_version: 'Debe ser un número entero.' },
        })
      }
      if (body.base_revision !== p!.revision || body.base_version !== cur.n) {
        return err(409, 'version_conflict', 'El proyecto cambió en otro lugar.', {
          current_version: cur.n,
          current_revision: p!.revision,
          current_version_id: cur.id,
        })
      }
      const now = new Date()
      const iso = now.toISOString()
      let v = cur
      if (
        cur.kind === 'autosave' &&
        now.getTime() - Date.parse(cur.created_at) < AUTOSAVE_WINDOW_MS
      ) {
        cur.content = structuredClone(body.content)
        cur.size = contentSize(body.content)
        cur.updated_at = iso
      } else {
        v = makeVersion(st, p!, 'autosave', body.content, iso)
        p!.currentId = v.id
      }
      p!.updated_at = iso
      p!.revision++
      save()
      return HttpResponse.json({ version_id: v.id, n: v.n, revision: p!.revision })
    }),
  ),

  http.post(
    `${A}/projects/:id/versions`,
    owned(async ({ request }, p) => {
      const text = await request.text()
      const body = (text ? JSON.parse(text) : {}) as { label?: unknown }
      const label = typeof body.label === 'string' && body.label.trim() ? body.label.trim() : null
      const st = projectsState()
      const iso = new Date().toISOString()
      const v = makeVersion(st, p!, 'manual', current(p!).content, iso, label)
      p!.currentId = v.id
      p!.updated_at = iso
      p!.revision++
      save()
      return HttpResponse.json(toVersion(v), { status: 201 })
    }),
  ),

  http.get(
    `${A}/projects/:id/versions`,
    owned((_info, p) => HttpResponse.json([...p!.versions].reverse().map(toVersion))),
  ),

  http.get(
    `${A}/projects/:id/versions/:vid`,
    owned(({ params }, p) => {
      const v = p!.versions.find((x) => x.id === params.vid)
      if (!v) return err(404, 'not_found', 'Versión no encontrada.')
      return HttpResponse.json(toVersionDetail(v))
    }),
  ),

  http.post(
    `${A}/projects/:id/versions/:vid/restore`,
    owned(({ params }, p) => {
      const src = p!.versions.find((x) => x.id === params.vid)
      if (!src) return err(404, 'not_found', 'Versión no encontrada.')
      const st = projectsState()
      const iso = new Date().toISOString()
      const v = makeVersion(st, p!, 'manual', src.content, iso, `Restaurada de la versión ${src.n}`)
      p!.currentId = v.id
      p!.updated_at = iso
      p!.revision++
      save()
      return HttpResponse.json(toProject(p!))
    }),
  ),
]
