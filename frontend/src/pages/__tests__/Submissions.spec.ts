import { mount, type DOMWrapper } from '@vue/test-utils'
import { http, HttpResponse } from 'msw'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { config } from '@/config'
import { signIn } from '@/mocks/db'
import { cdb, DOCENTE_EMAIL, IDS, uid } from '@/mocks/db.courses'
import { server } from '@/mocks/node'
import FpgaSubmitDialog from '@/pages/app/submissions/FpgaSubmitDialog.vue'
import { openSubmitDialog } from '@/pages/app/submissions/submitDialog'
import { MB } from '@/pages/app/submissions/uploadRules'
import { FakeXhr } from '@/test/fakeXhr'
import { renderAt, settle } from '@/test/utils'

beforeEach(() => {
  FakeXhr.progressEvents = []
  vi.stubGlobal('XMLHttpRequest', FakeXhr)
})
afterEach(() => {
  vi.unstubAllGlobals()
  document.querySelectorAll('.ld-submit-dialog-host').forEach((el) => el.remove())
})

const SOFIA = 'sofia.rodriguez@unimagdalena.edu.co'

function fakeFile(name: string, size?: number, type = 'application/pdf'): File {
  const f = new File(['contenido'], name, { type })
  if (size !== undefined) Object.defineProperty(f, 'size', { value: size })
  return f
}

/** Espera (con un tope) a que se cumpla una condición: las subidas encadenan varias peticiones. */
async function waitFor(check: () => boolean, tries = 50) {
  for (let i = 0; i < tries && !check(); i++) await settle(1)
}

async function chooseFile(input: DOMWrapper<Element>, file: File) {
  Object.defineProperty(input.element, 'files', { value: [file], configurable: true })
  await input.trigger('change')
}

describe('Lab del estudiante', () => {
  it('muestra enunciado renderizado, fechas en hora de Colombia y enlace al simulador', async () => {
    signIn()
    const { wrapper } = await renderAt(`/app/labs/${IDS.lab1}`)
    expect(wrapper.find('[data-test="statement"] h2').text()).toBe('Objetivo')
    expect(wrapper.find('[data-test="lab-due"]').text()).toContain('Hora de Colombia')
    expect(wrapper.find('[data-test="lab-due"]').text()).toMatch(/\d{4}/)
    expect(wrapper.find('[data-test="open-simulator"]').attributes('href')).toBe(
      '/labdigital/app/fpga/',
    )
    // Historial con revisión y devolución
    const attempts = wrapper.findAll('[data-test="attempt"]')
    expect(attempts).toHaveLength(2)
    expect(attempts[1]!.text()).toContain('Devuelta para corrección')
    // Ya entregó y la última no fue devuelta: no puede re-entregar
    expect(wrapper.find('[data-test="open-submit"]').attributes('disabled')).toBeDefined()
    expect(wrapper.find('[data-test="block-reason"]').text()).toContain(
      'no se permiten re-entregas',
    )
    wrapper.unmount()
  })

  it('strict y fecha pasada ⇒ explica el cierre y deshabilita «Entregar»', async () => {
    signIn()
    const { wrapper } = await renderAt(`/app/labs/${IDS.lab3}`)
    expect(wrapper.find('[data-test="lab-closed"]').text()).toContain('cierre estricto')
    expect(wrapper.find('[data-test="open-submit"]').attributes('disabled')).toBeDefined()
    wrapper.unmount()
  })

  it('entrega a tiempo en equipo con informe ⇒ «Entregado …»', async () => {
    signIn()
    const { wrapper } = await renderAt(`/app/labs/${IDS.lab2}`)
    expect(wrapper.find('[data-test="my-team"]').text()).toContain('Los Flip-Flops')
    expect(wrapper.find('[data-test="my-team"]').text()).toContain('FF1234')
    await wrapper.find('[data-test="open-submit"]').trigger('click')
    await settle()
    await wrapper.find('select[name="project"]').setValue(IDS.projContador)
    await settle()
    const versions = wrapper.findAll('select[name="version"] option')
    expect(versions.length).toBe(3) // actual + v2 + v1
    await chooseFile(wrapper.find('[data-test="file-report"]'), fakeFile('informe.pdf'))
    await chooseFile(
      wrapper.find('[data-test="file-bitstream"]'),
      fakeFile('top.bit', undefined, 'application/octet-stream'),
    )
    await wrapper.find('[data-test="submit-form"]').trigger('submit')
    await waitFor(() => wrapper.find('[data-test="submit-result"]').exists())
    const result = wrapper.find('[data-test="submit-result"]')
    expect(result.text()).toContain('Entregado el')
    expect(result.text()).not.toContain('(tardía)')
    const created = cdb.submissions.find((s) => s.lab_id === IDS.lab2)!
    expect(created.team_id).toBe(IDS.teamFF)
    expect(created.is_late).toBe(false)
    expect(created.file_ids).toHaveLength(2)
    expect(cdb.files.find((f) => f.id === created.file_ids[0])?.kind).toBe('report')
    expect(FakeXhr.progressEvents.length).toBeGreaterThanOrEqual(4) // progreso de los 2 archivos
    wrapper.unmount()
  })

  it('late_marked con fecha pasada ⇒ aviso y «Entregado … (tardía)»', async () => {
    signIn(SOFIA)
    cdb.projects.push({
      id: 'p-sofia',
      owner_id: uid(SOFIA),
      name: 'Sumador de Sofía',
      module: 'fpga',
      updated_at: new Date().toISOString(),
      versions: [
        {
          id: 'v-sofia',
          n: 1,
          label: null,
          kind: 'manual',
          size: 100,
          created_at: new Date().toISOString(),
        },
      ],
    })
    const { wrapper } = await renderAt(`/app/labs/${IDS.lab1}`)
    await wrapper.find('[data-test="open-submit"]').trigger('click')
    await settle()
    expect(wrapper.find('[data-test="submit-late"]').text()).toContain('marcada como tardía')
    // un único proyecto ⇒ preseleccionado
    expect((wrapper.find('select[name="project"]').element as HTMLSelectElement).value).toBe(
      'p-sofia',
    )
    await wrapper.find('[data-test="submit-form"]').trigger('submit')
    await settle(8)
    expect(wrapper.find('[data-test="submit-result"]').text()).toMatch(
      /Entregado el .+ \(tardía\)\./,
    )
    expect(cdb.submissions.at(-1)!.is_late).toBe(true)
    // el historial se actualiza tras cerrar el diálogo
    await wrapper.find('[data-test="submit-close"]').trigger('click')
    await settle()
    expect(wrapper.findAll('[data-test="attempt"]')).toHaveLength(1)
    wrapper.unmount()
  })

  it('límite de tamaño y tipo en cliente: no sube nada y deshabilita confirmar', async () => {
    signIn()
    let uploads = 0
    server.use(
      http.post(`${config.apiBase}/files`, () => {
        uploads++
        return HttpResponse.json({ id: 'x', sha256: '', size: 0, mime: '' })
      }),
    )
    const { wrapper } = await renderAt(`/app/labs/${IDS.lab2}`)
    await wrapper.find('[data-test="open-submit"]').trigger('click')
    await settle()
    await chooseFile(wrapper.find('[data-test="file-report"]'), fakeFile('enorme.pdf', 26 * MB))
    expect(wrapper.find('[data-test="file-error"]').text()).toContain('supera el máximo de 25 MB')
    await chooseFile(wrapper.find('[data-test="file-bitstream"]'), fakeFile('informe.pdf'))
    expect(wrapper.findAll('[data-test="file-error"]')[1]!.text()).toContain('.bit')
    expect(wrapper.find('[data-test="submit-confirm"]').attributes('disabled')).toBeDefined()
    // 100 MB por entrega
    for (let i = 0; i < 4; i++) {
      await chooseFile(
        wrapper.find('[data-test="file-attachment"]'),
        fakeFile(`video${i}.mp4`, 24 * MB, 'video/mp4'),
      )
    }
    expect(wrapper.find('[data-test="total-error"]').text()).toContain('el máximo es 100 MB')
    await wrapper.find('[data-test="submit-form"]').trigger('submit')
    await settle()
    expect(uploads).toBe(0)
    wrapper.unmount()
  })

  it('payload_too_large del servidor ⇒ mensaje de tamaño', async () => {
    signIn()
    server.use(
      http.post(`${config.apiBase}/files`, () =>
        HttpResponse.json(
          { error: { code: 'payload_too_large', message: 'Demasiado grande.' } },
          { status: 413 },
        ),
      ),
    )
    const { wrapper } = await renderAt(`/app/labs/${IDS.lab2}`)
    await wrapper.find('[data-test="open-submit"]').trigger('click')
    await settle()
    await wrapper.find('select[name="project"]').setValue(IDS.projContador)
    await chooseFile(wrapper.find('[data-test="file-report"]'), fakeFile('informe.pdf'))
    await wrapper.find('[data-test="submit-form"]').trigger('submit')
    await settle(8)
    expect(wrapper.find('[data-test="submit-error"]').text()).toContain('25 MB por archivo')
    wrapper.unmount()
  })

  it('deadline_passed del servidor ⇒ explica el cierre y bloquea', async () => {
    signIn()
    server.use(
      http.post(`${config.apiBase}/labs/:id/submissions`, () =>
        HttpResponse.json(
          { error: { code: 'deadline_passed', message: 'Cerrado.' } },
          { status: 409 },
        ),
      ),
    )
    const { wrapper } = await renderAt(`/app/labs/${IDS.lab2}`)
    await wrapper.find('[data-test="open-submit"]').trigger('click')
    await settle()
    await wrapper.find('select[name="project"]').setValue(IDS.projContador)
    await wrapper.find('[data-test="submit-form"]').trigger('submit')
    await settle(8)
    expect(wrapper.find('[data-test="submit-error"]').text()).toContain('cierre estricto')
    expect(wrapper.find('[data-test="submit-closed"]').exists()).toBe(true)
    expect(wrapper.find('[data-test="submit-confirm"]').attributes('disabled')).toBeDefined()
    wrapper.unmount()
  })

  it('equipo: crear con nombre ⇒ código; salir', async () => {
    signIn(SOFIA)
    const { wrapper } = await renderAt(`/app/labs/${IDS.lab2}`)
    expect(wrapper.find('[data-test="my-team"]').text()).toContain('Compuertas')
    await wrapper.find('[data-test="team-leave"]').trigger('click')
    await wrapper.find('[data-test="confirm-ok"]').trigger('click')
    await settle()
    expect(wrapper.find('[data-test="team-status"]').text()).toContain('Saliste del equipo')
    expect(wrapper.find('[data-test="block-reason"]').text()).toContain('únete a un equipo')
    await wrapper.find('input[name="team_name"]').setValue('Biestables')
    await wrapper.find('[data-test="team-create"]').trigger('submit')
    await settle()
    const team = cdb.teams.find((tm) => tm.name === 'Biestables')!
    expect(wrapper.find('[data-test="team-status"]').text()).toContain(team.join_code)
    expect(wrapper.find('[data-test="my-team"]').text()).toContain('Biestables')
    wrapper.unmount()
  })
})

describe('openSubmitDialog (API para el envoltorio FPGA)', () => {
  it('monta el diálogo con proyecto/versión dados, entrega y resuelve con la entrega', async () => {
    signIn()
    const versionId = cdb.projects.find((p) => p.id === IDS.projContador)!.versions[0]!.id
    const bit = fakeFile('ultimo.bit', undefined, 'application/octet-stream')
    const promise = openSubmitDialog({
      labId: IDS.lab2,
      projectId: IDS.projContador,
      versionId,
      prefill: { bitstream: bit },
    })
    await settle(8)
    await waitFor(
      () =>
        (document.querySelector('select[name="version"]') as HTMLSelectElement | null)?.value ===
        versionId,
    )
    const form = document.querySelector<HTMLFormElement>('[data-test="submit-form"]')!
    expect(form).toBeTruthy()
    expect(document.body.textContent).toContain('ultimo.bit')
    expect((form.querySelector('select[name="version"]') as HTMLSelectElement).value).toBe(
      versionId,
    )
    form.dispatchEvent(new Event('submit', { cancelable: true }))
    await waitFor(() => !!document.querySelector('[data-test="submit-result"]'))
    expect(document.querySelector('[data-test="submit-result"]')?.textContent).toContain(
      'Entregado el',
    )
    ;(document.querySelector('[data-test="submit-close"]') as HTMLButtonElement).click()
    const submission = await promise
    expect(submission?.version_id).toBe(versionId)
    expect(submission?.files ?? []).toHaveLength(1)
    expect(document.querySelector('.ld-submit-dialog-host')).toBeNull()
  })

  it('sin labId deja elegir entre los labs abiertos; cerrar resuelve null', async () => {
    signIn()
    const promise = openSubmitDialog({ projectId: IDS.projContador })
    await settle(6)
    const options = Array.from(document.querySelectorAll('select[name="lab"] option')).map(
      (o) => o.textContent,
    )
    expect(options.join('|')).toContain('Lab 2 — Contador BCD')
    expect(options.join('|')).not.toContain('Lab 3') // strict cerrado
    ;(document.querySelector('.ld-dialog__close') as HTMLButtonElement).click()
    expect(await promise).toBeNull()
  })
})

describe('FpgaSubmitDialog (contexto de registerFpgaSubmitDialog, LD-9)', () => {
  it('usa prepareVersion, precarga el .docx, tolera fallos del .bit y emite submitted', async () => {
    signIn()
    const versionId = cdb.projects.find((p) => p.id === IDS.projContador)!.versions[1]!.id
    let prepared = 0
    const context = {
      project: { id: IDS.projContador, name: 'Contador BCD' },
      prepareVersion: async () => {
        prepared++
        return { project_id: IDS.projContador, version_id: versionId }
      },
      jgfpga: {
        getReport: () => null,
        getReportDocx: async () => new Blob(['docx'], { type: 'application/octet-stream' }),
        getLastBitstream: async () => {
          throw new Error('sin red')
        },
      },
      query: { lab: IDS.lab2 },
    }
    const w = mount(FpgaSubmitDialog, { props: { context }, attachTo: document.body })
    await waitFor(() => w.find('[data-test="submit-form"]').exists())
    expect(prepared).toBe(1)
    expect(w.text()).toContain('Lab 2 — Contador BCD')
    expect(w.text()).toContain('informe-Contador BCD.docx')
    await w.find('[data-test="submit-form"]').trigger('submit')
    await waitFor(() => w.emitted('submitted') !== undefined)
    const [payload] = w.emitted('submitted')![0] as [{ submissionId: string }]
    const created = cdb.submissions.find((x) => x.id === payload.submissionId)!
    expect(created.version_id).toBe(versionId)
    expect(created.file_ids).toHaveLength(1)
    w.unmount()
  })
})

describe('Revisión del docente', () => {
  it('valida la nota contra la escala y califica', async () => {
    signIn(DOCENTE_EMAIL)
    const { wrapper } = await renderAt(`/app/entregas/${IDS.subAna2}`)
    expect(wrapper.find('[data-test="open-readonly"]').attributes('href')).toBe(
      `/labdigital/app/fpga/?entrega=${IDS.subAna2}`,
    )
    expect(wrapper.find('[data-test="submission-files"]').text()).toContain('informe-lab1-v2.pdf')
    const grade = wrapper.find('input[name="grade"]')
    await grade.setValue('5,5')
    await wrapper.find('[data-test="review-form"]').trigger('submit')
    await settle()
    expect(wrapper.find('[data-test="grade-error"]').text()).toContain('entre 0,0 y 5,0')
    await grade.setValue('4,55')
    await wrapper.find('[data-test="review-form"]').trigger('submit')
    await settle()
    expect(wrapper.find('[data-test="grade-error"]').text()).toContain('1 decimal(es)')
    await grade.setValue('4,2')
    await wrapper.find('textarea[name="comment"]').setValue('Bien, aunque tardía.')
    await wrapper.find('[data-test="review-form"]').trigger('submit')
    await settle(6)
    expect(wrapper.find('[data-test="review-sent"]').exists()).toBe(true)
    expect(wrapper.find('[data-test="current-grade"]').text()).toBe('4,2 / 5,0')
    expect(cdb.submissions.find((s) => s.id === IDS.subAna2)!.status).toBe('graded')
    wrapper.unmount()
  })

  it('devolver para corrección cambia el estado y permite re-entregar', async () => {
    signIn(DOCENTE_EMAIL)
    const { wrapper } = await renderAt(`/app/entregas/${IDS.subAna2}`)
    await wrapper.find('textarea[name="comment"]').setValue('Corrija el acarreo.')
    await wrapper.find('input[name="return_for_resubmission"]').setValue(true)
    await wrapper.find('[data-test="review-form"]').trigger('submit')
    await settle(6)
    expect(cdb.submissions.find((s) => s.id === IDS.subAna2)!.status).toBe('returned')
    wrapper.unmount()
    signIn()
    const r = await renderAt(`/app/labs/${IDS.lab1}`)
    expect(r.wrapper.find('[data-test="open-submit"]').attributes('disabled')).toBeUndefined()
    r.wrapper.unmount()
  })

  it('tabla de entregas con filtros por estado', async () => {
    signIn(DOCENTE_EMAIL)
    const { wrapper } = await renderAt(`/app/labs/${IDS.lab1}`)
    await wrapper.find('[data-test="tab-submissions"]').trigger('click')
    await settle()
    let rows = wrapper.findAll('[data-test="submission-row"]')
    expect(rows).toHaveLength(2) // último intento de Ana + Luis
    expect(wrapper.text()).toContain('Tardía')
    expect(wrapper.text()).toContain('Calificado')
    await wrapper.find('[data-test="filter-status"]').setValue('graded')
    rows = wrapper.findAll('[data-test="submission-row"]')
    expect(rows).toHaveLength(1)
    expect(rows[0]!.text()).toContain('Luis Fernando Pérez')
    expect(rows[0]!.text()).toContain('4,5 / 5,0')
    await wrapper.find('[data-test="filter-status"]').setValue('')
    await wrapper.find('[data-test="filter-latest"] input').setValue(false)
    expect(wrapper.findAll('[data-test="submission-row"]')).toHaveLength(3)
    wrapper.unmount()
  })

  it('equipos del lab: fijar y mover integrantes', async () => {
    signIn(DOCENTE_EMAIL)
    const { wrapper } = await renderAt(`/app/labs/${IDS.lab2}`)
    await wrapper.find('[data-test="tab-teams"]').trigger('click')
    await settle()
    expect(wrapper.findAll('[data-test="team-item"]')).toHaveLength(2)
    await wrapper.find('[data-test="team-lock"]').trigger('click')
    await settle()
    expect(cdb.teams.find((tm) => tm.id === IDS.teamFF)!.locked).toBe(true)
    // Mover: Sofía pasa a Los Flip-Flops (aunque esté fijado: lo hace el docente)
    const sofia = wrapper
      .findAll('[data-test="team-member"]')
      .find((li) => li.text().includes('Sofía'))!
    await sofia.find('[data-test="move-select"]').setValue(IDS.teamFF)
    await sofia.find('[data-test="move-submit"]').trigger('click')
    await settle()
    expect(cdb.teams.find((tm) => tm.id === IDS.teamFF)!.member_ids).toHaveLength(3)
    expect(cdb.teams.find((tm) => tm.id === IDS.teamCMP)!.member_ids).toHaveLength(0)
    wrapper.unmount()
  })
})
