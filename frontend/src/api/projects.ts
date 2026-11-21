/**
 * Proyectos con versiones (contrato §4 "Proyectos" y §5 "contenido").
 * Tipos escritos a mano: el contrato sólo fija rutas y cuerpos; los campos de respuesta marcados con
 * PROPUESTA son los que el frontend asume hasta que exista el OpenAPI del backend (LD-3).
 */
import { api, apiUrl } from './client'
import type { ISODateTime, UUID } from './types'

export type ProjectModule = 'fpga'

/** Un archivo del proyecto JG FPGA (§5). */
export interface FpgaFile {
  name: string
  role: 'design' | 'sim' | 'constraints' | string
  text: string
}

/** Contenido de un proyecto FPGA: lo que produce `window.JGFPGA.getProject()` (§5, §7). */
export interface FpgaContent {
  format: 'basys3-sim-project'
  version: 1
  name: string
  top: string
  simTop: string
  files: FpgaFile[]
  report: Record<string, unknown> | null
}

/** La API trata `content` como JSON opaco (validado por tamaño y `format`). */
export type ProjectContent = FpgaContent | Record<string, unknown>

export const FPGA_FORMAT = 'basys3-sim-project'

/**
 * Elemento de `GET /projects`.
 * PROPUESTA AL CONTRATO: campos `id, name, module, current_version_id, current_version_n, revision, created_at,
 * updated_at` (el contrato sólo fija `revision`).
 */
export interface ProjectSummary {
  id: UUID
  name: string
  module: ProjectModule
  /** Versión actual: es la que se manda como `base_version` en el autoguardado. */
  current_version_id: UUID
  current_version_n: number
  /** Sube en CADA guardado (también al sobrescribir la versión autosave abierta), contrato §6.1. */
  revision: number
  created_at: ISODateTime
  /** Última edición (cualquier guardado o renombrado). */
  updated_at: ISODateTime
}

/** `GET /projects/{id}` y `POST /projects`: incluye `content` de la versión actual. */
export interface Project extends ProjectSummary {
  content: ProjectContent
}

export type VersionKind = 'autosave' | 'manual'

/** Elemento de `GET /projects/{id}/versions` (PROPUESTA: `size` en bytes del JSON de `content`). */
export interface ProjectVersion {
  id: UUID
  n: number
  kind: VersionKind
  label: string | null
  size: number
  created_at: ISODateTime
  /** Última vez que se sobrescribió (la versión autosave abierta se reescribe). */
  updated_at?: ISODateTime
}

/** `GET /projects/{id}/versions/{vid}`. */
export interface ProjectVersionDetail extends ProjectVersion {
  content: ProjectContent
}

export interface CreateProjectRequest {
  name: string
  module: ProjectModule
  content: ProjectContent
}

/**
 * `PUT /projects/{id}/autosave` (contrato §4 y §6.1): `base_version` es el `id` de la versión actual que conoce
 * el cliente y `base_revision` su revisión; si la revisión no es la actual ⇒ 409 `version_conflict`.
 */
export interface AutosaveRequest {
  content: ProjectContent
  base_version: UUID
  base_revision: number
}

export interface AutosaveResponse {
  version_id: UUID
  n: number
  revision: number
}

/** `details` del 409 `version_conflict` (contrato §6.1). */
export interface VersionConflictDetails {
  current_version?: UUID
  current_revision?: number
}

const enc = encodeURIComponent

export const projectsApi = {
  list: (module?: ProjectModule) => api.get<ProjectSummary[]>('/projects', { query: { module } }),
  create: (body: CreateProjectRequest) => api.post<Project>('/projects', body),
  get: (id: UUID) => api.get<Project>(`/projects/${enc(id)}`),
  rename: (id: UUID, name: string) => api.patch<Project>(`/projects/${enc(id)}`, { name }),
  remove: (id: UUID) => api.delete<void>(`/projects/${enc(id)}`),
  autosave: (id: UUID, body: AutosaveRequest, opts?: { signal?: AbortSignal }) =>
    api.put<AutosaveResponse>(`/projects/${enc(id)}/autosave`, body, opts),
  createVersion: (id: UUID, label?: string) =>
    api.post<ProjectVersion>(`/projects/${enc(id)}/versions`, label ? { label } : {}),
  listVersions: (id: UUID) => api.get<ProjectVersion[]>(`/projects/${enc(id)}/versions`),
  getVersion: (id: UUID, vid: UUID) =>
    api.get<ProjectVersionDetail>(`/projects/${enc(id)}/versions/${enc(vid)}`),
  /** PROPUESTA: responde el `Project` con la versión restaurada como actual (copia nueva, kind manual). */
  restore: (id: UUID, vid: UUID) =>
    api.post<Project>(`/projects/${enc(id)}/versions/${enc(vid)}/restore`),
}

/**
 * Autoguardado "de despedida" (`beforeunload`/`pagehide`): `fetch` con `keepalive`, sin esperar respuesta
 * ni renovar la sesión. Best effort: los navegadores limitan el cuerpo de `keepalive` a ~64 KB.
 * Devuelve `false` si no se pudo ni intentar.
 */
export function autosaveKeepalive(id: UUID, body: AutosaveRequest): boolean {
  if (typeof fetch !== 'function') return false
  try {
    void fetch(apiUrl(`/projects/${enc(id)}/autosave`), {
      method: 'PUT',
      keepalive: true,
      credentials: 'include',
      headers: {
        Accept: 'application/json',
        'Content-Type': 'application/json',
        'X-Requested-With': 'labdigital',
      },
      body: JSON.stringify(body),
    }).catch(() => {})
    return true
  } catch {
    return false
  }
}

/** Tamaño en bytes del JSON de un contenido (lo que la API compara con el límite de 2 MB). */
export function contentSize(content: unknown): number {
  return new TextEncoder().encode(JSON.stringify(content)).length
}

/** Proyecto FPGA inicial válido (para crear desde la lista sin abrir el simulador). */
export function starterFpgaContent(name: string): FpgaContent {
  return {
    format: FPGA_FORMAT,
    version: 1,
    name,
    top: 'top',
    simTop: '',
    files: [
      {
        name: 'top.vhd',
        role: 'design',
        text: [
          'library ieee;',
          'use ieee.std_logic_1164.all;',
          '',
          'entity top is',
          '  port (',
          '    sw  : in  std_logic_vector(15 downto 0);',
          '    led : out std_logic_vector(15 downto 0)',
          '  );',
          'end entity top;',
          '',
          'architecture rtl of top is',
          'begin',
          '  led <= sw;',
          'end architecture rtl;',
          '',
        ].join('\n'),
      },
    ],
    report: null,
  }
}
