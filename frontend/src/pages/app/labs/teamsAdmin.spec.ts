import { describe, expect, it } from 'vitest'
import { ApiError } from '@/api/errors'
import type { Team } from '@/api/courses'
import { moveOptions, suggestedTeamCount, teamsErrorMessage } from './teamsAdmin'

const team = (id: string, members: number): Team => ({
  id,
  lab_id: 'lab',
  name: `Pareja ${id}`,
  join_code: 'ABC123',
  locked: false,
  members: Array.from({ length: members }, (_, i) => ({ id: `${id}-${i}`, full_name: `E${i}` })),
})

const apiError = (code: string) => new ApiError({ status: 409, code, message: 'x' })

describe('teamsAdmin', () => {
  it('sugiere los equipos que faltan para quienes no tienen equipo', () => {
    expect(suggestedTeamCount(24, 2)).toBe(12)
    expect(suggestedTeamCount(5, 2)).toBe(3)
    expect(suggestedTeamCount(0, 2)).toBe(1)
    expect(suggestedTeamCount(500, 2)).toBe(60)
    expect(suggestedTeamCount(4, null)).toBe(1)
  })

  it('las opciones de «Mover a…» excluyen el propio equipo y deshabilitan los completos', () => {
    const options = moveOptions([team('1', 2), team('2', 1), team('3', 0)], 2, '3')
    expect(options.map((o) => o.id)).toEqual(['1', '2'])
    expect(options[0]).toEqual({ id: '1', label: 'Pareja 1 (completo)', disabled: true })
    expect(options[1]!.disabled).toBe(false)
  })

  it('los errores se dicen al docente y si no, los generales', () => {
    expect(teamsErrorMessage(apiError('already_in_team'))).toContain('Usa «Mover a…»')
    expect(teamsErrorMessage(apiError('team_has_submissions'))).toContain('ya tiene entregas')
    expect(teamsErrorMessage(apiError('team_name_taken'))).toContain('Ya hay un equipo')
  })
})
