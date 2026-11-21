/**
 * Entregas, revisiones y archivos (contrato §4). Incluye una lectura mínima de proyectos y versiones para el
 * diálogo de entrega; el cliente completo de proyectos lo aporta LD-8a (`src/api/projects.ts`).
 */
import { api, apiUrl, refreshSession } from './client'
import { ApiError, errorFromResponse } from './errors'
import type { SubmissionStatus } from './courses'
import type { ISODateTime, UUID } from './types'

export type FileKind = 'report' | 'bitstream' | 'attachment'

/** `POST /files` → `{id, sha256, size, mime}`. */
export interface UploadedFile {
  id: UUID
  sha256: string
  size: number
  mime: string
}

/** Archivo asociado a una entrega (propuesta: incluye `kind` y `name`). */
export interface SubmissionFile extends UploadedFile {
  kind: FileKind
  name: string
}

/** Revisión tal como la devuelve la API (contrato §6.1). */
export interface Review {
  id: UUID
  reviewer_name: string
  grade: number | null
  comment: string
  returned_for_resubmission: boolean
  created_at: ISODateTime
}

export interface Submission {
  id: UUID
  lab_id: UUID
  attempt: number
  /** Quién entregó y, en labs en equipo, el equipo (contrato §6.1). */
  submitted_by: { id: UUID; full_name: string }
  team: { id: UUID; name: string } | null
  /** Integrantes al entregar. */
  members: { id: UUID; full_name: string }[]
  project_id: UUID
  project_name: string
  version_id: UUID
  version_n: number
  submitted_at: ISODateTime
  is_late: boolean
  status: SubmissionStatus
  /** Nota vigente (la de la última revisión con nota). */
  grade: number | null
  files: SubmissionFile[]
  reviews: Review[]
  /** Sólo en `GET /submissions/{id}` (contrato §6.1): contenido congelado (§5). */
  content?: unknown
}

export interface SubmissionInput {
  project_id: UUID
  version_id?: UUID
  file_ids: UUID[]
}

export interface ReviewInput {
  grade?: number | null
  comment: string
  return_for_resubmission: boolean
}

/**
 * Lectura mínima de proyectos con las formas fijadas en el contrato §6.1 (mismas que `src/api/projects.ts`
 * de LD-9; al integrar, conviene importar de allí y borrar éstas).
 */
export interface ProjectSummary {
  id: UUID
  name: string
  module: string
  current_version_id: UUID
  current_version_n: number
  revision: number
  created_at: ISODateTime
  updated_at: ISODateTime
}

export interface ProjectVersion {
  id: UUID
  n: number
  kind: 'autosave' | 'manual' | 'submitted'
  label: string | null
  size: number
  created_at: ISODateTime
  updated_at?: ISODateTime
}

const enc = encodeURIComponent

export const submissionsApi = {
  create: (labId: UUID, body: SubmissionInput) =>
    api.post<Submission>(`/labs/${enc(labId)}/submissions`, body),
  listForLab: (labId: UUID) => api.get<Submission[]>(`/labs/${enc(labId)}/submissions`),
  get: (id: UUID) => api.get<Submission>(`/submissions/${enc(id)}`),
  review: (id: UUID, body: ReviewInput) =>
    api.post<Submission>(`/submissions/${enc(id)}/reviews`, body),
}

export const projectsReadApi = {
  list: (module = 'fpga') => api.get<ProjectSummary[]>('/projects', { query: { module } }),
  versions: (projectId: UUID) => api.get<ProjectVersion[]>(`/projects/${enc(projectId)}/versions`),
}

export function fileUrl(id: UUID): string {
  return apiUrl(`/files/${enc(id)}`)
}

export interface UploadOptions {
  onProgress?: (loaded: number, total: number) => void
  signal?: AbortSignal
}

function xhrUpload(form: FormData, opts: UploadOptions): Promise<Response> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest()
    xhr.open('POST', apiUrl('/files'))
    xhr.withCredentials = true
    xhr.setRequestHeader('Accept', 'application/json')
    xhr.setRequestHeader('X-Requested-With', 'labdigital')
    xhr.upload.onprogress = (ev) => {
      if (ev.lengthComputable) opts.onProgress?.(ev.loaded, ev.total)
    }
    xhr.onload = () => {
      const headers = new Headers()
      const type = xhr.getResponseHeader('Content-Type')
      if (type) headers.set('Content-Type', type)
      const retry = xhr.getResponseHeader('Retry-After')
      if (retry) headers.set('Retry-After', retry)
      const status = xhr.status === 0 ? 599 : xhr.status
      const nullBody = status === 204 || status === 205 || status === 304
      resolve(new Response(nullBody ? null : xhr.responseText, { status, headers }))
    }
    xhr.onerror = () =>
      reject(new ApiError({ status: 0, code: 'network_error', message: 'network_error' }))
    xhr.onabort = () => reject(new DOMException('Aborted', 'AbortError'))
    opts.signal?.addEventListener('abort', () => xhr.abort(), { once: true })
    xhr.send(form)
  })
}

/**
 * `POST /files` (multipart, campo `file` + `kind`) con progreso de subida (XHR: `fetch` no lo ofrece).
 * Ante un 401 renueva la sesión una vez y reintenta, como el cliente general.
 */
export async function uploadFile(
  file: File,
  kind: FileKind,
  opts: UploadOptions = {},
): Promise<UploadedFile> {
  const build = () => {
    const form = new FormData()
    form.append('file', file, file.name)
    form.append('kind', kind)
    return form
  }
  let res = await xhrUpload(build(), opts)
  if (res.status === 401 && (await refreshSession())) res = await xhrUpload(build(), opts)
  if (!res.ok) throw await errorFromResponse(res)
  return (await res.json()) as UploadedFile
}
