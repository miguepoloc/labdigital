/**
 * API imperativa del diálogo de entrega, para el envoltorio FPGA (LD-8a) u otros módulos:
 *
 * ```ts
 * import { openSubmitDialog } from '@/pages/app/submissions/submitDialog'
 * const submission = await openSubmitDialog({
 *   projectId, versionId,          // versión a congelar (sin versionId: la actual)
 *   labId,                         // opcional: sin él, el estudiante elige entre sus labs abiertos
 *   prefill: { bitstream, report } // opcional: File del .bit / informe obtenidos de window.JGFPGA
 * })
 * if (submission) { … }            // null si se cerró sin entregar
 * ```
 *
 * Monta el diálogo en un contenedor propio bajo `document.body` (no necesita router ni Pinia) y lo
 * desmonta al cerrarse. La promesa se resuelve al cerrar: con la entrega creada o con `null`.
 */
import { createApp, h } from 'vue'
import type { Lab } from '@/api/courses'
import type { Submission } from '@/api/submissions'
import SubmitDialog from './SubmitDialog.vue'

export interface SubmitDialogProps {
  labId?: string
  /** Lab ya cargado (evita otra petición). */
  lab?: Lab | null
  projectId?: string
  /** Versión a congelar; sin ella se entrega la versión actual del proyecto. */
  versionId?: string
  /** Archivos ya disponibles (p. ej. el `.bit` y el informe `.docx` de `window.JGFPGA`). */
  prefill?: {
    report?: File | null
    bitstream?: File | null
    /** El `.bit` viene de `getLastBitstream()` (último de este navegador): se pide confirmarlo. */
    bitstreamFromBrowser?: boolean
    attachments?: File[]
  }
}

/**
 * Forma estructural de `FpgaSubmitContext` (LD-9, `src/pages/app/fpga/extensions.ts`) que usa
 * `FpgaSubmitDialog.vue`. Se registra en el envoltorio con:
 * `registerFpgaSubmitDialog(defineAsyncComponent(() => import('@/pages/app/submissions/FpgaSubmitDialog.vue')))`
 */
export interface FpgaSubmitContextLike {
  project: Readonly<{ id: string; name: string }>
  prepareVersion(): Promise<{ project_id: string; version_id: string }>
  jgfpga: {
    getReportDocx(): Promise<Blob | null>
    getLastBitstream(): Promise<{ name: string; blob: Blob } | null>
  }
  query: Readonly<Record<string, string>>
}

export interface OpenSubmitDialogOptions extends SubmitDialogProps {
  /** Se llama en cuanto la entrega queda creada (antes de que el usuario cierre el diálogo). */
  onSubmitted?: (submission: Submission) => void
  /** Contenedor donde montar el diálogo (por defecto `document.body`). */
  container?: HTMLElement
}

export function openSubmitDialog(opts: OpenSubmitDialogOptions): Promise<Submission | null> {
  const { onSubmitted, container = document.body, ...props } = opts
  return new Promise((resolve) => {
    const host = document.createElement('div')
    host.className = 'ld-submit-dialog-host'
    container.appendChild(host)
    let result: Submission | null = null
    const app = createApp({
      render: () =>
        h(SubmitDialog, {
          ...props,
          onSubmitted: (s: Submission) => {
            result = s
            onSubmitted?.(s)
          },
          onClose: () => {
            app.unmount()
            host.remove()
            resolve(result)
          },
        }),
    })
    app.mount(host)
  })
}
