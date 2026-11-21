import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { defineComponent, h } from 'vue'
import type { FpgaContent, ProjectContent } from '@/api/projects'
import { signIn } from '@/mocks/db'
import {
  failNextAutosaves,
  findMockProject,
  projectsState,
  saveFromElsewhere,
} from '@/mocks/handlers.projects'
import { AUTOSAVE_DEFAULTS } from '@/pages/app/fpga/autosave'
import { registerFpgaSubmitDialog, type FpgaSubmitContext } from '@/pages/app/fpga/extensions'
import { renderAt, settle } from '@/test/utils'

const DEBOUNCE = 40
const defaults = { ...AUTOSAVE_DEFAULTS }

beforeEach(() => {
  AUTOSAVE_DEFAULTS.debounceMs = DEBOUNCE
  AUTOSAVE_DEFAULTS.retryDelaysMs = [30]
})
afterEach(() => {
  Object.assign(AUTOSAVE_DEFAULTS, defaults)
  registerFpgaSubmitDialog(null)
})

const wait = (ms: number) => new Promise((r) => setTimeout(r, ms))

/** `window.JGFPGA` falso, con el comportamiento documentado en EMBED.md. */
function fakeJg(opts: { autoReady?: boolean } = {}) {
  const listeners = { change: new Set<(c: FpgaContent) => void>(), ready: new Set<() => void>() }
  let current: FpgaContent = {
    format: 'basys3-sim-project',
    version: 1,
    name: 'cache del modulo',
    top: 'top',
    simTop: '',
    files: [{ name: 'top.vhd', role: 'design', text: '-- cache' }],
    report: null,
  }
  const fake = {
    version: '1',
    getProject: vi.fn(() => structuredClone(current)),
    loadProject: vi.fn((c: ProjectContent, ...rest: [{ readOnly?: boolean }?]) => {
      void rest
      const content = c as FpgaContent
      if (content.format !== 'basys3-sim-project') {
        throw new Error(`JGFPGA.loadProject: formato desconocido «${String(content.format)}»`)
      }
      current = structuredClone(content)
      return [] as string[]
    }),
    getReport: vi.fn(() => null),
    getReportDocx: vi.fn(async () => null),
    getLastBitstream: vi.fn(async () => null),
    on: vi.fn((ev: 'change' | 'ready', fn: never) => {
      ;(listeners[ev] as Set<unknown>).add(fn)
      if (ev === 'ready' && opts.autoReady) setTimeout(() => (fn as () => void)(), 0)
    }),
    off: vi.fn((ev: 'change' | 'ready', fn: never) => {
      ;(listeners[ev] as Set<unknown>).delete(fn)
    }),
    /** Simula una edición del estudiante (el módulo emite `change` con el proyecto). */
    edit(text: string) {
      current = { ...current, files: [{ name: 'top.vhd', role: 'design', text }] }
      listeners.change.forEach((fn) => fn(structuredClone(current)))
    },
    listeners,
  }
  return fake
}

type Fake = ReturnType<typeof fakeJg>

function frameOf(wrapper: Awaited<ReturnType<typeof renderAt>>['wrapper']) {
  return wrapper.find('[data-test="fpga-frame"]').element as HTMLIFrameElement
}

function install(frame: HTMLIFrameElement, fake: Fake) {
  ;(frame.contentWindow as unknown as { JGFPGA: Fake }).JGFPGA = fake
}

function postReady(frame: HTMLIFrameElement, init: Partial<MessageEventInit> = {}) {
  window.dispatchEvent(
    new MessageEvent('message', {
      data: { type: 'jgfpga:ready', version: '1' },
      origin: window.location.origin,
      source: frame.contentWindow,
      ...init,
    }),
  )
}

async function openWrapper(path: string, fake = fakeJg()) {
  const r = await renderAt(path)
  const frame = frameOf(r.wrapper)
  install(frame, fake)
  postReady(frame)
  await settle()
  return { ...r, frame, fake }
}

function bcd() {
  signIn()
  return projectsState().projects.find((p) => p.name === 'Contador BCD')!
}

const status = (w: Awaited<ReturnType<typeof renderAt>>['wrapper']) =>
  w.find('[data-test="save-status"]').text()

describe('Envoltorio FPGA: carga', () => {
  it('al recibir jgfpga:ready llama SIEMPRE a loadProject con el contenido del proyecto', async () => {
    const p = bcd()
    const { wrapper, fake } = await openWrapper(`/app/fpga/${p.id}`)
    expect(fake.loadProject).toHaveBeenCalledTimes(1)
    expect(fake.loadProject).toHaveBeenCalledWith(p.versions[2]!.content, { readOnly: false })
    expect(fake.on).toHaveBeenCalledWith('change', expect.any(Function))
    expect((wrapper.find('[data-test="project-name"]').element as HTMLInputElement).value).toBe(
      'Contador BCD',
    )
    expect(status(wrapper)).toBe('Guardado')
    expect(frameOf(wrapper).getAttribute('src')).toBe('/labdigital/fpga/')
    wrapper.unmount()
  })

  it('ignora postMessage de otro origen o de otra ventana; un ready repetido no recarga', async () => {
    const p = bcd()
    const { wrapper } = await renderAt(`/app/fpga/${p.id}`)
    const frame = frameOf(wrapper)
    const fake = fakeJg()
    install(frame, fake)
    postReady(frame, { origin: 'https://malicioso.example' })
    postReady(frame, { source: window })
    window.dispatchEvent(
      new MessageEvent('message', {
        data: { type: 'otra-cosa' },
        origin: window.location.origin,
        source: frame.contentWindow,
      }),
    )
    await settle()
    expect(fake.loadProject).not.toHaveBeenCalled()
    postReady(frame)
    postReady(frame)
    await settle()
    expect(fake.loadProject).toHaveBeenCalledTimes(1)
    wrapper.unmount()
  })

  it('también arranca con el evento ready de window.JGFPGA (al cargar el iframe)', async () => {
    const p = bcd()
    const { wrapper } = await renderAt(`/app/fpga/${p.id}`)
    const frame = frameOf(wrapper)
    const fake = fakeJg({ autoReady: true })
    install(frame, fake)
    frame.dispatchEvent(new Event('load'))
    await settle()
    expect(fake.on).toHaveBeenCalledWith('ready', expect.any(Function))
    expect(fake.loadProject).toHaveBeenCalledTimes(1)
    wrapper.unmount()
  })

  it('si loadProject lanza (formato inválido) lo muestra y no activa el autoguardado', async () => {
    const p = bcd()
    findMockProject(p.id)!.versions[2]!.content = { format: 'otro', files: [] }
    const { wrapper, fake } = await openWrapper(`/app/fpga/${p.id}`)
    expect(wrapper.find('[data-test="fatal"]').text()).toContain('formato desconocido')
    expect(fake.on).not.toHaveBeenCalledWith('change', expect.any(Function))
    wrapper.unmount()
  })

  it('sin projectId crea un proyecto con getProject() y pasa a /app/fpga/:id', async () => {
    signIn()
    const before = projectsState().projects.length
    const { wrapper, router, fake } = await openWrapper('/app/fpga?nombre=Mi%20sumador')
    const st = projectsState()
    expect(st.projects).toHaveLength(before + 1)
    const created = st.projects.at(-1)!
    expect(created.name).toBe('Mi sumador')
    expect(created.versions[0]!.content).toMatchObject({
      name: 'Mi sumador',
      files: [{ text: '-- cache' }],
    })
    expect(router.currentRoute.value.params.projectId).toBe(created.id)
    expect(router.currentRoute.value.query).toEqual({})
    expect(fake.loadProject).toHaveBeenCalledTimes(1)
    expect(fake.loadProject.mock.calls[0]![1]).toEqual({ readOnly: false })
    // Y autoguarda sobre el proyecto recién creado.
    fake.edit('-- nuevo')
    await wait(DEBOUNCE + 30)
    await settle()
    expect(st.calls.autosave.at(-1)).toMatchObject({ base_version: created.currentId })
    wrapper.unmount()
  })
})

describe('Envoltorio FPGA: autoguardado', () => {
  it('debounce: varias ediciones ⇒ un PUT con base_version y base_revision', async () => {
    const p = bcd()
    const { wrapper, fake } = await openWrapper(`/app/fpga/${p.id}`)
    const st = projectsState()
    fake.edit('-- uno')
    await wait(DEBOUNCE / 2)
    fake.edit('-- dos')
    await settle(1)
    expect(status(wrapper)).toBe('Cambios sin guardar')
    expect(st.calls.autosave).toHaveLength(0)
    await wait(DEBOUNCE + 30)
    await settle()
    expect(st.calls.autosave).toHaveLength(1)
    expect(st.calls.autosave[0]).toMatchObject({
      base_version: p.versions[2]!.id,
      base_revision: 0,
      content: { files: [{ text: '-- dos' }] },
    })
    expect(findMockProject(p.id)!.revision).toBe(1)
    expect(status(wrapper)).toMatch(/^Guardado hace \d+ s$/)
    // El siguiente guardado usa la revisión nueva (sin 409).
    fake.edit('-- tres')
    await wait(DEBOUNCE + 30)
    await settle()
    expect(st.calls.autosave[1]).toMatchObject({ base_revision: 1 })
    expect(status(wrapper)).toMatch(/^Guardado/)
    wrapper.unmount()
  })

  it('409 ⇒ aviso de conflicto; "Cargar la versión del servidor" recarga el módulo', async () => {
    const p = bcd()
    const { wrapper, fake } = await openWrapper(`/app/fpga/${p.id}`)
    const server = saveFromElsewhere(p.id, {
      ...(p.versions[2]!.content as FpgaContent),
      files: [{ name: 'top.vhd', role: 'design', text: '-- de otra pestaña' }],
    })
    fake.edit('-- mio')
    await wait(DEBOUNCE + 30)
    await settle()
    expect(wrapper.find('[data-test="conflict"]').exists()).toBe(true)
    expect(status(wrapper)).toBe('Conflicto de versiones')
    await wrapper.find('[data-test="conflict-reload"]').trigger('click')
    await settle()
    expect(fake.loadProject).toHaveBeenLastCalledWith(server.content, { readOnly: false })
    expect(wrapper.find('[data-test="conflict"]').exists()).toBe(false)
    // Desde ahí, el autoguardado parte de la versión del servidor.
    fake.edit('-- despues')
    await wait(DEBOUNCE + 30)
    await settle()
    expect(projectsState().calls.autosave.at(-1)).toMatchObject({
      base_version: server.id,
      base_revision: findMockProject(p.id)!.revision - 1,
    })
    expect(status(wrapper)).toMatch(/^Guardado/)
    wrapper.unmount()
  })

  it('409 ⇒ "Sobrescribir con lo mío" guarda sobre la versión actual del servidor', async () => {
    const p = bcd()
    const { wrapper, fake } = await openWrapper(`/app/fpga/${p.id}`)
    const server = saveFromElsewhere(p.id)
    const rev = findMockProject(p.id)!.revision
    fake.edit('-- mio gana')
    await wait(DEBOUNCE + 30)
    await settle()
    await wrapper.find('[data-test="conflict-overwrite"]').trigger('click')
    await settle()
    expect(projectsState().calls.autosave.at(-1)).toMatchObject({
      base_version: server.id,
      base_revision: rev,
      content: { files: [{ text: '-- mio gana' }] },
    })
    const mp = findMockProject(p.id)!
    expect(mp.versions.find((v) => v.id === mp.currentId)!.content).toMatchObject({
      files: [{ text: '-- mio gana' }],
    })
    expect(wrapper.find('[data-test="conflict"]').exists()).toBe(false)
    wrapper.unmount()
  })

  it('sin conexión ⇒ "Sin conexión, reintentando" y luego guarda', async () => {
    const p = bcd()
    const { wrapper, fake } = await openWrapper(`/app/fpga/${p.id}`)
    failNextAutosaves('network')
    fake.edit('-- sin red')
    await wait(DEBOUNCE + 10)
    await settle(2)
    expect(status(wrapper)).toBe('Sin conexión, reintentando')
    await wait(60)
    await settle()
    expect(projectsState().calls.autosave).toHaveLength(2)
    expect(status(wrapper)).toMatch(/^Guardado/)
    wrapper.unmount()
  })

  it('"Guardar versión" guarda lo pendiente, crea una versión manual y sigue sin conflictos', async () => {
    const p = bcd()
    const { wrapper, fake } = await openWrapper(`/app/fpga/${p.id}`)
    fake.edit('-- antes de la versión')
    await wrapper.find('[data-test="save-version"]').trigger('click')
    await settle()
    const mp = findMockProject(p.id)!
    // La autosave abierta del seed tiene > 10 min: el autoguardado abre la v4 y "Guardar versión" crea la v5.
    expect(mp.versions).toHaveLength(5)
    const manual = mp.versions.at(-1)!
    expect(manual).toMatchObject({ kind: 'manual', n: 5 })
    expect(manual.content).toMatchObject({ files: [{ text: '-- antes de la versión' }] })
    expect(wrapper.find('[data-test="notice"]').text()).toContain('Versión 5 guardada.')
    fake.edit('-- después')
    await wait(DEBOUNCE + 30)
    await settle()
    expect(wrapper.find('[data-test="conflict"]').exists()).toBe(false)
    expect(projectsState().calls.autosave.at(-1)).toMatchObject({ base_version: manual.id })
    wrapper.unmount()
  })

  it('al salir de la ruta guarda lo pendiente', async () => {
    const p = bcd()
    const { wrapper, fake, router } = await openWrapper(`/app/fpga/${p.id}`)
    fake.edit('-- me voy')
    await router.push('/app/proyectos')
    await settle()
    expect(projectsState().calls.autosave.at(-1)).toMatchObject({
      content: { files: [{ text: '-- me voy' }] },
    })
    wrapper.unmount()
  })
})

describe('Envoltorio FPGA: solo lectura y extensiones', () => {
  it('?ver=&readonly=1 carga esa versión en solo lectura y no autoguarda', async () => {
    const p = bcd()
    const v1 = p.versions[0]!
    const { wrapper, fake } = await openWrapper(`/app/fpga/${p.id}?ver=${v1.id}&readonly=1`)
    expect(fake.loadProject).toHaveBeenCalledWith(v1.content, { readOnly: true })
    expect(fake.on).not.toHaveBeenCalledWith('change', expect.any(Function))
    expect(status(wrapper)).toBe('Solo lectura · versión 1')
    expect(wrapper.find('[data-test="save-version"]').exists()).toBe(false)
    expect(wrapper.find('[data-test="submit"]').exists()).toBe(false)
    expect(wrapper.find('input[data-test="project-name"]').exists()).toBe(false)
    fake.edit('-- no debería guardarse')
    await wait(DEBOUNCE + 30)
    await settle()
    expect(projectsState().calls.autosave).toHaveLength(0)
    wrapper.unmount()
  })

  it('"Entregar" abre el diálogo provisional y el punto de extensión lo sustituye', async () => {
    const p = bcd()
    const { wrapper } = await openWrapper(`/app/fpga/${p.id}`)
    await wrapper.find('[data-test="submit"]').trigger('click')
    await settle(1)
    expect(document.body.textContent).toContain('Las entregas se habilitan con los cursos')
    wrapper.unmount()

    let received: FpgaSubmitContext | null = null
    registerFpgaSubmitDialog(
      defineComponent({
        props: { context: { type: Object, required: true } },
        setup(props) {
          received = props.context as FpgaSubmitContext
          return () => h('div', { 'data-test': 'real-submit' }, 'diálogo real')
        },
      }),
    )
    const second = await openWrapper(`/app/fpga/${p.id}`)
    second.fake.edit('-- para entregar')
    await second.wrapper.find('[data-test="submit"]').trigger('click')
    await settle(1)
    expect(second.wrapper.find('[data-test="real-submit"]').exists()).toBe(true)
    const ctx = received as unknown as FpgaSubmitContext
    expect(ctx.project.id).toBe(p.id)
    const ref = await ctx.prepareVersion()
    expect(ref.project_id).toBe(p.id)
    expect(ref.version_id).toBe(findMockProject(p.id)!.currentId)
    expect(projectsState().calls.autosave.at(-1)).toMatchObject({
      content: { files: [{ text: '-- para entregar' }] },
    })
    second.wrapper.unmount()
  })
})
