import { describe, expect, it } from 'vitest'
import { signIn } from '@/mocks/db'
import { findMockProject, projectsState } from '@/mocks/handlers.projects'
import { renderAt, settle } from '@/test/utils'

function ana() {
  signIn()
  return projectsState()
}

describe('ProjectsListPage (/app/proyectos)', () => {
  it('lista los proyectos con módulo y última edición (más reciente primero)', async () => {
    ana()
    const { wrapper } = await renderAt('/app/proyectos')
    const items = wrapper.findAll('[data-test="project-item"]')
    expect(items).toHaveLength(2)
    expect(items[0]!.text()).toContain('Semáforo')
    expect(items[0]!.text()).toContain('FPGA')
    expect(items[0]!.text()).toContain('Última edición:')
    expect(items[1]!.text()).toContain('Contador BCD')
    expect(items[0]!.find('[data-test="open"]').attributes('href')).toMatch(
      /^\/labdigital\/app\/fpga\/0190p-/,
    )
    wrapper.unmount()
  })

  it('crea un proyecto con contenido inicial válido', async () => {
    const st = ana()
    const { wrapper } = await renderAt('/app/proyectos')
    await wrapper.find('input[name="name"]').setValue('  Sumador de 4 bits ')
    await wrapper.find('[data-test="create-form"]').trigger('submit')
    await settle()
    expect(wrapper.find('[data-test="status"]').text()).toContain('«Sumador de 4 bits» creado')
    expect(wrapper.findAll('[data-test="project-item"]')[0]!.text()).toContain('Sumador de 4 bits')
    const created = st.projects.at(-1)!
    expect(created.name).toBe('Sumador de 4 bits')
    expect(created.versions[0]!.content).toMatchObject({
      format: 'basys3-sim-project',
      version: 1,
      files: [{ name: 'top.vhd', role: 'design' }],
    })
    wrapper.unmount()
  })

  it('no crea sin nombre', async () => {
    const st = ana()
    const { wrapper } = await renderAt('/app/proyectos')
    await wrapper.find('[data-test="create-form"]').trigger('submit')
    await settle()
    expect(wrapper.text()).toContain('Este campo es obligatorio.')
    expect(st.projects).toHaveLength(2)
    wrapper.unmount()
  })

  it('renombra en la propia fila', async () => {
    const st = ana()
    const { wrapper } = await renderAt('/app/proyectos')
    const first = () => wrapper.findAll('[data-test="project-item"]')[0]!
    await first().find('[data-test="rename"]').trigger('click')
    await first().find('input[name="rename"]').setValue('Semáforo peatonal')
    await first().find('[data-test="rename-form"]').trigger('submit')
    await settle()
    expect(first().text()).toContain('Semáforo peatonal')
    expect(first().find('[data-test="rename-form"]').exists()).toBe(false)
    expect(st.projects.find((p) => p.name === 'Semáforo peatonal')).toBeTruthy()
    wrapper.unmount()
  })

  it('borra sólo tras confirmar en la página', async () => {
    const st = ana()
    const { wrapper } = await renderAt('/app/proyectos')
    const target = st.projects.find((p) => p.name === 'Semáforo')!
    const row = () => wrapper.findAll('[data-test="project-item"]')[0]!
    await row().find('[data-test="remove"]').trigger('click')
    expect(row().find('[data-test="confirm-remove"]').text()).toContain('¿Borrar «Semáforo»?')
    expect(target.deleted_at).toBeNull()
    await row().find('[data-test="confirm-remove-yes"]').trigger('click')
    await settle()
    expect(target.deleted_at).not.toBeNull()
    expect(wrapper.findAll('[data-test="project-item"]')).toHaveLength(1)
    expect(wrapper.find('[data-test="status"]').text()).toContain('«Semáforo» borrado')
    wrapper.unmount()
  })

  it('sin proyectos muestra el estado vacío', async () => {
    const st = ana()
    st.projects.forEach((p) => (p.deleted_at = '2026-11-10T00:00:00Z'))
    const { wrapper } = await renderAt('/app/proyectos')
    expect(wrapper.text()).toContain('Aún no tienes proyectos')
    wrapper.unmount()
  })
})

describe('ProjectDetailPage (/app/proyectos/:id)', () => {
  it('muestra el historial: autosave vs manual, fecha, tamaño y la actual', async () => {
    const st = ana()
    const bcd = st.projects.find((p) => p.name === 'Contador BCD')!
    const { wrapper } = await renderAt(`/app/proyectos/${bcd.id}`)
    expect(wrapper.find('[data-test="project-name"]').text()).toBe('Contador BCD')
    const rows = wrapper.findAll('[data-test="version-row"]')
    expect(rows).toHaveLength(3)
    expect(rows[0]!.text()).toContain('v3')
    expect(rows[0]!.text()).toContain('Autoguardado')
    expect(rows[0]!.find('[data-test="current"]').exists()).toBe(true)
    expect(rows[0]!.find('[data-test="restore"]').exists()).toBe(false)
    expect(rows[1]!.text()).toContain('Manual')
    expect(rows[1]!.text()).toContain('Antes de la síntesis')
    expect(rows[1]!.text()).toMatch(/\d+(,\d)? (B|KB)/)
    const view = rows[1]!.find('[data-test="view"]').attributes('href')!
    expect(view).toContain(`/labdigital/app/fpga/${bcd.id}?`)
    expect(view).toContain(`ver=${bcd.versions[1]!.id}`)
    expect(view).toContain('readonly=1')
    wrapper.unmount()
  })

  it('restaura una versión (con confirmación) y la nueva queda como actual', async () => {
    const st = ana()
    const bcd = st.projects.find((p) => p.name === 'Contador BCD')!
    const { wrapper } = await renderAt(`/app/proyectos/${bcd.id}`)
    const v1 = () => wrapper.findAll('[data-test="version-row"]').at(-1)!
    await v1().find('[data-test="restore"]').trigger('click')
    expect(wrapper.find('[data-test="confirm-restore"]').text()).toContain(
      '¿Restaurar la versión 1?',
    )
    await wrapper.find('[data-test="confirm-restore-yes"]').trigger('click')
    await settle()
    const p = findMockProject(bcd.id)!
    expect(p.versions).toHaveLength(4)
    expect(p.currentId).toBe(p.versions[3]!.id)
    expect(p.versions[3]!.content).toEqual(p.versions[0]!.content)
    expect(wrapper.find('[data-test="status"]').text()).toContain(
      'Versión 1 restaurada como versión 4.',
    )
    const rows = wrapper.findAll('[data-test="version-row"]')
    expect(rows).toHaveLength(4)
    expect(rows[0]!.text()).toContain('Restaurada de la versión 1')
    expect(rows[0]!.find('[data-test="current"]').exists()).toBe(true)
    wrapper.unmount()
  })

  it('"Guardar versión" crea una versión manual', async () => {
    const st = ana()
    const sem = st.projects.find((p) => p.name === 'Semáforo')!
    const { wrapper } = await renderAt(`/app/proyectos/${sem.id}`)
    await wrapper.find('[data-test="save-version"]').trigger('click')
    await settle()
    expect(sem.versions).toHaveLength(2)
    expect(sem.versions[1]!.kind).toBe('manual')
    expect(wrapper.find('[data-test="status"]').text()).toContain('Versión 2 guardada.')
    expect(wrapper.findAll('[data-test="version-row"]')).toHaveLength(2)
    wrapper.unmount()
  })

  it('proyecto inexistente ⇒ aviso', async () => {
    ana()
    const { wrapper } = await renderAt('/app/proyectos/no-existe')
    expect(wrapper.find('[data-test="not-found"]').exists()).toBe(true)
    wrapper.unmount()
  })
})
