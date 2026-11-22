/**
 * Punto de extensión del botón "Entregar" del envoltorio FPGA.
 *
 * Mientras no haya cursos, el envoltorio muestra `FpgaSubmitPlaceholder.vue`. El flujo real de entregas
 * (LD-6 / F2b) registra su propio diálogo, p. ej. desde su archivo de rutas o su página de laboratorio:
 *
 *   import { registerFpgaSubmitDialog } from '@/pages/app/fpga/extensions'
 *   registerFpgaSubmitDialog(defineAsyncComponent(() => import('@/pages/app/labs/SubmitFromFpgaDialog.vue')))
 *
 * El componente recibe la prop `context: FpgaSubmitContext` y emite `close` (y opcionalmente
 * `submitted`, `{ submissionId }`).
 */
import { shallowRef, type Component } from 'vue'
import type { Project } from '@/api/projects'
import type { JgFpgaApi } from './jgfpga'

export interface FpgaSubmitContext {
  /** Proyecto abierto (id, nombre, versión actual). */
  project: Readonly<Project>
  /**
   * Guarda lo pendiente y devuelve la versión a congelar en `POST /labs/{id}/submissions {project_id, version_id}`.
   * Lanza si no se pudo guardar (sin conexión, conflicto…).
   */
  prepareVersion(): Promise<{ project_id: string; version_id: string }>
  /**
   * Informe y `.bit` del simulador. OJO (contrato §7): `getLastBitstream()` es el último `.bit` de ESTE navegador,
   * hay que mostrar nombre/fecha para que el estudiante confirme; `getReportDocx`/`getLastBitstream` lanzan ante
   * errores de red: capturarlos.
   */
  jgfpga: Pick<JgFpgaApi, 'getReport' | 'getReportDocx' | 'getLastBitstream'>
  /** Query de la ruta del envoltorio (p. ej. `?lab=<id>` si se llegó desde un laboratorio). */
  query: Readonly<Record<string, string>>
}

export const fpgaSubmitDialog = shallowRef<Component | null>(null)

/** Registra el diálogo de entrega real (sustituye al placeholder). */
export function registerFpgaSubmitDialog(component: Component | null): void {
  fpgaSubmitDialog.value = component
}
