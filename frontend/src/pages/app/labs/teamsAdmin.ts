/** Reglas y textos del panel de equipos del docente (LD-18), fuera del SFC para poder probarlos. */
import { isApiError } from '@/api/errors'
import type { Team } from '@/api/courses'
import { hasKey, t } from '@/i18n'
import { courseErrorMessage } from '../courses/courseErrors'

/** Igual que el backend (`MAX_BULK_TEAMS`). */
export const MAX_BULK_TEAMS = 60

export interface MoveOption {
  id: string
  label: string
  disabled: boolean
}

/** Errores dichos al docente (`teams.adminErrors.<code>`) y, si no, los generales de cursos. */
export function teamsErrorMessage(e: unknown): string {
  if (isApiError(e)) {
    const key = `teams.adminErrors.${e.code}`
    if (hasKey(key)) return t(key)
  }
  return courseErrorMessage(e)
}

export function isFull(team: Team, maxSize: number | null): boolean {
  return maxSize !== null && team.members.length >= maxSize
}

/** Equipos a los que se puede mover/asignar (menos `exceptId`); los completos van deshabilitados. */
export function moveOptions(
  teams: Team[],
  maxSize: number | null,
  exceptId?: string,
): MoveOption[] {
  return teams
    .filter((tm) => tm.id !== exceptId)
    .map((tm) => {
      const full = isFull(tm, maxSize)
      return {
        id: tm.id,
        label: full ? t('teams.fullOption', { name: tm.name }) : tm.name,
        disabled: full,
      }
    })
}

/** Cuántos equipos sugerir al crear varios: los que hacen falta para quienes aún no tienen equipo. */
export function suggestedTeamCount(unassigned: number, maxSize: number | null): number {
  if (!maxSize || unassigned <= 0) return 1
  return Math.min(Math.ceil(unassigned / maxSize), MAX_BULK_TEAMS)
}
