import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiError } from '@/api/errors'
import type { AutosaveRequest, AutosaveResponse } from '@/api/projects'
import { Autosaver, type AutosaverSnapshot } from './autosave'

const content = (text: string) => ({
  format: 'basys3-sim-project' as const,
  version: 1 as const,
  name: 'p',
  top: 'top',
  simTop: '',
  files: [{ name: 'top.vhd', role: 'design', text }],
  report: null,
})

function setup(save?: (b: AutosaveRequest) => Promise<AutosaveResponse>) {
  const calls: AutosaveRequest[] = []
  let revision = 7
  const impl =
    save ??
    (async () => {
      revision++
      return { version_id: 'v1', n: 1, revision }
    })
  const states: AutosaverSnapshot['status'][] = []
  const keepalive = vi.fn(() => true)
  const saver = new Autosaver({
    base: { version: 'v1', n: 1, revision: 7 },
    save: (b) => {
      calls.push(structuredClone(b))
      return impl(b)
    },
    keepalive,
    debounceMs: 5000,
    retryDelaysMs: [1000, 3000],
    onChange: (s) => states.push(s.status),
  })
  return { saver, calls, states, keepalive }
}

const conflict = (rev: number) =>
  new ApiError({
    status: 409,
    code: 'version_conflict',
    message: 'conflicto',
    details: { current_version: 9, current_revision: rev, current_version_id: 'v9' },
  })

describe('Autosaver', () => {
  beforeEach(() => vi.useFakeTimers())
  afterEach(() => vi.useRealTimers())

  it('espera 5 s desde el último cambio y manda base_version + base_revision', async () => {
    const { saver, calls } = setup()
    saver.change(content('a'))
    await vi.advanceTimersByTimeAsync(3000)
    saver.change(content('b'))
    await vi.advanceTimersByTimeAsync(4999)
    expect(calls).toHaveLength(0)
    expect(saver.snapshot.status).toBe('pending')
    await vi.advanceTimersByTimeAsync(1)
    expect(calls).toHaveLength(1)
    expect(calls[0]).toEqual({ content: content('b'), base_version: 1, base_revision: 7 })
    expect(saver.snapshot.status).toBe('saved')
    expect(saver.snapshot.lastSavedAt).not.toBeNull()
    // El siguiente guardado parte de la revisión devuelta.
    saver.change(content('c'))
    await vi.advanceTimersByTimeAsync(5000)
    expect(calls[1]).toMatchObject({ base_version: 1, base_revision: 8 })
  })

  it('no lanza dos guardados a la vez: lo que llega mientras guarda sale después', async () => {
    let release!: () => void
    const { saver, calls } = setup(
      (b) =>
        new Promise((r) => {
          release = () => r({ version_id: 'v1', n: 1, revision: b.base_revision + 1 })
        }),
    )
    saver.change(content('a'))
    await vi.advanceTimersByTimeAsync(5000)
    expect(saver.snapshot.status).toBe('saving')
    saver.change(content('b'))
    await vi.advanceTimersByTimeAsync(5000)
    expect(calls).toHaveLength(1)
    release()
    await vi.advanceTimersByTimeAsync(0)
    expect(saver.snapshot.status).toBe('pending')
    await vi.advanceTimersByTimeAsync(5000)
    expect(calls).toHaveLength(2)
    expect(calls[1]).toMatchObject({ content: content('b'), base_revision: 8 })
  })

  it('409 version_conflict ⇒ estado conflict sin reintentos; overwrite usa la versión del servidor', async () => {
    let fail = true
    const { saver, calls } = setup(async (b) => {
      if (fail) throw conflict(12)
      return {
        version_id: 'v' + String(b.base_version),
        n: b.base_version,
        revision: b.base_revision + 1,
      }
    })
    saver.change(content('mio'))
    await vi.advanceTimersByTimeAsync(5000)
    expect(saver.snapshot.status).toBe('conflict')
    expect(saver.snapshot.conflict).toEqual({
      current_version: 9,
      current_revision: 12,
      current_version_id: 'v9',
    })
    saver.change(content('mio 2'))
    await vi.advanceTimersByTimeAsync(60_000)
    expect(calls).toHaveLength(1)
    fail = false
    await saver.overwrite()
    expect(calls[1]).toEqual({ content: content('mio 2'), base_version: 9, base_revision: 12 })
    expect(saver.snapshot.status).toBe('saved')
  })

  it('reset (recargar del servidor) descarta lo pendiente y cambia la base', async () => {
    const { saver, calls } = setup(async () => {
      throw conflict(12)
    })
    saver.change(content('x'))
    await vi.advanceTimersByTimeAsync(5000)
    saver.reset({ version: 'v9', n: 9, revision: 12 })
    expect(saver.snapshot.status).toBe('saved')
    expect(saver.unsaved).toBeNull()
    await vi.advanceTimersByTimeAsync(60_000)
    expect(calls).toHaveLength(1)
  })

  it('sin red ⇒ offline y reintento con espera creciente hasta lograrlo', async () => {
    let failures = 2
    const { saver, calls, states } = setup(async (b) => {
      if (failures-- > 0) throw new ApiError({ status: 0, code: 'network_error', message: 'x' })
      return { version_id: 'v1', n: 1, revision: b.base_revision + 1 }
    })
    saver.change(content('a'))
    await vi.advanceTimersByTimeAsync(5000)
    expect(saver.snapshot.status).toBe('offline')
    await vi.advanceTimersByTimeAsync(999)
    expect(calls).toHaveLength(1)
    await vi.advanceTimersByTimeAsync(1)
    expect(calls).toHaveLength(2)
    expect(saver.snapshot.status).toBe('offline')
    await vi.advanceTimersByTimeAsync(2999)
    expect(calls).toHaveLength(2)
    // Un cambio durante la espera no reinicia el reintento: sale en él con el contenido más nuevo.
    saver.change(content('b'))
    await vi.advanceTimersByTimeAsync(1)
    expect(calls).toHaveLength(3)
    expect(calls[2]!.content).toEqual(content('b'))
    expect(saver.snapshot.status).toBe('saved')
    expect(states).toContain('offline')
  })

  it('5xx también reintenta; 413 queda en error sin reintentos', async () => {
    const { saver, calls } = setup(async () => {
      throw new ApiError({ status: 413, code: 'payload_too_large', message: 'grande' })
    })
    saver.change(content('a'))
    await vi.advanceTimersByTimeAsync(5000)
    expect(saver.snapshot.status).toBe('error')
    await vi.advanceTimersByTimeAsync(60_000)
    expect(calls).toHaveLength(1)
    expect(saver.snapshot.dirty).toBe(true)
  })

  it('flush guarda ya y flushOnExit manda lo pendiente con keepalive', async () => {
    const { saver, calls, keepalive } = setup()
    saver.change(content('a'))
    await saver.flush()
    expect(calls).toHaveLength(1)
    expect(saver.flushOnExit()).toBe(false) // nada pendiente
    saver.change(content('b'))
    expect(saver.flushOnExit()).toBe(true)
    expect(keepalive).toHaveBeenCalledWith({
      content: content('b'),
      base_version: 1,
      base_revision: 8,
    })
  })

  it('si la página sigue viva tras el keepalive, el 409 que causó se resuelve solo', async () => {
    let first = true
    const { saver, calls } = setup(async (b) => {
      if (first) {
        first = false
        throw conflict(8) // = revisión enviada por keepalive (7) + 1
      }
      return { version_id: 'v9', n: 2, revision: b.base_revision + 1 }
    })
    saver.change(content('a'))
    saver.flushOnExit()
    saver.change(content('b'))
    await vi.advanceTimersByTimeAsync(5000)
    expect(calls).toHaveLength(2)
    expect(calls[1]).toMatchObject({ base_version: 9, base_revision: 8 })
    expect(saver.snapshot.status).toBe('saved')
  })
})
