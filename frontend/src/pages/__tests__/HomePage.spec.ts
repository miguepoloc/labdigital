import { http, HttpResponse } from 'msw'
import { describe, expect, it } from 'vitest'
import { config } from '@/config'
import { signIn } from '@/mocks/db'
import { DOCENTE_EMAIL, IDS } from '@/mocks/db.courses'
import { projectsState } from '@/mocks/handlers.projects'
import { server } from '@/mocks/node'
import { renderAt } from '@/test/utils'

const serverError = () =>
  HttpResponse.json({ error: { code: 'internal', message: 'boom' } }, { status: 500 })

describe('HomePage (/app)', () => {
  it('estudiante: proyectos recientes, cursos (con pendiente) y próximas entregas', async () => {
    const me = signIn()
    const mine = projectsState()
      .projects.filter((p) => p.ownerId === me.userId && !p.deleted_at)
      .sort((a, b) => b.updated_at.localeCompare(a.updated_at))
    const { wrapper } = await renderAt('/app')
    expect(wrapper.text()).not.toContain('Pronto')

    const projects = wrapper.findAll('[data-test="home-project"]')
    expect(projects).toHaveLength(Math.min(4, mine.length))
    expect(projects[0]!.text()).toContain(mine[0]!.name)
    expect(projects[0]!.find('a').attributes('href')).toBe(
      `/labdigital/app/proyectos/${mine[0]!.id}`,
    )
    expect(projects[0]!.find('[data-test="home-project-open"]').attributes('href')).toBe(
      `/labdigital/app/fpga/${mine[0]!.id}`,
    )
    expect(wrapper.find('[data-test="home-projects"]').text()).toContain('Nuevo proyecto')

    const courses = wrapper.findAll('[data-test="home-course"]')
    expect(courses).toHaveLength(2)
    expect(courses[0]!.text()).toContain('Diseño de Sistemas Digitales 2027-1')
    expect(courses[0]!.text()).toContain('Estudiante')
    expect(courses[0]!.text()).toContain('2027-1')
    expect(courses[0]!.find('a').attributes('href')).toBe(`/labdigital/app/cursos/${IDS.course}`)
    expect(courses[1]!.text()).toContain('Circuitos Digitales 2027-1')
    expect(courses[1]!.find('[data-test="home-pending"]').text()).toBe('Solicitud pendiente')
    expect(courses[0]!.find('[data-test="home-pending"]').exists()).toBe(false)
    // Microprocesamiento: no es miembro ⇒ no aparece
    expect(wrapper.text()).not.toContain('Microprocesamiento')

    const upcoming = wrapper.findAll('[data-test="home-upcoming-item"]')
    expect(upcoming.map((u) => u.text()).join('\n')).toContain('Lab 2 — Contador BCD')
    expect(wrapper.find('[data-test="home-upcoming"]').text()).not.toContain('Transmisor UART')
    // vencido y estricto: no aparece
    expect(wrapper.find('[data-test="home-upcoming"]').text()).not.toContain('Lab 3')
    wrapper.unmount()
  })

  it('docente: proyectos vacíos con CTA y contadores del curso', async () => {
    signIn(DOCENTE_EMAIL)
    const { wrapper } = await renderAt('/app')
    const empty = wrapper.find('[data-test="home-projects-empty"]')
    expect(empty.text()).toContain('Aún no tienes proyectos.')
    expect(empty.find('a').attributes('href')).toBe('/labdigital/app/proyectos')

    const course = wrapper.find('[data-test="home-course"]')
    expect(course.text()).toContain('Docente')
    expect(course.text()).toContain('3 estudiantes')
    expect(course.find('[data-test="home-requests"]').text()).toBe('1 solicitud por revisar')
    expect(course.text()).toContain('4 laboratorios')

    const upcoming = wrapper.findAll('[data-test="home-upcoming-item"]')
    expect(upcoming).toHaveLength(1)
    expect(upcoming[0]!.text()).toContain('Lab 2')
    expect(upcoming[0]!.text()).toContain('Vence el')
    wrapper.unmount()
  })

  it('sin cursos: estado vacío con CTA para unirse', async () => {
    signIn('admin@unimagdalena.edu.co')
    const { wrapper } = await renderAt('/app')
    const empty = wrapper.find('[data-test="home-courses-empty"]')
    expect(empty.text()).toContain('Aún no estás en ningún curso.')
    expect(empty.text()).toContain('Unirme con código')
    expect(empty.find('a').attributes('href')).toBe('/labdigital/app/cursos')
    expect(wrapper.find('[data-test="home-upcoming"]').exists()).toBe(false)
    wrapper.unmount()
  })

  it('si falla la carga de cursos, los proyectos se siguen mostrando', async () => {
    signIn()
    server.use(http.get(`${config.apiBase}/courses`, serverError))
    const { wrapper } = await renderAt('/app')
    expect(wrapper.find('[data-test="home-courses-error"]').exists()).toBe(true)
    expect(wrapper.find('[data-test="home-courses"]').text()).toContain('Reintentar')
    expect(wrapper.findAll('[data-test="home-project"]').length).toBeGreaterThan(0)
    wrapper.unmount()
  })

  it('si fallan los proyectos, los cursos se siguen mostrando', async () => {
    signIn()
    server.use(http.get(`${config.apiBase}/projects`, serverError))
    const { wrapper } = await renderAt('/app')
    expect(wrapper.find('[data-test="home-projects-error"]').exists()).toBe(true)
    expect(wrapper.findAll('[data-test="home-course"]')).toHaveLength(2)
    wrapper.unmount()
  })
})
