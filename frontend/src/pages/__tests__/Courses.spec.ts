import { describe, expect, it } from 'vitest'
import { signIn } from '@/mocks/db'
import { cdb, DOCENTE_EMAIL, IDS, uid } from '@/mocks/db.courses'
import { renderAt, settle } from '@/test/utils'

describe('Cursos (estudiante)', () => {
  it('lista mis cursos con la solicitud pendiente', async () => {
    signIn()
    const { wrapper } = await renderAt('/app/cursos')
    const student = wrapper.find('[data-test="courses-student"]')
    expect(student.text()).toContain('Diseño de Sistemas Digitales 2027-1')
    expect(student.text()).toContain('Circuitos Digitales 2027-1')
    expect(student.text()).toContain('Solicitud pendiente')
    expect(wrapper.find('[data-test="courses-teacher"]').text()).toContain('No has creado cursos')
    wrapper.unmount()
  })

  it('se une con código ⇒ solicitud pendiente', async () => {
    signIn()
    const { wrapper } = await renderAt('/app/cursos')
    await wrapper.find('input[name="join_code"]').setValue('micro1')
    await wrapper.find('[data-test="join-form"]').trigger('submit')
    await settle()
    expect(wrapper.find('[data-test="join-status"]').text()).toContain(
      'tu solicitud para «Microprocesamiento I 2027-1» quedó enviada',
    )
    const m = cdb.memberships.find(
      (x) => x.course_id === IDS.courseMicro && x.user_id === uid('estudiante@unimagdalena.edu.co'),
    )
    expect(m?.status).toBe('pending')
    wrapper.unmount()
  })

  it('código inválido ⇒ mensaje claro', async () => {
    signIn()
    const { wrapper } = await renderAt('/app/cursos')
    await wrapper.find('input[name="join_code"]').setValue('NOEXISTE')
    await wrapper.find('[data-test="join-form"]').trigger('submit')
    await settle()
    expect(wrapper.text()).toContain('El código no es válido')
    wrapper.unmount()
  })

  it('con solicitud pendiente ve el aviso y no los labs', async () => {
    signIn()
    const { wrapper } = await renderAt(`/app/cursos/${IDS.courseCircuitos}`)
    expect(wrapper.find('[data-test="membership-notice"]').text()).toContain(
      'pendiente de aprobación',
    )
    expect(wrapper.find('[data-test="lab-item"]').exists()).toBe(false)
    wrapper.unmount()
  })
})

describe('Permisos: vista docente vs estudiante', () => {
  it('el estudiante ve sólo labs publicados y no las pestañas del docente', async () => {
    signIn()
    const { wrapper } = await renderAt(`/app/cursos/${IDS.course}`)
    expect(wrapper.find('[data-test="student-view"]').exists()).toBe(true)
    expect(wrapper.find('[data-test="teacher-view"]').exists()).toBe(false)
    expect(wrapper.find('[data-test="tab-requests"]').exists()).toBe(false)
    expect(wrapper.find('[data-test="new-lab"]').exists()).toBe(false)
    const labs = wrapper.findAll('[data-test="lab-item"]')
    expect(labs).toHaveLength(3) // el borrador (Lab 4) no aparece
    expect(wrapper.text()).not.toContain('Transmisor UART')
    // estado de mi entrega por lab
    expect(labs[0]!.text()).toContain('Tardía')
    expect(labs[2]!.text()).toContain('Sin entregar')
    wrapper.unmount()
  })

  it('el docente ve pestañas, borradores, código y exportación de notas', async () => {
    signIn(DOCENTE_EMAIL)
    const { wrapper } = await renderAt(`/app/cursos/${IDS.course}`)
    expect(wrapper.find('[data-test="teacher-view"]').exists()).toBe(true)
    expect(wrapper.findAll('[data-test="lab-item"]')).toHaveLength(4)
    expect(wrapper.text()).toContain('Borrador')
    expect(wrapper.find('[data-test="export-grades"]').attributes('href')).toContain(
      `/labdigital/api/v1/courses/${IDS.course}/grades.csv`,
    )
    expect(wrapper.find('[data-test="tab-requests"]').text()).toContain('1')
    await wrapper.find('[data-test="tab-settings"]').trigger('click')
    expect(wrapper.find('[data-test="join-code"]').text()).toBe('DSD27A')
    wrapper.unmount()
  })

  it('un estudiante no puede abrir la entrega de otro', async () => {
    signIn()
    const { wrapper } = await renderAt(`/app/entregas/${IDS.subLuis1}`)
    expect(wrapper.find('[data-test="submission-error"]').text()).toContain('No tienes permiso')
    expect(wrapper.find('[data-test="review-form"]').exists()).toBe(false)
    wrapper.unmount()
  })

  it('un estudiante no puede abrir un borrador ni el editor de labs', async () => {
    signIn()
    let r = await renderAt(`/app/labs/${IDS.lab4}`)
    expect(r.wrapper.find('[data-test="lab-error"]').text()).toContain('No encontramos')
    r.wrapper.unmount()
    r = await renderAt(`/app/cursos/${IDS.course}/labs/nuevo`)
    expect(r.wrapper.find('[data-test="editor-error"]').text()).toContain('No tienes permiso')
    expect(r.wrapper.find('[data-test="lab-form"]').exists()).toBe(false)
    r.wrapper.unmount()
  })

  it('el estudiante ve su propia entrega sin formulario de revisión', async () => {
    signIn()
    const { wrapper } = await renderAt(`/app/entregas/${IDS.subAna1}`)
    expect(wrapper.find('h1').text()).toBe('Entrega')
    expect(wrapper.find('[data-test="review-form"]').exists()).toBe(false)
    expect(wrapper.text()).toContain('Falta el testbench')
    wrapper.unmount()
  })
})

describe('Docente: solicitudes y miembros', () => {
  it('aprueba una solicitud pendiente', async () => {
    signIn(DOCENTE_EMAIL)
    const { wrapper } = await renderAt(`/app/cursos/${IDS.course}`)
    await wrapper.find('[data-test="tab-requests"]').trigger('click')
    await settle()
    const items = wrapper.findAll('[data-test="request-item"]')
    expect(items).toHaveLength(1)
    expect(items[0]!.text()).toContain('Juan Camilo Rojas')
    await items[0]!.find('[data-test="approve"]').trigger('click')
    await settle()
    expect(wrapper.find('[data-test="members-status"]').text()).toContain(
      'Juan Camilo Rojas ya es estudiante del curso',
    )
    expect(wrapper.findAll('[data-test="request-item"]')).toHaveLength(0)
    const m = cdb.memberships.find((x) => x.user_id === uid('juan.rojas@unimagdalena.edu.co'))
    expect(m?.status).toBe('active')
    wrapper.unmount()
  })

  it('rota el código del curso', async () => {
    signIn(DOCENTE_EMAIL)
    const { wrapper } = await renderAt(`/app/cursos/${IDS.course}`)
    await wrapper.find('[data-test="tab-settings"]').trigger('click')
    await wrapper.find('[data-test="rotate-code"]').trigger('click')
    await wrapper.find('[data-test="confirm-ok"]').trigger('click')
    await settle()
    const code = cdb.courses.find((c) => c.id === IDS.course)!.join_code
    expect(code).not.toBe('DSD27A')
    expect(wrapper.find('[data-test="join-code"]').text()).toBe(code)
    wrapper.unmount()
  })

  it('cualquier usuario crea un curso y queda como docente', async () => {
    signIn()
    const { wrapper, router } = await renderAt('/app/cursos')
    await wrapper.find('[data-test="create-course"]').trigger('click')
    await wrapper.find('input[name="name"]').setValue('Electrónica Digital Avanzada')
    await wrapper.find('input[name="period"]').setValue('2027-1')
    await wrapper.find('[data-test="course-form"]').trigger('submit')
    await settle()
    const created = cdb.courses.find((c) => c.name === 'Electrónica Digital Avanzada')!
    expect(created.owner_id).toBe(uid('estudiante@unimagdalena.edu.co'))
    expect(router.currentRoute.value.params.id).toBe(created.id)
    expect(wrapper.find('[data-test="join-code"]').text()).toBe(created.join_code)
    wrapper.unmount()
  })
})

describe('Docente: crear lab con escala', () => {
  it('crea y publica un lab con escala 0–100 en equipo', async () => {
    signIn(DOCENTE_EMAIL)
    const { wrapper, router } = await renderAt(`/app/cursos/${IDS.course}/labs/nuevo`)
    await wrapper.find('input[name="title"]').setValue('Lab 5 — ALU de 4 bits')
    await wrapper.find('textarea[name="statement_md"]').setValue('# ALU\n\nDiseñe una **ALU**.')
    await wrapper.find('input[name="due_at"]').setValue('2027-03-05T23:59')
    await wrapper.find('input[name="deadline_policy"][value="strict"]').setValue(true)
    await wrapper.find('input[name="team_mode"][value="team"]').setValue(true)
    await wrapper.find('input[name="max_team_size"]').setValue('2')
    await wrapper.find('input[name="scale_max"]').setValue('100')
    await wrapper.find('input[name="scale_decimals"]').setValue('0')
    await wrapper.find('input[name="scale_pass_mark"]').setValue('60')
    expect(wrapper.find('[data-test="scale-preview"]').text()).toContain('De 0 a 100')
    await wrapper.find('[data-test="save-publish"]').trigger('click')
    await settle()
    const lab = cdb.labs.find((l) => l.title === 'Lab 5 — ALU de 4 bits')!
    expect(lab).toBeTruthy()
    expect(lab.grade_scale).toEqual({
      type: 'numeric',
      min: 0,
      max: 100,
      decimals: 0,
      pass_mark: 60,
    })
    expect(lab.deadline_policy).toBe('strict')
    expect(lab.team_mode).toBe('team')
    expect(lab.max_team_size).toBe(2)
    expect(lab.due_at).toBe('2027-03-06T04:59:00.000Z') // 23:59 en Bogotá
    expect(lab.published_at).not.toBeNull()
    expect(router.currentRoute.value.name).toBe('lab')
    expect(wrapper.find('[data-test="lab-status"]').text()).toContain('guardado')
    wrapper.unmount()
  })

  it('escala inválida o fecha faltante ⇒ no guarda', async () => {
    signIn(DOCENTE_EMAIL)
    const before = cdb.labs.length
    const { wrapper } = await renderAt(`/app/cursos/${IDS.course}/labs/nuevo`)
    await wrapper.find('input[name="title"]').setValue('Lab mal')
    await wrapper.find('input[name="scale_min"]').setValue('5')
    await wrapper.find('input[name="scale_max"]').setValue('5')
    await wrapper.find('[data-test="lab-form"]').trigger('submit')
    await settle()
    expect(wrapper.text()).toContain('El máximo debe ser mayor que el mínimo.')
    expect(wrapper.text()).toContain('Indica la fecha límite')
    expect(cdb.labs.length).toBe(before)
    wrapper.unmount()
  })

  it('escala aprobado / no aprobado sin fecha', async () => {
    signIn(DOCENTE_EMAIL)
    const { wrapper } = await renderAt(`/app/cursos/${IDS.course}/labs/nuevo`)
    await wrapper.find('input[name="title"]').setValue('Lab libre')
    await wrapper.find('input[name="deadline_policy"][value="none"]').setValue(true)
    await wrapper.find('[data-test="scale-pass-fail"]').setValue(true)
    await wrapper.find('[data-test="lab-form"]').trigger('submit')
    await settle()
    const lab = cdb.labs.find((l) => l.title === 'Lab libre')!
    expect(lab.grade_scale).toEqual({ type: 'pass_fail' })
    expect(lab.published_at).toBeNull()
    wrapper.unmount()
  })
})
