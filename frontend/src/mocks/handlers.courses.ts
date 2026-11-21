/**
 * API simulada (MSW) de cursos, labs, equipos, entregas, archivos y lectura mínima de proyectos (LD-8b).
 * Se registran ANTES de los handlers de `handlers.ts`; el primero (`/*` sin respuesta) sólo asegura que
 * existan los usuarios demo y deja pasar la petición al siguiente handler.
 *
 * TEMPORAL: `GET /projects` y `GET /projects/:id/versions` existen aquí para el diálogo de entrega; cuando
 * LD-8a aporte sus mocks de proyectos, conviene quedarse con los suyos y borrar los de este archivo.
 */
import { http, HttpResponse, type HttpResponseResolver } from 'msw'
import type { CourseInput, GradeScale, LabInput, MembershipStatus } from '@/api/courses'
import type { FileKind, ReviewInput, SubmissionInput } from '@/api/submissions'
import { config } from '@/config'
import { deadlineState, validateGrade } from '@/pages/app/labs/labRules'
import {
  ALLOWED_EXTENSIONS,
  MAX_FILE_BYTES,
  MAX_SUBMISSION_BYTES,
  extensionOf,
} from '@/pages/app/submissions/uploadRules'
import { currentUser, type MockUser } from './db'
import { findMockProject } from './handlers.projects'
import {
  cdb,
  ensureCourseUsers,
  newId,
  userById,
  type MCourse,
  type MLab,
  type MProject,
  type MSubmission,
  type MTeam,
} from './db.courses'

const A = config.apiBase

function err(status: number, code: string, message: string, details?: Record<string, unknown>) {
  return HttpResponse.json({ error: { code, message, details } }, { status })
}
const validation = (fields: Record<string, string>) =>
  err(422, 'validation_error', 'Datos no válidos.', { fields })
const forbidden = () => err(403, 'forbidden', 'No tiene permiso.')
const notFound = () => err(404, 'not_found', 'No encontrado.')
const noContent = () => new HttpResponse(null, { status: 204 })

type Ctx = Parameters<HttpResponseResolver>[0] & { user: MockUser }

/** Sesión obligatoria + CSRF en mutaciones (como `authed` de handlers.ts). */
function authed(resolver: (ctx: Ctx) => Response | Promise<Response>): HttpResponseResolver {
  return async (info) => {
    if (
      info.request.method !== 'GET' &&
      info.request.headers.get('X-Requested-With') !== 'labdigital'
    ) {
      return err(403, 'csrf_rejected', 'Petición rechazada (CSRF).')
    }
    const user = currentUser()
    if (!user) return err(401, 'unauthenticated', 'No ha iniciado sesión.')
    return resolver({ ...info, user })
  }
}

function genCode(len = 6): string {
  const abc = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789'
  let s = ''
  for (let i = 0; i < len; i++) s += abc[Math.floor(Math.random() * abc.length)]
  return s
}

// ---- Permisos ----

function course(id: unknown) {
  return cdb.courses.find((c) => c.id === id)
}
function membership(courseId: string, userId: string) {
  return cdb.memberships.find((m) => m.course_id === courseId && m.user_id === userId)
}
function roleIn(c: MCourse, userId: string): 'docente' | 'estudiante' | null {
  if (c.owner_id === userId) return 'docente'
  return membership(c.id, userId)?.status === 'active' ? 'estudiante' : null
}
function labOf(id: unknown) {
  const lab = cdb.labs.find((l) => l.id === id)
  const c = lab ? course(lab.course_id) : undefined
  return lab && c ? { lab, course: c } : null
}
function myTeam(labId: string, userId: string): MTeam | undefined {
  return cdb.teams.find((t) => t.lab_id === labId && t.member_ids.includes(userId))
}

// ---- Serialización ----

function toCourse(c: MCourse, userId: string) {
  const mine = c.owner_id === userId
  const m = membership(c.id, userId)
  const students = cdb.memberships.filter((x) => x.course_id === c.id)
  return {
    id: c.id,
    name: c.name,
    period: c.period,
    description: c.description,
    owner_id: c.owner_id,
    owner_name: userById(c.owner_id)?.full_name ?? '',
    my_role: mine ? 'docente' : 'estudiante',
    my_status: mine ? 'active' : (m?.status ?? 'removed'),
    join_code: mine ? c.join_code : null,
    created_at: c.created_at,
    archived_at: c.archived_at,
    student_count: mine ? students.filter((x) => x.status === 'active').length : null,
    pending_count: mine ? students.filter((x) => x.status === 'pending').length : null,
  }
}

function groupKey(s: Pick<MSubmission, 'student_id' | 'team_id'>) {
  return s.team_id ? `t:${s.team_id}` : `u:${s.student_id}`
}

function visibleTo(s: MSubmission, userId: string, isTeacher: boolean) {
  if (isTeacher) return true
  if (s.student_id === userId || s.submitted_by === userId) return true
  const team = s.team_id ? cdb.teams.find((t) => t.id === s.team_id) : undefined
  return !!team?.member_ids.includes(userId)
}

function currentGrade(subId: string): number | null {
  const reviews = cdb.reviews.filter((r) => r.submission_id === subId && r.grade !== null)
  return reviews.length ? reviews[reviews.length - 1]!.grade : null
}

function toSubmission(s: MSubmission, withContent = false) {
  const team = s.team_id ? cdb.teams.find((t) => t.id === s.team_id) : undefined
  const project = cdb.projects.find((p) => p.id === s.project_id)
  const version = project?.versions.find((v) => v.id === s.version_id)
  const memberIds = team ? team.member_ids : s.student_id ? [s.student_id] : []
  return {
    id: s.id,
    lab_id: s.lab_id,
    attempt: s.attempt,
    student_id: s.student_id,
    team_id: s.team_id,
    submitted_by: { id: s.submitted_by, full_name: userById(s.submitted_by)?.full_name ?? '' },
    team_name: team?.name ?? null,
    members: memberIds.map((id) => ({ id, full_name: userById(id)?.full_name ?? '' })),
    project_id: s.project_id,
    project_name: project?.name ?? '',
    version_id: s.version_id,
    version_n: version?.n ?? 0,
    submitted_at: s.submitted_at,
    is_late: s.is_late,
    status: s.status,
    grade: currentGrade(s.id),
    files: s.file_ids
      .map((id) => cdb.files.find((f) => f.id === id))
      .filter((f) => !!f)
      .map((f) => ({
        id: f.id,
        kind: f.kind,
        name: f.name,
        size: f.size,
        mime: f.mime,
        sha256: f.sha256,
      })),
    reviews: cdb.reviews
      .filter((r) => r.submission_id === s.id)
      .map((r) => ({ ...r, reviewer_name: userById(r.reviewer_id)?.full_name ?? '' })),
    ...(withContent
      ? {
          content: {
            format: 'basys3-sim-project',
            version: 1,
            name: project?.name ?? '',
            top: 'top',
            simTop: 'tb',
            files: [],
            report: null,
          },
        }
      : {}),
  }
}

function mySubmissions(lab: MLab, userId: string) {
  const team = myTeam(lab.id, userId)
  return cdb.submissions.filter(
    (s) =>
      s.lab_id === lab.id &&
      (s.student_id === userId || (team && s.team_id === team.id) || s.submitted_by === userId),
  )
}

function toLab(lab: MLab, userId: string, isTeacher: boolean) {
  const mine = isTeacher ? [] : mySubmissions(lab, userId)
  const last = mine[mine.length - 1]
  return {
    ...lab,
    my_submission: last
      ? {
          id: last.id,
          attempt: last.attempt,
          status: last.status,
          is_late: last.is_late,
          submitted_at: last.submitted_at,
          grade: currentGrade(last.id),
        }
      : null,
  }
}

function toTeam(t: MTeam, userId: string, isTeacher: boolean) {
  return {
    id: t.id,
    lab_id: t.lab_id,
    name: t.name,
    join_code: isTeacher || t.member_ids.includes(userId) ? t.join_code : null,
    locked: t.locked,
    members: t.member_ids.map((id) => ({ user_id: id, full_name: userById(id)?.full_name ?? '' })),
  }
}

// ---- Validaciones ----

function validateCourse(body: Partial<CourseInput>, partial: boolean) {
  const fields: Record<string, string> = {}
  if ((!partial || body.name !== undefined) && !body.name?.trim())
    fields.name = 'Escriba el nombre.'
  if ((!partial || body.period !== undefined) && !body.period?.trim())
    fields.period = 'Indique el periodo.'
  return fields
}

function validateScaleServer(s: GradeScale | undefined): string | null {
  if (!s || (s.type !== 'numeric' && s.type !== 'pass_fail')) return 'Escala no válida.'
  if (s.type === 'numeric') {
    if (typeof s.min !== 'number' || typeof s.max !== 'number' || s.max <= s.min)
      return 'El máximo debe ser mayor que el mínimo.'
  }
  return null
}

function validateLab(body: Partial<LabInput>, partial: boolean) {
  const fields: Record<string, string> = {}
  const has = (k: keyof LabInput) => !partial || body[k] !== undefined
  if (has('title') && !body.title?.trim()) fields.title = 'Escriba el título.'
  if (has('deadline_policy') && !['strict', 'late_marked', 'none'].includes(body.deadline_policy!))
    fields.deadline_policy = 'Política no válida.'
  if (body.deadline_policy && body.deadline_policy !== 'none' && has('due_at') && !body.due_at)
    fields.due_at = 'Indique la fecha límite.'
  if (has('team_mode') && !['individual', 'team'].includes(body.team_mode!))
    fields.team_mode = 'Modalidad no válida.'
  if (
    body.team_mode === 'team' &&
    body.max_team_size !== undefined &&
    body.max_team_size !== null
  ) {
    if (!Number.isInteger(body.max_team_size) || body.max_team_size < 2)
      fields.max_team_size = 'Tamaño no válido.'
  }
  if (has('grade_scale')) {
    const e = validateScaleServer(body.grade_scale)
    if (e) fields.grade_scale = e
  }
  return fields
}

// ---- CSV ----

function csvCell(v: string) {
  return /[",\n;]/.test(v) ? `"${v.replace(/"/g, '""')}"` : v
}

/** Proyecto del usuario: primero los mocks de proyectos (LD-9, los definitivos), si no los de este módulo. */
function lookupProject(id: string, userId: string): MProject | undefined {
  const own = cdb.projects.find((p) => p.id === id && p.owner_id === userId)
  if (own) return own
  const m = findMockProject(id)
  if (!m || m.ownerId !== userId || m.deleted_at) return undefined
  return {
    id: m.id,
    owner_id: m.ownerId,
    name: m.name,
    module: m.module,
    updated_at: m.updated_at,
    versions: m.versions.map((v) => ({
      id: v.id,
      n: v.n,
      label: v.label,
      kind: v.kind,
      size: v.size,
      created_at: v.created_at,
    })),
  }
}

export const courseHandlers = [
  // Asegura los usuarios demo antes de cualquier petición (también del login) y deja pasar.
  http.all(`${A}/*`, () => {
    ensureCourseUsers()
  }),

  // ---- Cursos ----
  http.get(
    `${A}/courses`,
    authed(({ user }) =>
      HttpResponse.json(
        cdb.courses
          .filter((c) => {
            if (c.owner_id === user.id) return true
            const m = membership(c.id, user.id)
            return !!m && m.status !== 'removed'
          })
          .map((c) => toCourse(c, user.id)),
      ),
    ),
  ),

  http.post(
    `${A}/courses`,
    authed(async ({ request, user }) => {
      const body = (await request.json()) as CourseInput
      const fields = validateCourse(body, false)
      if (Object.keys(fields).length) return validation(fields)
      const c: MCourse = {
        id: newId('co'),
        name: body.name.trim(),
        period: body.period.trim(),
        description: body.description?.trim() ?? '',
        owner_id: user.id,
        join_code: genCode(),
        created_at: new Date().toISOString(),
        archived_at: null,
      }
      cdb.courses.push(c)
      return HttpResponse.json(toCourse(c, user.id), { status: 201 })
    }),
  ),

  http.post(
    `${A}/courses/join`,
    authed(async ({ request, user }) => {
      const { code } = (await request.json()) as { code?: string }
      const normalized = (code ?? '').trim().toUpperCase()
      if (!normalized) return validation({ code: 'Escriba el código.' })
      const c = cdb.courses.find((x) => x.join_code === normalized && !x.archived_at)
      if (!c) return err(404, 'invalid_code', 'Código no válido.')
      if (c.owner_id === user.id) return err(409, 'already_member', 'Ya es el docente.')
      const m = membership(c.id, user.id)
      if (m && (m.status === 'active' || m.status === 'pending'))
        return err(409, 'already_member', 'Ya pertenece o tiene solicitud.')
      if (m) {
        m.status = 'pending'
        m.requested_at = new Date().toISOString()
      } else {
        cdb.memberships.push({
          course_id: c.id,
          user_id: user.id,
          role: 'estudiante',
          status: 'pending',
          requested_at: new Date().toISOString(),
        })
      }
      return HttpResponse.json(toCourse(c, user.id), { status: 201 })
    }),
  ),

  http.get(
    `${A}/courses/:id`,
    authed(({ params, user }) => {
      const c = course(params.id)
      if (!c) return notFound()
      if (c.owner_id !== user.id && !membership(c.id, user.id)) return forbidden()
      return HttpResponse.json(toCourse(c, user.id))
    }),
  ),

  http.patch(
    `${A}/courses/:id`,
    authed(async ({ params, request, user }) => {
      const c = course(params.id)
      if (!c) return notFound()
      if (c.owner_id !== user.id) return forbidden()
      const body = (await request.json()) as Partial<CourseInput>
      const fields = validateCourse(body, true)
      if (Object.keys(fields).length) return validation(fields)
      if (body.name !== undefined) c.name = body.name.trim()
      if (body.period !== undefined) c.period = body.period.trim()
      if (body.description !== undefined) c.description = body.description.trim()
      return HttpResponse.json(toCourse(c, user.id))
    }),
  ),

  http.post(
    `${A}/courses/:id/join-code/rotate`,
    authed(({ params, user }) => {
      const c = course(params.id)
      if (!c) return notFound()
      if (c.owner_id !== user.id) return forbidden()
      c.join_code = genCode()
      return HttpResponse.json({ join_code: c.join_code })
    }),
  ),

  http.get(
    `${A}/courses/:id/members`,
    authed(({ params, request, user }) => {
      const c = course(params.id)
      if (!c) return notFound()
      if (c.owner_id !== user.id) return forbidden()
      const status = new URL(request.url).searchParams.get('status') as MembershipStatus | null
      return HttpResponse.json(
        cdb.memberships
          .filter((m) => m.course_id === c.id && (!status || m.status === status))
          .map((m) => {
            const u = userById(m.user_id)
            return {
              user_id: m.user_id,
              full_name: u?.full_name ?? '',
              email: u?.email ?? '',
              role: m.role,
              status: m.status,
              requested_at: m.requested_at,
            }
          }),
      )
    }),
  ),

  http.post(
    `${A}/courses/:id/members/:uid/:action`,
    authed(({ params, user }) => {
      const c = course(params.id)
      if (!c) return notFound()
      if (c.owner_id !== user.id) return forbidden()
      const m = membership(c.id, String(params.uid))
      if (!m) return notFound()
      const action = params.action
      if (action === 'approve' || action === 'reject') {
        if (m.status !== 'pending')
          return err(409, 'not_pending', 'La solicitud ya no está pendiente.')
        m.status = action === 'approve' ? 'active' : 'rejected'
      } else if (action === 'remove') {
        m.status = 'removed'
        for (const t of cdb.teams) t.member_ids = t.member_ids.filter((x) => x !== m.user_id)
      } else return notFound()
      return noContent()
    }),
  ),

  http.get(
    `${A}/courses/:id/grades.csv`,
    authed(({ params, user }) => {
      const c = course(params.id)
      if (!c) return notFound()
      if (c.owner_id !== user.id) return forbidden()
      const labs = cdb.labs.filter((l) => l.course_id === c.id && l.published_at)
      const students = cdb.memberships.filter((m) => m.course_id === c.id && m.status === 'active')
      const rows = [['estudiante', 'correo', ...labs.map((l) => l.title)]]
      for (const m of students) {
        const u = userById(m.user_id)
        const grades = labs.map((l) => {
          const team = myTeam(l.id, m.user_id)
          const subs = cdb.submissions.filter(
            (s) =>
              s.lab_id === l.id && (s.student_id === m.user_id || (team && s.team_id === team.id)),
          )
          const g = subs.length ? currentGrade(subs[subs.length - 1]!.id) : null
          return g === null ? '' : String(g)
        })
        rows.push([u?.full_name ?? '', u?.email ?? '', ...grades])
      }
      const csv = rows.map((r) => r.map(csvCell).join(',')).join('\n') + '\n'
      return new HttpResponse(csv, {
        headers: {
          'Content-Type': 'text/csv; charset=utf-8',
          'Content-Disposition': 'attachment; filename="notas.csv"',
        },
      })
    }),
  ),

  // ---- Labs ----
  http.get(
    `${A}/courses/:id/labs`,
    authed(({ params, user }) => {
      const c = course(params.id)
      if (!c) return notFound()
      const role = roleIn(c, user.id)
      if (!role) return forbidden()
      const teacher = role === 'docente'
      return HttpResponse.json(
        cdb.labs
          .filter((l) => l.course_id === c.id && (teacher || l.published_at))
          .map((l) => toLab(l, user.id, teacher)),
      )
    }),
  ),

  http.post(
    `${A}/courses/:id/labs`,
    authed(async ({ params, request, user }) => {
      const c = course(params.id)
      if (!c) return notFound()
      if (c.owner_id !== user.id) return forbidden()
      const body = (await request.json()) as LabInput
      const fields = validateLab(body, false)
      if (Object.keys(fields).length) return validation(fields)
      const lab: MLab = {
        id: newId('lb'),
        course_id: c.id,
        title: body.title.trim(),
        statement_md: body.statement_md ?? '',
        module: body.module || 'fpga',
        published_at: null,
        opens_at: body.opens_at ?? null,
        due_at: body.deadline_policy === 'none' ? (body.due_at ?? null) : (body.due_at ?? null),
        deadline_policy: body.deadline_policy,
        team_mode: body.team_mode,
        max_team_size: body.team_mode === 'team' ? (body.max_team_size ?? null) : null,
        grade_scale: body.grade_scale,
        allow_resubmission: !!body.allow_resubmission,
        created_at: new Date().toISOString(),
      }
      cdb.labs.push(lab)
      return HttpResponse.json(toLab(lab, user.id, true), { status: 201 })
    }),
  ),

  http.get(
    `${A}/labs/:id`,
    authed(({ params, user }) => {
      const found = labOf(params.id)
      if (!found) return notFound()
      const role = roleIn(found.course, user.id)
      if (!role) return forbidden()
      if (role === 'estudiante' && !found.lab.published_at) return notFound()
      return HttpResponse.json(toLab(found.lab, user.id, role === 'docente'))
    }),
  ),

  http.patch(
    `${A}/labs/:id`,
    authed(async ({ params, request, user }) => {
      const found = labOf(params.id)
      if (!found) return notFound()
      if (found.course.owner_id !== user.id) return forbidden()
      const body = (await request.json()) as Partial<LabInput>
      const fields = validateLab({ ...found.lab, ...body }, true)
      if (Object.keys(fields).length) return validation(fields)
      Object.assign(found.lab, body)
      if (found.lab.team_mode === 'individual') found.lab.max_team_size = null
      return HttpResponse.json(toLab(found.lab, user.id, true))
    }),
  ),

  http.post(
    `${A}/labs/:id/publish`,
    authed(({ params, user }) => {
      const found = labOf(params.id)
      if (!found) return notFound()
      if (found.course.owner_id !== user.id) return forbidden()
      found.lab.published_at ??= new Date().toISOString()
      return HttpResponse.json(toLab(found.lab, user.id, true))
    }),
  ),

  // ---- Equipos ----
  http.get(
    `${A}/labs/:id/teams`,
    authed(({ params, user }) => {
      const found = labOf(params.id)
      if (!found) return notFound()
      const role = roleIn(found.course, user.id)
      if (!role) return forbidden()
      return HttpResponse.json(
        cdb.teams
          .filter((t) => t.lab_id === found.lab.id)
          .map((t) => toTeam(t, user.id, role === 'docente')),
      )
    }),
  ),

  http.post(
    `${A}/labs/:id/teams/join`,
    authed(async ({ params, request, user }) => {
      const found = labOf(params.id)
      if (!found) return notFound()
      if (roleIn(found.course, user.id) !== 'estudiante') return forbidden()
      const { code } = (await request.json()) as { code?: string }
      const team = cdb.teams.find(
        (t) => t.lab_id === found.lab.id && t.join_code === (code ?? '').trim().toUpperCase(),
      )
      if (!team) return err(404, 'invalid_code', 'Código no válido.')
      if (myTeam(found.lab.id, user.id)) return err(409, 'already_in_team', 'Ya tiene equipo.')
      if (team.locked) return err(409, 'team_locked', 'Equipo fijado.')
      const max = found.lab.max_team_size
      if (max && team.member_ids.length >= max) return err(409, 'team_full', 'Equipo completo.')
      team.member_ids.push(user.id)
      return HttpResponse.json(toTeam(team, user.id, false))
    }),
  ),

  http.post(
    `${A}/labs/:id/teams`,
    authed(async ({ params, request, user }) => {
      const found = labOf(params.id)
      if (!found) return notFound()
      if (roleIn(found.course, user.id) !== 'estudiante') return forbidden()
      if (found.lab.team_mode !== 'team')
        return validation({ name: 'Este laboratorio es individual.' })
      const { name } = (await request.json()) as { name?: string }
      if (!name?.trim()) return validation({ name: 'Escriba el nombre del equipo.' })
      if (myTeam(found.lab.id, user.id)) return err(409, 'already_in_team', 'Ya tiene equipo.')
      const team: MTeam = {
        id: newId('tm'),
        lab_id: found.lab.id,
        name: name.trim(),
        join_code: genCode(),
        locked: false,
        member_ids: [user.id],
      }
      cdb.teams.push(team)
      return HttpResponse.json(toTeam(team, user.id, false), { status: 201 })
    }),
  ),

  http.post(
    `${A}/teams/:id/leave`,
    authed(({ params, user }) => {
      const team = cdb.teams.find((t) => t.id === params.id)
      if (!team) return notFound()
      if (!team.member_ids.includes(user.id)) return forbidden()
      if (team.locked) return err(409, 'team_locked', 'Equipo fijado.')
      team.member_ids = team.member_ids.filter((x) => x !== user.id)
      if (!team.member_ids.length && !cdb.submissions.some((s) => s.team_id === team.id)) {
        cdb.teams = cdb.teams.filter((t) => t !== team)
      }
      return noContent()
    }),
  ),

  http.put(
    `${A}/teams/:id/members`,
    authed(async ({ params, request, user }) => {
      const team = cdb.teams.find((t) => t.id === params.id)
      const found = team ? labOf(team.lab_id) : null
      if (!team || !found) return notFound()
      if (found.course.owner_id !== user.id) return forbidden()
      const ids = (await request.json()) as string[]
      if (!Array.isArray(ids)) return validation({ members: 'Lista no válida.' })
      const invalid = ids.filter((id) => roleIn(found.course, id) !== 'estudiante')
      if (invalid.length)
        return validation({ members: 'Hay usuarios que no son estudiantes del curso.' })
      for (const t of cdb.teams) {
        if (t.lab_id === team.lab_id && t !== team)
          t.member_ids = t.member_ids.filter((x) => !ids.includes(x))
      }
      team.member_ids = [...new Set(ids)]
      return HttpResponse.json(toTeam(team, user.id, true))
    }),
  ),

  http.post(
    `${A}/teams/:id/lock`,
    authed(({ params, user }) => {
      const team = cdb.teams.find((t) => t.id === params.id)
      const found = team ? labOf(team.lab_id) : null
      if (!team || !found) return notFound()
      if (found.course.owner_id !== user.id) return forbidden()
      team.locked = true
      return HttpResponse.json(toTeam(team, user.id, true))
    }),
  ),

  // ---- Entregas ----
  http.post(
    `${A}/labs/:id/submissions`,
    authed(async ({ params, request, user }) => {
      const found = labOf(params.id)
      if (!found || !found.lab.published_at) return notFound()
      const { lab } = found
      if (roleIn(found.course, user.id) !== 'estudiante') return forbidden()
      const state = deadlineState(lab)
      if (state === 'not_open') return err(409, 'lab_not_open', 'El laboratorio aún no abre.')
      if (state === 'closed') return err(409, 'deadline_passed', 'La fecha límite ya pasó.')
      const team = lab.team_mode === 'team' ? myTeam(lab.id, user.id) : undefined
      if (lab.team_mode === 'team' && !team) return err(409, 'team_required', 'Necesita un equipo.')
      const body = (await request.json()) as SubmissionInput
      const project = lookupProject(body.project_id, user.id)
      if (!project) return validation({ project_id: 'Elija uno de sus proyectos.' })
      const versionId = body.version_id ?? project.versions[project.versions.length - 1]?.id
      if (!versionId || !project.versions.some((v) => v.id === versionId))
        return validation({ version_id: 'La versión no existe.' })
      const files = (body.file_ids ?? []).map((id) =>
        cdb.files.find((f) => f.id === id && f.owner_id === user.id),
      )
      if (files.some((f) => !f)) return validation({ file_ids: 'Hay archivos que no existen.' })
      const total = files.reduce((acc, f) => acc + f!.size, 0)
      if (total > MAX_SUBMISSION_BYTES)
        return err(413, 'payload_too_large', 'La entrega supera 100 MB.')
      const key = groupKey({ student_id: team ? null : user.id, team_id: team?.id ?? null })
      const previous = cdb.submissions.filter((s) => s.lab_id === lab.id && groupKey(s) === key)
      const last = previous[previous.length - 1]
      if (last && !lab.allow_resubmission && last.status !== 'returned')
        return err(409, 'resubmission_not_allowed', 'No se admiten re-entregas.')
      const s: MSubmission = {
        id: newId('sb'),
        lab_id: lab.id,
        attempt: previous.length + 1,
        student_id: team ? null : user.id,
        team_id: team?.id ?? null,
        submitted_by: user.id,
        project_id: project.id,
        version_id: versionId,
        submitted_at: new Date().toISOString(),
        is_late: state === 'late',
        status: 'submitted',
        file_ids: files.map((f) => f!.id),
      }
      cdb.submissions.push(s)
      return HttpResponse.json(toSubmission(s), { status: 201 })
    }),
  ),

  http.get(
    `${A}/labs/:id/submissions`,
    authed(({ params, user }) => {
      const found = labOf(params.id)
      if (!found) return notFound()
      const role = roleIn(found.course, user.id)
      if (!role) return forbidden()
      const teacher = role === 'docente'
      return HttpResponse.json(
        cdb.submissions
          .filter((s) => s.lab_id === found.lab.id && visibleTo(s, user.id, teacher))
          .map((s) => toSubmission(s)),
      )
    }),
  ),

  http.get(
    `${A}/submissions/:id`,
    authed(({ params, user }) => {
      const s = cdb.submissions.find((x) => x.id === params.id)
      const found = s ? labOf(s.lab_id) : null
      if (!s || !found) return notFound()
      const teacher = found.course.owner_id === user.id
      if (!visibleTo(s, user.id, teacher)) return forbidden()
      return HttpResponse.json(toSubmission(s, true))
    }),
  ),

  http.post(
    `${A}/submissions/:id/reviews`,
    authed(async ({ params, request, user }) => {
      const s = cdb.submissions.find((x) => x.id === params.id)
      const found = s ? labOf(s.lab_id) : null
      if (!s || !found) return notFound()
      if (found.course.owner_id !== user.id) return forbidden()
      const body = (await request.json()) as ReviewInput
      let grade: number | null = null
      if (body.grade !== undefined && body.grade !== null) {
        const check = validateGrade(String(body.grade), found.lab.grade_scale)
        if (!check.ok) return validation({ grade: check.error })
        grade = check.value
      }
      if (grade === null && !body.comment?.trim() && !body.return_for_resubmission)
        return validation({ comment: 'Escriba un comentario.' })
      const r = {
        id: newId('rv'),
        submission_id: s.id,
        reviewer_id: user.id,
        grade,
        comment: body.comment?.trim() ?? '',
        return_for_resubmission: !!body.return_for_resubmission,
        created_at: new Date().toISOString(),
      }
      cdb.reviews.push(r)
      if (r.return_for_resubmission) s.status = 'returned'
      else if (grade !== null) s.status = 'graded'
      return HttpResponse.json({ ...r, reviewer_name: user.full_name }, { status: 201 })
    }),
  ),

  // ---- Archivos ----
  http.post(
    `${A}/files`,
    authed(async ({ request, user }) => {
      const form = await request.formData()
      const file = form.get('file')
      const kind = String(form.get('kind') ?? '') as FileKind
      // Comprobación por forma (no `instanceof File`: en tests el File de jsdom y el de Node difieren).
      if (!file || typeof file === 'string') return validation({ file: 'Falta el archivo.' })
      if (!['report', 'bitstream', 'attachment'].includes(kind))
        return validation({ kind: 'Tipo de archivo no válido.' })
      if (!(ALLOWED_EXTENSIONS as readonly string[]).includes(extensionOf(file.name)))
        return validation({ file: 'Tipo de archivo no permitido.' })
      if (file.size > MAX_FILE_BYTES)
        return err(413, 'payload_too_large', 'El archivo supera 25 MB.')
      const f = {
        id: newId('fi'),
        owner_id: user.id,
        name: file.name,
        size: file.size,
        mime: file.type || 'application/octet-stream',
        sha256: 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855',
        kind,
      }
      cdb.files.push(f)
      return HttpResponse.json(
        { id: f.id, sha256: f.sha256, size: f.size, mime: f.mime },
        { status: 201 },
      )
    }),
  ),

  http.get(
    `${A}/files/:id`,
    authed(({ params }) => {
      const f = cdb.files.find((x) => x.id === params.id)
      if (!f) return notFound()
      return new HttpResponse(`Archivo simulado: ${f.name}`, {
        headers: {
          'Content-Type': f.mime,
          'Content-Disposition': `attachment; filename="${f.name}"`,
        },
      })
    }),
  ),

  // ---- Proyectos (lectura mínima, TEMPORAL hasta los mocks de LD-8a) ----
  http.get(
    `${A}/projects`,
    authed(({ request, user }) => {
      const module = new URL(request.url).searchParams.get('module')
      return HttpResponse.json(
        cdb.projects
          .filter((p) => p.owner_id === user.id && (!module || p.module === module))
          .map((p) => ({
            id: p.id,
            name: p.name,
            module: p.module,
            current_version_id: p.versions[p.versions.length - 1]?.id ?? '',
            current_version_n: p.versions[p.versions.length - 1]?.n ?? 0,
            revision: p.versions.length,
            created_at: p.versions[0]?.created_at ?? p.updated_at,
            updated_at: p.updated_at,
          })),
      )
    }),
  ),

  http.get(
    `${A}/projects/:id/versions`,
    authed(({ params, user }) => {
      const p = cdb.projects.find((x) => x.id === params.id)
      if (!p) return notFound()
      if (p.owner_id !== user.id) return forbidden()
      return HttpResponse.json(
        [...p.versions].reverse().map((v) => ({ ...v, updated_at: v.created_at })),
      )
    }),
  ),
]
