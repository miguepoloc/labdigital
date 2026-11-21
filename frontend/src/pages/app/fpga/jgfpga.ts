/**
 * Puente con la API de integración de JG FPGA (`window.JGFPGA`, contrato §7 y `docs/EMBED.md` del módulo).
 * El iframe es del MISMO origen: se accede directamente a `contentWindow.JGFPGA`.
 */
import { config } from '@/config'
import type { FpgaContent, ProjectContent } from '@/api/projects'

export interface JgFpgaBitstream {
  name: string
  blob: Blob
}

export interface JgFpgaApi {
  version: string
  getProject(): FpgaContent
  /** Lanza si `format`/`version`/`files` no son válidos; devuelve los archivos omitidos. No emite `change`. */
  loadProject(content: ProjectContent, opts?: { readOnly?: boolean }): string[] | void
  readOnly?(): boolean
  getReport(): Record<string, unknown> | null
  getReportDocx(): Promise<Blob | null>
  /** El `.bit` más reciente DE ESTE NAVEGADOR (no necesariamente del proyecto). Lanza ante errores HTTP. */
  getLastBitstream(): Promise<JgFpgaBitstream | null>
  on(event: 'change', fn: (content: FpgaContent) => void): void
  on(event: 'ready', fn: () => void): void
  off(event: 'change' | 'ready', fn: (...args: never[]) => void): void
}

/** URL del módulo en el iframe. En desarrollo `VITE_FPGA_URL` permite usar el stub (`dev-fpga-stub.html`). */
export function fpgaFrameUrl(): string {
  if (import.meta.env.DEV && import.meta.env.VITE_FPGA_URL) return import.meta.env.VITE_FPGA_URL
  return `${config.basePath}fpga/`
}

function apiOf(frame: HTMLIFrameElement): JgFpgaApi | null {
  try {
    const w = frame.contentWindow as (Window & { JGFPGA?: JgFpgaApi }) | null
    const api = w?.JGFPGA
    return api && typeof api.loadProject === 'function' ? api : null
  } catch {
    return null // otro origen: no se toca
  }
}

/**
 * Llama a `onReady(api)` cada vez que el módulo del iframe queda listo (una vez por carga del iframe), sea por
 * `postMessage({type: "jgfpga:ready"})` (sólo si `event.origin === location.origin` y viene de ESE iframe) o por
 * el evento `ready` de `window.JGFPGA` (que también se entrega a quien se suscribe tarde).
 * Devuelve la función para dejar de escuchar.
 */
export function watchFrameReady(
  frame: HTMLIFrameElement,
  onReady: (api: JgFpgaApi) => void,
): () => void {
  const seen = new WeakSet<object>()
  const subscribed = new WeakSet<object>()

  const fire = (api: JgFpgaApi | null) => {
    if (!api || seen.has(api)) return
    seen.add(api)
    onReady(api)
  }

  const onMessage = (e: MessageEvent) => {
    if (e.origin !== window.location.origin) return
    if (!frame.contentWindow || e.source !== frame.contentWindow) return
    const data = e.data as { type?: unknown } | null
    if (!data || typeof data !== 'object' || data.type !== 'jgfpga:ready') return
    fire(apiOf(frame))
  }

  const subscribe = () => {
    const api = apiOf(frame)
    if (!api || subscribed.has(api)) return
    subscribed.add(api)
    const handler = () => {
      api.off('ready', handler)
      fire(api)
    }
    api.on('ready', handler)
  }

  window.addEventListener('message', onMessage)
  frame.addEventListener('load', subscribe)
  subscribe() // por si ya cargó

  return () => {
    window.removeEventListener('message', onMessage)
    frame.removeEventListener('load', subscribe)
  }
}
