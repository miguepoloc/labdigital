import type { VueWrapper } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import { signIn } from '@/mocks/db'
import { cdb, DOCENTE_EMAIL, IDS, uid } from '@/mocks/db.courses'
import { renderAt, settle } from '@/test/utils'

const SOFIA = uid('sofia.rodriguez@unimagdalena.edu.co')
const LUIS = uid('luis.perez@unimagdalena.edu.co')
const PAIRS_LAB = '0190c1c1-0000-7000-8000-0000000000aa'

const team = (name: string) => cdb.teams.find((tm) => tm.name === name)

/** Abre la pestaña «Equipos» de un lab como docente. */
async function openTeams(labId: string = IDS.lab2) {
  signIn(DOCENTE_EMAIL)
  const { wrapper } = await renderAt(`/app/labs/${labId}`)
  await wrapper.find('[data-test="tab-teams"]').trigger('click')
  await settle()
  return wrapper
}

/** «Proyecto final» en parejas, sin equipos (el caso de «Digitales 2»). */
function addPairsLab() {
  const base = cdb.labs.find((l) => l.id === IDS.lab2)!
  cdb.labs.push({ ...base, id: PAIRS_LAB, title: 'Proyecto final', max_team_size: 2 })
}

function teamItem(wrapper: VueWrapper, name: string) {
  return wrapper
    .findAll('[data-test="team-item"]')
    .find((li) => li.find('[data-test="team-name"]').text() === name)!
}

function status(wrapper: VueWrapper) {
  return wrapper.find('[data-test="teams-status"]').text()
}

describe('Equipos del docente (LD-18)', () => {
  it('muestra los equipos y la columna «Sin equipo»', async () => {
    team('Compuertas')!.member_ids = []
    const wrapper = await openTeams()
    expect(wrapper.findAll('[data-test="team-item"]')).toHaveLength(2)
    expect(teamItem(wrapper, 'Los Flip-Flops').text()).toContain('FF1234')
    const free = wrapper.findAll('[data-test="unassigned-student"]')
    expect(free).toHaveLength(1)
    expect(free[0]!.text()).toContain('Sofía Rodríguez')
    wrapper.unmount()
  })

  it('crea un equipo con nombre e integrantes', async () => {
    team('Compuertas')!.member_ids = []
    const wrapper = await openTeams()
    await wrapper.find('[data-test="team-new"]').trigger('click')
    await wrapper.find('input[name="team_name"]').setValue('Pareja 1')
    const sofia = wrapper
      .findAll('[data-test="team-form"] input[type="checkbox"]')
      .find((c) => c.element.parentElement?.textContent?.includes('Sofía'))!
    await sofia.setValue(true)
    await wrapper.find('[data-test="team-form-save"]').trigger('click')
    await settle()
    expect(team('Pareja 1')!.member_ids).toEqual([SOFIA])
    expect(status(wrapper)).toContain('Equipo «Pareja 1» creado')
    expect(wrapper.find('[data-test="team-form"]').exists()).toBe(false)
    expect(wrapper.findAll('[data-test="unassigned-student"]')).toHaveLength(0)
    wrapper.unmount()
  })

  it('nombre repetido ⇒ el error se muestra en el diálogo', async () => {
    const wrapper = await openTeams()
    await wrapper.find('[data-test="team-new"]').trigger('click')
    await wrapper.find('[data-test="team-form-save"]').trigger('click')
    expect(wrapper.find('[data-test="team-form"]').text()).toContain('Este campo es obligatorio')
    await wrapper.find('input[name="team_name"]').setValue('compuertas')
    await wrapper.find('[data-test="team-form-save"]').trigger('click')
    await settle()
    expect(wrapper.find('[data-test="team-form-error"]').text()).toContain(
      'Ya hay un equipo con ese nombre',
    )
    expect(cdb.teams.filter((tm) => tm.lab_id === IDS.lab2)).toHaveLength(2)
    wrapper.unmount()
  })

  it('crea 12 parejas de una vez y no repite nombres', async () => {
    addPairsLab()
    const wrapper = await openTeams(PAIRS_LAB)
    expect(wrapper.find('[data-test="teams-list"]').text()).toContain('Aún no hay equipos')
    await wrapper.find('[data-test="team-bulk"]').trigger('click')
    const prefix = wrapper.find<HTMLInputElement>('input[name="bulk_prefix"]')
    expect(prefix.element.value).toBe('Pareja')
    await wrapper.find('input[name="bulk_count"]').setValue('0')
    await wrapper.find('[data-test="bulk-save"]').trigger('click')
    expect(wrapper.find('[data-test="bulk-form"]').text()).toContain('entre 1 y 60')
    await wrapper.find('input[name="bulk_count"]').setValue('12')
    await wrapper.find('[data-test="bulk-save"]').trigger('click')
    await settle()
    const names = cdb.teams.filter((tm) => tm.lab_id === PAIRS_LAB).map((tm) => tm.name)
    expect(names).toEqual(Array.from({ length: 12 }, (_, i) => `Pareja ${i + 1}`))
    expect(status(wrapper)).toContain('Se crearon 12 equipos')
    expect(wrapper.findAll('[data-test="team-item"]')).toHaveLength(12)

    await wrapper.find('[data-test="team-bulk"]').trigger('click')
    await wrapper.find('input[name="bulk_count"]').setValue('12')
    await wrapper.find('[data-test="bulk-save"]').trigger('click')
    await settle()
    expect(status(wrapper)).toContain('ya existían todos esos nombres')
    wrapper.unmount()
  })

  it('mueve a un estudiante a otro equipo con «Mover a…»', async () => {
    const wrapper = await openTeams()
    const luis = teamItem(wrapper, 'Los Flip-Flops')
      .findAll('[data-test="team-member"]')
      .find((li) => li.text().includes('Luis'))!
    const select = luis.find('[data-test="move-select"]')
    expect(select.attributes('aria-label')).toBe('Mover a Luis Fernando Pérez a otro equipo')
    expect(luis.find('[data-test="move-submit"]').attributes('disabled')).toBeDefined()
    await select.setValue(IDS.teamCMP)
    await luis.find('[data-test="move-submit"]').trigger('click')
    await settle()
    expect(team('Compuertas')!.member_ids).toEqual([SOFIA, LUIS])
    expect(team('Los Flip-Flops')!.member_ids).not.toContain(LUIS)
    expect(status(wrapper)).toContain('Luis Fernando Pérez ahora está en «Compuertas»')
    wrapper.unmount()
  })

  it('un equipo completo aparece deshabilitado en «Mover a…»', async () => {
    addPairsLab()
    cdb.teams.push(
      {
        ...team('Los Flip-Flops')!,
        id: 'tm-a',
        lab_id: PAIRS_LAB,
        name: 'Pareja 1',
        member_ids: [LUIS, uid('estudiante@unimagdalena.edu.co')],
      },
      {
        ...team('Compuertas')!,
        id: 'tm-b',
        lab_id: PAIRS_LAB,
        name: 'Pareja 2',
        member_ids: [SOFIA],
      },
    )
    const wrapper = await openTeams(PAIRS_LAB)
    const sofia = teamItem(wrapper, 'Pareja 2').find('[data-test="team-member"]')
    const option = sofia.find('option[value="tm-a"]')
    expect(option.text()).toBe('Pareja 1 (completo)')
    expect(option.attributes('disabled')).toBeDefined()
    wrapper.unmount()
  })

  it('quita a un estudiante de su equipo y queda «Sin equipo»', async () => {
    const wrapper = await openTeams()
    await teamItem(wrapper, 'Compuertas').find('[data-test="member-remove"]').trigger('click')
    await settle()
    expect(team('Compuertas')!.member_ids).toEqual([])
    expect(wrapper.find('[data-test="unassigned"]').text()).toContain('Sofía Rodríguez')
    // Asignarla de vuelta desde «Sin equipo».
    const row = wrapper.find('[data-test="unassigned-student"]')
    await row.find('[data-test="move-select"]').setValue(IDS.teamCMP)
    await row.find('[data-test="move-submit"]').trigger('click')
    await settle()
    expect(team('Compuertas')!.member_ids).toEqual([SOFIA])
    wrapper.unmount()
  })

  it('renombra un equipo', async () => {
    const wrapper = await openTeams()
    await teamItem(wrapper, 'Compuertas').find('[data-test="team-rename"]').trigger('click')
    const input = wrapper.find<HTMLInputElement>('input[name="team_name"]')
    expect(input.element.value).toBe('Compuertas')
    await input.setValue('Pareja 7')
    await wrapper.find('[data-test="team-form-save"]').trigger('click')
    await settle()
    expect(team('Pareja 7')?.id).toBe(IDS.teamCMP)
    expect(status(wrapper)).toContain('ahora se llama «Pareja 7»')
    wrapper.unmount()
  })

  it('elimina un equipo tras confirmar', async () => {
    const wrapper = await openTeams()
    await teamItem(wrapper, 'Compuertas').find('[data-test="team-delete"]').trigger('click')
    expect(wrapper.text()).toContain('Eliminar «Compuertas»')
    expect(team('Compuertas')).toBeDefined() // nada hasta confirmar
    await wrapper.find('[data-test="confirm-ok"]').trigger('click')
    await settle()
    expect(team('Compuertas')).toBeUndefined()
    expect(status(wrapper)).toContain('Equipo «Compuertas» eliminado')
    expect(wrapper.find('[data-test="unassigned"]').text()).toContain('Sofía Rodríguez')
    wrapper.unmount()
  })

  it('no elimina un equipo con entregas y lo explica', async () => {
    cdb.submissions[0]!.team_id = IDS.teamFF
    const wrapper = await openTeams()
    await teamItem(wrapper, 'Los Flip-Flops').find('[data-test="team-delete"]').trigger('click')
    await wrapper.find('[data-test="confirm-ok"]').trigger('click')
    await settle()
    expect(wrapper.find('[role="dialog"]').text()).toContain('ya tiene entregas')
    expect(team('Los Flip-Flops')).toBeDefined()
    wrapper.unmount()
  })

  it('fija y quita la fijación', async () => {
    const wrapper = await openTeams()
    const lockBtn = () => teamItem(wrapper, 'Compuertas').find('[data-test="team-lock"]')
    await lockBtn().trigger('click')
    await settle()
    expect(team('Compuertas')!.locked).toBe(true)
    expect(lockBtn().text()).toBe('Quitar fijación')
    await lockBtn().trigger('click')
    await settle()
    expect(team('Compuertas')!.locked).toBe(false)
    expect(status(wrapper)).toContain('ya no está fijado')
    wrapper.unmount()
  })

  it('reparte al azar a quienes no tienen equipo', async () => {
    team('Compuertas')!.member_ids = []
    team('Los Flip-Flops')!.member_ids = []
    const wrapper = await openTeams()
    expect(wrapper.findAll('[data-test="unassigned-student"]')).toHaveLength(3)
    await wrapper.find('[data-test="team-auto"]').trigger('click')
    await settle()
    const placed = cdb.teams.filter((tm) => tm.lab_id === IDS.lab2).flatMap((tm) => tm.member_ids)
    expect(placed).toHaveLength(3)
    expect(status(wrapper)).toContain('todos tienen equipo')
    expect(wrapper.find('[data-test="team-auto"]').attributes('disabled')).toBeDefined()
    wrapper.unmount()
  })

  it('un estudiante no ve el panel del docente', async () => {
    signIn()
    const { wrapper } = await renderAt(`/app/labs/${IDS.lab2}`)
    expect(wrapper.find('[data-test="teams-admin"]').exists()).toBe(false)
    expect(wrapper.find('[data-test="team-new"]').exists()).toBe(false)
    wrapper.unmount()
  })
})
