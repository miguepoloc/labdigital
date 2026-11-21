import { describe, expect, it } from 'vitest'
import { ApiError } from '@/api/errors'
import { t } from '@/i18n'
import { errorMessage, fieldErrors } from './errors'
import { describeUserAgent } from './format'
import { pageTitle } from './head'
import { passwordStrength } from './validation'

describe('errorMessage', () => {
  it('mapea cada código fijo del contrato a un texto propio', () => {
    for (const code of [
      'invalid_credentials',
      'email_not_verified',
      'account_inactive',
      'rate_limited',
      'csrf_rejected',
      'token_invalid',
      'version_conflict',
      'deadline_passed',
      'forbidden',
      'not_found',
      'validation_error',
      'payload_too_large',
    ]) {
      const msg = errorMessage(new ApiError({ status: 400, code, message: 'srv' }))
      expect(msg).not.toBe('srv')
      expect(msg).not.toBe(t('errors.unknown'))
    }
  })

  it('rate_limited con Retry-After incluye la espera', () => {
    expect(
      errorMessage(
        new ApiError({ status: 429, code: 'rate_limited', message: '', retryAfter: 12 }),
      ),
    ).toContain('12 s')
  })

  it('código desconocido ⇒ mensaje del servidor; nada útil ⇒ genérico', () => {
    expect(
      errorMessage(new ApiError({ status: 400, code: 'otra_cosa', message: 'Texto del servidor' })),
    ).toBe('Texto del servidor')
    expect(errorMessage(new Error('x'))).toBe(t('errors.unknown'))
  })

  it('fieldErrors lee details.fields de validation_error', () => {
    const e = new ApiError({
      status: 422,
      code: 'validation_error',
      message: '',
      details: { fields: { email: 'mal' } },
    })
    expect(fieldErrors(e)).toEqual({ email: 'mal' })
  })
})

describe('utilidades', () => {
  it('passwordStrength', () => {
    expect(passwordStrength('')).toBe(0)
    expect(passwordStrength('abc')).toBeLessThanOrEqual(1)
    expect(passwordStrength('aaaaaaaaaaaa')).toBe(0)
    expect(passwordStrength('Muy-Segura-2026!')).toBe(4)
  })

  it('describeUserAgent', () => {
    expect(describeUserAgent('Mozilla/5.0 (Windows NT 10.0) Chrome/131.0 Safari/537.36')).toBe(
      'Chrome en Windows',
    )
    expect(describeUserAgent(null)).toBeNull()
  })

  it('pageTitle', () => {
    expect(pageTitle('forgot.title')).toBe('Recuperar contraseña · LabDigital')
    expect(pageTitle(undefined)).toBe('LabDigital GIDEAM')
  })
})
