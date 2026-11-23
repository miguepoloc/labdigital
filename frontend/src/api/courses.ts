/**
 * Cursos, labs y equipos (contrato §4). Tipos escritos a mano.
 * PROPUESTA AL CONTRATO: §4 fija rutas y cuerpos de petición, pero no la forma de las respuestas;
 * el frontend asume las interfaces de este archivo (marcadas con «propuesta» donde añaden campos).
 */
import { api, apiUrl } from './client'
import type { ISODateTime, UUID } from './types'

export type CourseRole = 'docente' | 'estudiante'
export type MembershipStatus = 'pending' | 'active' | 'rejected' | 'removed'

/** `GET /courses` y `GET /courses/{id}`. */
export interface Course {
  id: UUID
  name: string
  period: string
  description: string
  owner_id: UUID
  /** Propuesta: nombre del docente para mostrarlo sin otra petición. */
  owner_name: string
  /** Propuesta: mi rol y estado de membresía en este curso. */
  my_role: CourseRole
  my_status: MembershipStatus
  /** Sólo para el docente (null para estudiantes). */
  join_code: string | null
  created_at: ISODateTime
  archived_at: ISODateTime | null
  /** Propuesta: contadores para la lista (sólo docente; null para estudiantes). */
  student_count?: number | null
  pending_count?: number | null
}

export interface CourseInput {
  name: string
  period: string
  description: string
}

/** `GET /courses/{id}/members?status=`. */
export interface Member {
  user_id: UUID
  full_name: string
  email: string
  role: CourseRole
  status: MembershipStatus
  requested_at: ISODateTime
}

export type DeadlinePolicy = 'strict' | 'late_marked' | 'none'
export type TeamMode = 'individual' | 'team'

export interface GradeScale {
  type: 'numeric' | 'pass_fail'
  min?: number
  max?: number
  decimals?: number
  /** Nota mínima aprobatoria (sólo numérica). */
  pass_mark?: number
}

export type SubmissionStatus = 'submitted' | 'returned' | 'graded'

/** Propuesta: resumen de mi última entrega dentro de `Lab` (evita N peticiones en la lista). */
export interface MySubmissionSummary {
  id: UUID
  attempt: number
  status: SubmissionStatus
  is_late: boolean
  submitted_at: ISODateTime
  grade: number | null
}

export interface Lab {
  id: UUID
  course_id: UUID
  title: string
  statement_md: string
  module: string
  published_at: ISODateTime | null
  opens_at: ISODateTime | null
  due_at: ISODateTime | null
  deadline_policy: DeadlinePolicy
  team_mode: TeamMode
  max_team_size: number | null
  grade_scale: GradeScale
  allow_resubmission: boolean
  created_at: ISODateTime
  my_submission?: MySubmissionSummary | null
}

export interface LabInput {
  title: string
  statement_md: string
  module: string
  opens_at?: ISODateTime | null
  due_at?: ISODateTime | null
  deadline_policy: DeadlinePolicy
  team_mode: TeamMode
  max_team_size?: number | null
  grade_scale: GradeScale
  allow_resubmission: boolean
}

/** Integrante de un equipo (contrato §6.1: `{id, full_name}`, no `user_id` como en `Member`). */
export interface TeamMember {
  id: UUID
  full_name: string
}

/** `GET /labs/{id}/teams`. */
export interface Team {
  id: UUID
  lab_id: UUID
  name: string
  /** Sólo visible para sus miembros y el docente. */
  join_code: string | null
  locked: boolean
  members: TeamMember[]
}

const enc = encodeURIComponent

export const coursesApi = {
  list: () => api.get<Course[]>('/courses'),
  get: (id: UUID) => api.get<Course>(`/courses/${enc(id)}`),
  create: (body: CourseInput) => api.post<Course>('/courses', body),
  update: (id: UUID, body: Partial<CourseInput>) => api.patch<Course>(`/courses/${enc(id)}`, body),
  rotateCode: (id: UUID) => api.post<{ join_code: string }>(`/courses/${enc(id)}/join-code/rotate`),
  /** → membresía `pending` (propuesta: devuelve el `Course` con `my_status`). */
  join: (code: string) => api.post<Course>('/courses/join', { code }),
  members: (id: UUID, status?: MembershipStatus) =>
    api.get<Member[]>(`/courses/${enc(id)}/members`, { query: { status } }),
  memberAction: (id: UUID, uid: UUID, action: 'approve' | 'reject' | 'remove') =>
    api.post<void>(`/courses/${enc(id)}/members/${enc(uid)}/${action}`),
  /** URL de descarga directa (GET con cookies). */
  gradesCsvUrl: (id: UUID) => apiUrl(`/courses/${enc(id)}/grades.csv`),
}

export const labsApi = {
  list: (courseId: UUID) => api.get<Lab[]>(`/courses/${enc(courseId)}/labs`),
  create: (courseId: UUID, body: LabInput) => api.post<Lab>(`/courses/${enc(courseId)}/labs`, body),
  get: (id: UUID) => api.get<Lab>(`/labs/${enc(id)}`),
  update: (id: UUID, body: Partial<LabInput>) => api.patch<Lab>(`/labs/${enc(id)}`, body),
  publish: (id: UUID) => api.post<Lab>(`/labs/${enc(id)}/publish`),
}

/** `POST /labs/{id}/teams` como docente (LD-18): equipo sin el docente, vacío o con integrantes. */
export interface TeamInput {
  name: string
  member_ids?: UUID[]
}

/** `POST /labs/{id}/teams/bulk`: crea «prefix 1..count» vacíos (salta nombres ya usados). */
export interface BulkTeamsInput {
  count: number
  prefix?: string
}

export const teamsApi = {
  list: (labId: UUID) => api.get<Team[]>(`/labs/${enc(labId)}/teams`),
  /** Estudiante: crea su equipo y entra. Devuelve el `Team` completo (con `join_code`). */
  create: (labId: UUID, name: string) => api.post<Team>(`/labs/${enc(labId)}/teams`, { name }),
  join: (labId: UUID, code: string) =>
    api.post<Team | undefined>(`/labs/${enc(labId)}/teams/join`, { code }),
  leave: (teamId: UUID) => api.post<void>(`/teams/${enc(teamId)}/leave`),
  /** Docente: reemplaza integrantes; quien estuviera en otro equipo del lab se mueve aquí. */
  setMembers: (teamId: UUID, userIds: UUID[]) =>
    api.put<Team>(`/teams/${enc(teamId)}/members`, userIds),
  lock: (teamId: UUID) => api.post<Team | undefined>(`/teams/${enc(teamId)}/lock`),
  unlock: (teamId: UUID) => api.post<Team | undefined>(`/teams/${enc(teamId)}/unlock`),
  /** Docente (LD-18). */
  createAsTeacher: (labId: UUID, body: TeamInput) =>
    api.post<Team>(`/labs/${enc(labId)}/teams`, body),
  bulk: (labId: UUID, body: BulkTeamsInput) =>
    api.post<Team[]>(`/labs/${enc(labId)}/teams/bulk`, body),
  unassigned: (labId: UUID) => api.get<TeamMember[]>(`/labs/${enc(labId)}/teams/unassigned`),
  autoAssign: (labId: UUID) => api.post<Team[]>(`/labs/${enc(labId)}/teams/auto-assign`),
  rename: (teamId: UUID, name: string) => api.patch<Team>(`/teams/${enc(teamId)}`, { name }),
  remove: (teamId: UUID) => api.delete<void>(`/teams/${enc(teamId)}`),
}
