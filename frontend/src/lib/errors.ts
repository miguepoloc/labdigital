import { isApiError } from '@/api/errors'
import { hasKey, t } from '@/i18n'

/** Mensaje amable para cualquier error (códigos del contrato §6 → textos de `es.errors`). */
export function errorMessage(e: unknown): string {
  if (isApiError(e)) {
    if (e.code === 'rate_limited' && e.retryAfter !== undefined && e.retryAfter > 0) {
      return t('errors.rate_limited_wait', { seconds: e.retryAfter })
    }
    const key = `errors.${e.code}`
    if (hasKey(key)) return t(key)
    // Código no conocido: el servidor ya manda el texto en español.
    if (e.message && !e.message.startsWith('HTTP ')) return e.message
  }
  return t('errors.unknown')
}

/**
 * Errores por campo de un `validation_error`. Se acepta `details.fields = {campo: mensaje}`.
 * PROPUESTA AL CONTRATO: fijar esa forma de `details` para 422.
 */
export function fieldErrors(e: unknown): Record<string, string> {
  if (!isApiError(e) || e.code !== 'validation_error') return {}
  const fields = e.details?.fields
  if (!fields || typeof fields !== 'object') return {}
  const out: Record<string, string> = {}
  for (const [k, v] of Object.entries(fields as Record<string, unknown>)) {
    if (typeof v === 'string') out[k] = v
  }
  return out
}
