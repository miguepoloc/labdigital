import { describe, expect, it } from 'vitest'
import { fromBogotaInput, toBogotaInput } from '@/lib/bogota'
import { MB, validateFile, validateTotal } from '../submissions/uploadRules'
import { deadlineState, formatGrade, validateGrade, validateScale } from './labRules'

const NOW = Date.parse('2027-02-10T12:00:00Z')
const past = '2027-02-05T04:59:00Z'
const future = '2027-03-01T04:59:00Z'

describe('deadlineState', () => {
  it('strict / late_marked / none', () => {
    expect(deadlineState({ opens_at: null, due_at: future, deadline_policy: 'strict' }, NOW)).toBe(
      'open',
    )
    expect(deadlineState({ opens_at: null, due_at: past, deadline_policy: 'strict' }, NOW)).toBe(
      'closed',
    )
    expect(
      deadlineState({ opens_at: null, due_at: past, deadline_policy: 'late_marked' }, NOW),
    ).toBe('late')
    expect(deadlineState({ opens_at: null, due_at: past, deadline_policy: 'none' }, NOW)).toBe(
      'open',
    )
    expect(deadlineState({ opens_at: future, due_at: null, deadline_policy: 'none' }, NOW)).toBe(
      'not_open',
    )
  })
})

describe('validateGrade', () => {
  const scale = { type: 'numeric' as const, min: 0, max: 5, decimals: 1, pass_mark: 3 }

  it('acepta coma o punto y respeta rango y decimales', () => {
    expect(validateGrade('4,5', scale)).toEqual({ ok: true, value: 4.5 })
    expect(validateGrade('3.0', scale)).toEqual({ ok: true, value: 3 })
    expect(validateGrade('', scale)).toEqual({ ok: true, value: null })
    expect(validateGrade('5,5', scale)).toMatchObject({ ok: false })
    expect(validateGrade('-1', scale)).toMatchObject({ ok: false })
    expect(validateGrade('4,55', scale)).toMatchObject({ ok: false })
    expect(validateGrade('cuatro', scale)).toMatchObject({ ok: false })
  })

  it('aprobado / no aprobado', () => {
    const pf = { type: 'pass_fail' as const }
    expect(validateGrade('1', pf)).toEqual({ ok: true, value: 1 })
    expect(validateGrade('0', pf)).toEqual({ ok: true, value: 0 })
    expect(validateGrade('4', pf)).toMatchObject({ ok: false })
    expect(formatGrade(1, pf)).toBe('Aprobado')
    expect(formatGrade(0, pf)).toBe('No aprobado')
  })

  it('formatea con la escala', () => {
    expect(formatGrade(4.5, scale)).toBe('4,5 / 5,0')
    expect(formatGrade(null, scale)).toBe('—')
  })
})

describe('validateScale', () => {
  it('detecta máximo ≤ mínimo, decimales y nota de aprobación fuera de rango', () => {
    expect(validateScale({ type: 'numeric', min: 0, max: 5, decimals: 1, pass_mark: 3 })).toEqual(
      {},
    )
    expect(validateScale({ type: 'numeric', min: 5, max: 5, decimals: 1 })).toHaveProperty('max')
    expect(validateScale({ type: 'numeric', min: 0, max: 5, decimals: 3 })).toHaveProperty(
      'decimals',
    )
    expect(
      validateScale({ type: 'numeric', min: 0, max: 5, decimals: 1, pass_mark: 7 }),
    ).toHaveProperty('pass_mark')
    expect(validateScale({ type: 'pass_fail' })).toEqual({})
  })
})

describe('uploadRules', () => {
  it('valida tipo por clase y tamaño por archivo y por entrega', () => {
    expect(validateFile({ name: 'informe.pdf', size: MB }, 'report')).toBeNull()
    expect(validateFile({ name: 'informe.DOCX', size: MB }, 'report')).toBeNull()
    expect(validateFile({ name: 'top.bit', size: MB }, 'report')).toContain(
      'no es de un tipo permitido',
    )
    expect(validateFile({ name: 'top.bit', size: MB }, 'bitstream')).toBeNull()
    expect(validateFile({ name: 'video.mp4', size: 26 * MB }, 'attachment')).toContain('25 MB')
    expect(validateFile({ name: 'script.exe', size: 10 }, 'attachment')).toContain('tipo permitido')
    expect(
      validateTotal([{ size: 25 * MB }, { size: 25 * MB }, { size: 25 * MB }, { size: 25 * MB }]),
    ).toBeNull()
    expect(
      validateTotal([{ size: 25 * MB }, { size: 25 * MB }, { size: 25 * MB }, { size: 26 * MB }]),
    ).toContain('100 MB')
  })
})

describe('fechas en America/Bogota', () => {
  it('ida y vuelta de datetime-local en hora de Colombia (UTC−5)', () => {
    expect(fromBogotaInput('2027-02-05T23:59')).toBe('2027-02-06T04:59:00.000Z')
    expect(toBogotaInput('2027-02-06T04:59:00.000Z')).toBe('2027-02-05T23:59')
    expect(fromBogotaInput('')).toBeNull()
  })
})
