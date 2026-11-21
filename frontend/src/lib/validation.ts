import { config } from '@/config'
import { t } from '@/i18n'

export type Validator = (value: string) => string | null

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/

export const required: Validator = (v) => (v.trim() ? null : t('validation.required'))

export const email: Validator = (v) =>
  !v.trim() ? t('validation.required') : EMAIL_RE.test(v.trim()) ? null : t('validation.email')

export const password: Validator = (v) =>
  !v
    ? t('validation.required')
    : v.length >= config.passwordMinLength
      ? null
      : t('validation.passwordMin', { min: config.passwordMinLength })

export const fullName: Validator = (v) =>
  !v.trim() ? t('validation.required') : v.trim().length >= 3 ? null : t('validation.fullNameMin')

export function matches(other: () => string): Validator {
  return (v) =>
    !v ? t('validation.required') : v === other() ? null : t('validation.passwordMatch')
}

/** Puntuación 0–4 (sin dependencias): longitud + variedad de caracteres. */
export function passwordStrength(v: string): 0 | 1 | 2 | 3 | 4 {
  if (!v) return 0
  let score = 0
  if (v.length >= config.passwordMinLength) score++
  if (v.length >= 14) score++
  const classes = [/[a-z]/, /[A-Z]/, /\d/, /[^A-Za-z0-9]/].filter((re) => re.test(v)).length
  if (classes >= 2) score++
  if (classes >= 3) score++
  if (v.length < config.passwordMinLength) score = Math.min(score, 1)
  if (/^(.)\1+$/.test(v)) score = 0
  return score as 0 | 1 | 2 | 3 | 4
}
