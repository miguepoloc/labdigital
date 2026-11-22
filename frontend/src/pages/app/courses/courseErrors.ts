import { isApiError } from '@/api/errors'
import { hasKey, t } from '@/i18n'
import { errorMessage, fieldErrors } from '@/lib/errors'

/**
 * Mensaje para errores de cursos/labs/entregas: primero los textos propios (`courseErrors.<code>`, en
 * trato de tú), luego los generales. Un `validation_error` con un solo campo muestra ese mensaje.
 */
export function courseErrorMessage(e: unknown): string {
  if (isApiError(e)) {
    if (e.code === 'validation_error') {
      const fields = Object.values(fieldErrors(e))
      if (fields.length === 1) return fields[0]!
    }
    const key = `courseErrors.${e.code}`
    if (hasKey(key)) return t(key)
  }
  return errorMessage(e)
}

export { fieldErrors }
