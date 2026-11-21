/**
 * Autoguardado del envoltorio FPGA (LD-9), independiente de Vue para poder probarlo con temporizadores falsos.
 *
 * - `change(content)` reinicia un *debounce* (~5 s); al vencer se hace `PUT /projects/{id}/autosave` con
 *   `{content, base_version, base_revision}` (contrato §4 y §6.1). Los cambios que llegan mientras se guarda se
 *   acumulan y salen en el siguiente guardado (nunca dos peticiones a la vez).
 * - Red caída, 5xx o 429 ⇒ estado `offline` y reintento con espera creciente (o `Retry-After`).
 * - 409 `version_conflict` ⇒ estado `conflict` (sin reintentos) hasta que la página elija `overwrite()` o `reset()`.
 * - Otros errores (413, 422, 403…) ⇒ estado `error`; el contenido queda pendiente para el siguiente intento.
 * - `flushOnExit()` (beforeunload/pagehide): envío best effort con `keepalive`. Como esa respuesta no se lee, si la
 *   página sigue viva el siguiente guardado daría 409 contra sí mismo: se reconoce (revisión = la enviada + 1) y
 *   se reintenta con la base nueva sin molestar al usuario.
 */
import { isApiError } from '@/api/errors'
import type {
  AutosaveRequest,
  AutosaveResponse,
  ProjectContent,
  VersionConflictDetails,
} from '@/api/projects'

export type SaveStatus = 'idle' | 'pending' | 'saving' | 'saved' | 'offline' | 'conflict' | 'error'

export interface SaveBase {
  version: string
  revision: number
}

export interface AutosaverSnapshot {
  status: SaveStatus
  /** `Date.now()` del último guardado confirmado. */
  lastSavedAt: number | null
  /** Último error (en `offline`/`error`). */
  error: unknown
  conflict: VersionConflictDetails | null
  /** Hay contenido sin confirmar en el servidor. */
  dirty: boolean
}

export interface AutosaverOptions {
  base: SaveBase
  save: (body: AutosaveRequest) => Promise<AutosaveResponse>
  /** Envío sin esperar respuesta al salir de la página; devuelve `false` si no se pudo. */
  keepalive?: (body: AutosaveRequest) => boolean
  debounceMs?: number
  retryDelaysMs?: number[]
  onChange?: (s: AutosaverSnapshot) => void
  now?: () => number
}

/** Tiempos por defecto (los tests del envoltorio los acortan). */
export const AUTOSAVE_DEFAULTS = {
  debounceMs: 5000,
  retryDelaysMs: [2000, 5000, 10000, 30000],
}

export class Autosaver {
  private base: SaveBase
  private pending: ProjectContent | null = null
  private inFlight: Promise<void> | null = null
  private debounceTimer: ReturnType<typeof setTimeout> | null = null
  private retryTimer: ReturnType<typeof setTimeout> | null = null
  private attempt = 0
  private keepaliveRevision: number | null = null
  private disposed = false
  private snap: AutosaverSnapshot = {
    status: 'idle',
    lastSavedAt: null,
    error: null,
    conflict: null,
    dirty: false,
  }

  constructor(private readonly opts: AutosaverOptions) {
    this.base = { ...opts.base }
  }

  get snapshot(): Readonly<AutosaverSnapshot> {
    return this.snap
  }

  get currentBase(): Readonly<SaveBase> {
    return this.base
  }

  /** El contenido más reciente que aún no está confirmado en el servidor (o `null`). */
  get unsaved(): ProjectContent | null {
    return this.pending
  }

  private get debounceMs() {
    return this.opts.debounceMs ?? AUTOSAVE_DEFAULTS.debounceMs
  }

  private now() {
    return (this.opts.now ?? Date.now)()
  }

  private set(patch: Partial<AutosaverSnapshot>) {
    this.snap = { ...this.snap, ...patch, dirty: this.pending !== null || this.inFlight !== null }
    this.opts.onChange?.(this.snap)
  }

  private clearTimers() {
    if (this.debounceTimer) clearTimeout(this.debounceTimer)
    if (this.retryTimer) clearTimeout(this.retryTimer)
    this.debounceTimer = this.retryTimer = null
  }

  /** Nuevo contenido del simulador (evento `change` de `window.JGFPGA`). */
  change(content: ProjectContent): void {
    if (this.disposed) return
    this.pending = content
    if (this.snap.status === 'conflict') return this.set({})
    if (this.snap.status === 'offline' && this.retryTimer) return this.set({}) // sale en el reintento
    if (this.debounceTimer) clearTimeout(this.debounceTimer)
    this.debounceTimer = setTimeout(() => {
      this.debounceTimer = null
      void this.run()
    }, this.debounceMs)
    if (this.snap.status !== 'saving' && this.snap.status !== 'error')
      this.set({ status: 'pending' })
    else this.set({})
  }

  /** Guarda ya lo pendiente (p. ej. antes de "Guardar versión" o al salir de la ruta). */
  async flush(): Promise<void> {
    if (this.disposed) return
    if (this.debounceTimer) clearTimeout(this.debounceTimer)
    this.debounceTimer = null
    if (this.inFlight) await this.inFlight
    if (this.snap.status === 'conflict') return
    if (this.pending) {
      if (this.retryTimer) clearTimeout(this.retryTimer)
      this.retryTimer = null
      await this.run()
    }
  }

  /** Reintenta ya un guardado en espera (p. ej. evento `online`). */
  retryNow(): void {
    if (this.snap.status !== 'offline' || !this.retryTimer) return
    clearTimeout(this.retryTimer)
    this.retryTimer = null
    void this.run()
  }

  /** Best effort al salir de la página. Devuelve `true` si había algo que enviar y se envió. */
  flushOnExit(): boolean {
    if (this.disposed || !this.pending || this.snap.status === 'conflict' || !this.opts.keepalive)
      return false
    const ok = this.opts.keepalive(this.body(this.pending))
    if (ok) this.keepaliveRevision = this.base.revision
    return ok
  }

  /** Resuelve un conflicto quedándose con el contenido local: se guarda sobre la versión actual del servidor. */
  async overwrite(current?: SaveBase): Promise<void> {
    const c = this.snap.conflict
    const next =
      current ??
      (c?.current_version !== undefined && c.current_revision !== undefined
        ? { version: c.current_version, revision: c.current_revision }
        : null)
    if (!next) throw new Error('Autosaver.overwrite: falta la versión actual del servidor')
    this.base = { ...next }
    this.set({ status: this.pending ? 'pending' : 'saved', conflict: null, error: null })
    await this.flush()
  }

  /** Cambia la base sin tocar lo pendiente (p. ej. tras "Guardar versión", que crea una versión actual nueva). */
  rebase(base: SaveBase): void {
    this.base = { ...base }
  }

  /** Descarta lo pendiente y parte de una base nueva (recargar la versión del servidor, restaurar…). */
  reset(base: SaveBase): void {
    this.clearTimers()
    this.pending = null
    this.attempt = 0
    this.keepaliveRevision = null
    this.base = { ...base }
    this.set({ status: 'saved', conflict: null, error: null, lastSavedAt: this.now() })
  }

  dispose(): void {
    this.disposed = true
    this.clearTimers()
  }

  private body(content: ProjectContent): AutosaveRequest {
    return { content, base_version: this.base.version, base_revision: this.base.revision }
  }

  private run(): Promise<void> {
    if (this.inFlight) return this.inFlight
    if (!this.pending || this.disposed) return Promise.resolve()
    const content = this.pending
    this.pending = null
    this.inFlight = this.send(content).finally(() => {
      this.inFlight = null
      this.set({})
    })
    this.set({ status: 'saving' })
    return this.inFlight
  }

  private async send(content: ProjectContent): Promise<void> {
    try {
      const res = await this.opts.save(this.body(content))
      if (this.disposed) return
      this.base = { version: res.version_id, revision: res.revision }
      this.attempt = 0
      this.keepaliveRevision = null
      if (this.pending) {
        this.set({ status: 'pending', lastSavedAt: this.now(), error: null })
        this.debounceTimer = setTimeout(() => {
          this.debounceTimer = null
          void this.run()
        }, this.debounceMs)
      } else {
        this.set({ status: 'saved', lastSavedAt: this.now(), error: null })
      }
    } catch (e) {
      if (this.disposed) return
      // Lo que no se guardó vuelve a estar pendiente (salvo que ya haya algo más nuevo).
      this.pending = this.pending ?? content
      if (isApiError(e) && e.status === 409 && e.code === 'version_conflict') {
        const details = (e.details ?? {}) as VersionConflictDetails
        if (
          this.keepaliveRevision !== null &&
          details.current_version !== undefined &&
          details.current_revision === this.keepaliveRevision + 1
        ) {
          // El 409 lo causó nuestro propio envío con keepalive: seguimos sobre esa revisión.
          this.keepaliveRevision = null
          this.base = { version: details.current_version, revision: details.current_revision }
          this.inFlight = null
          await this.run()
          return
        }
        this.clearTimers()
        this.set({ status: 'conflict', conflict: details, error: e })
        return
      }
      const transient = !isApiError(e) || e.status === 0 || e.status >= 500 || e.status === 429
      if (transient) {
        const delays = this.opts.retryDelaysMs ?? AUTOSAVE_DEFAULTS.retryDelaysMs
        const fallback = delays[Math.min(this.attempt, delays.length - 1)] ?? 5000
        const wait = isApiError(e) && e.retryAfter !== undefined ? e.retryAfter * 1000 : fallback
        this.attempt++
        if (this.debounceTimer) clearTimeout(this.debounceTimer)
        this.debounceTimer = null
        this.retryTimer = setTimeout(() => {
          this.retryTimer = null
          void this.run()
        }, wait)
        this.set({ status: 'offline', error: e })
        return
      }
      this.set({ status: 'error', error: e })
    }
  }
}
