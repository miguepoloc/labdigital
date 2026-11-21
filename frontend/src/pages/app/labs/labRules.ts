/** Reglas de cliente de labs: estado de la fecha, escala de nota y validación de notas. */
import type { GradeScale, Lab, SubmissionStatus } from '@/api/courses'
import { t } from '@/i18n'

export type DeadlineState =
  /** Aún no abre (`opens_at` en el futuro). */
  | 'not_open'
  /** Se puede entregar a tiempo. */
  | 'open'
  /** Pasó la fecha, pero la política admite entregas marcadas como tardías. */
  | 'late'
  /** Pasó la fecha y la política es estricta: no se admiten entregas. */
  | 'closed'

export function deadlineState(
  lab: Pick<Lab, 'opens_at' | 'due_at' | 'deadline_policy'>,
  now: number = Date.now(),
): DeadlineState {
  if (lab.opens_at && Date.parse(lab.opens_at) > now) return 'not_open'
  if (lab.deadline_policy === 'none' || !lab.due_at) return 'open'
  if (Date.parse(lab.due_at) >= now) return 'open'
  return lab.deadline_policy === 'strict' ? 'closed' : 'late'
}

/** Escala por defecto del editor: 0,0 a 5,0 con un decimal y 3,0 para aprobar (costumbre colombiana). */
export function defaultScale(): GradeScale {
  return { type: 'numeric', min: 0, max: 5, decimals: 1, pass_mark: 3 }
}

const num = new Intl.NumberFormat('es-CO', { maximumFractionDigits: 2 })

export function formatNumber(n: number, decimals?: number): string {
  return decimals === undefined
    ? num.format(n)
    : new Intl.NumberFormat('es-CO', {
        minimumFractionDigits: decimals,
        maximumFractionDigits: decimals,
      }).format(n)
}

/** Texto de una nota según la escala («4,5 / 5,0», «Aprobado»). */
export function formatGrade(grade: number | null | undefined, scale: GradeScale): string {
  if (grade === null || grade === undefined) return '—'
  if (scale.type === 'pass_fail') return grade >= 1 ? t('grading.pass') : t('grading.fail')
  const d = scale.decimals ?? 0
  return `${formatNumber(grade, d)} / ${formatNumber(scale.max ?? 0, d)}`
}

/** Descripción corta de la escala («De 0,0 a 5,0 (1 decimal); aprueba con 3,0»). */
export function describeScale(scale: GradeScale): string {
  if (scale.type === 'pass_fail') return t('grading.passFailDesc')
  const d = scale.decimals ?? 0
  const base = t('grading.numericDesc', {
    min: formatNumber(scale.min ?? 0, d),
    max: formatNumber(scale.max ?? 0, d),
    decimals: d,
  })
  return scale.pass_mark !== undefined && scale.pass_mark !== null
    ? `${base} ${t('grading.passMarkDesc', { mark: formatNumber(scale.pass_mark, d) })}`
    : base
}

/** Errores del editor de escala (clave = campo de `grade_scale`). */
export function validateScale(scale: GradeScale): Record<string, string> {
  const errors: Record<string, string> = {}
  if (scale.type === 'pass_fail') return errors
  const { min, max, decimals, pass_mark } = scale
  if (min === undefined || !Number.isFinite(min)) errors.min = t('grading.errMin')
  if (max === undefined || !Number.isFinite(max)) errors.max = t('grading.errMax')
  else if (min !== undefined && Number.isFinite(min) && max <= min)
    errors.max = t('grading.errMaxGtMin')
  if (decimals === undefined || !Number.isInteger(decimals) || decimals < 0 || decimals > 2)
    errors.decimals = t('grading.errDecimals')
  if (pass_mark !== undefined && pass_mark !== null) {
    if (!Number.isFinite(pass_mark)) errors.pass_mark = t('grading.errPassMark')
    else if (min !== undefined && max !== undefined && (pass_mark < min || pass_mark > max))
      errors.pass_mark = t('grading.errPassMarkRange')
  }
  return errors
}

/** Convierte «4,5» o «4.5» en número; null si no es un número. */
export function parseDecimal(raw: string): number | null {
  const s = raw.trim().replace(',', '.')
  if (!/^-?\d+(\.\d+)?$/.test(s)) return null
  return Number(s)
}

export type GradeCheck = { ok: true; value: number | null } | { ok: false; error: string }

/**
 * Valida la nota escrita por el docente contra la escala del lab. Vacía = sin nota (sólo comentario o
 * devolución). En `pass_fail` el valor es `"1"` (aprobado) o `"0"` (no aprobado).
 */
export function validateGrade(raw: string, scale: GradeScale): GradeCheck {
  if (!raw.trim()) return { ok: true, value: null }
  if (scale.type === 'pass_fail') {
    if (raw === '1' || raw === '0') return { ok: true, value: Number(raw) }
    return { ok: false, error: t('grading.errPassFail') }
  }
  const value = parseDecimal(raw)
  const d = scale.decimals ?? 0
  const min = scale.min ?? 0
  const max = scale.max ?? 0
  if (value === null) return { ok: false, error: t('grading.errNotNumber') }
  if (value < min || value > max) {
    return {
      ok: false,
      error: t('grading.errRange', { min: formatNumber(min, d), max: formatNumber(max, d) }),
    }
  }
  const decimalsUsed = (raw.trim().replace(',', '.').split('.')[1] ?? '').length
  if (decimalsUsed > d) return { ok: false, error: t('grading.errDecimalsUsed', { decimals: d }) }
  return { ok: true, value }
}

/** Estado visible de una entrega (incluye la marca de tardía). */
export type SubmissionBadge = 'submitted' | 'late' | 'graded' | 'returned'

export function submissionBadge(s: {
  status: SubmissionStatus
  is_late: boolean
}): SubmissionBadge {
  if (s.status === 'graded') return 'graded'
  if (s.status === 'returned') return 'returned'
  return s.is_late ? 'late' : 'submitted'
}
