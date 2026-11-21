import { describe, expect, it, vi } from 'vitest'
import { db, DEMO_PASSWORD } from '@/mocks/db'
import { RATE_LIMITED_EMAIL } from '@/mocks/handlers'
import { server } from '@/mocks/node'
import { useSessionStore } from '@/stores/session'
import { renderAt, settle } from '@/test/utils'

async function fillAndSubmit(
  wrapper: Awaited<ReturnType<typeof renderAt>>['wrapper'],
  email: string,
  pw: string,
) {
  await wrapper.find('input[name="email"]').setValue(email)
  await wrapper.find('input[name="password"]').setValue(pw)
  await wrapper.find('form').trigger('submit')
  await settle()
}

describe('LoginPage (/entrar)', () => {
  it('valida antes de enviar y no llama a la API', async () => {
    const { wrapper } = await renderAt('/entrar')
    const calls: string[] = []
    server.events.on('request:start', ({ request }) => calls.push(request.url))
    await wrapper.find('form').trigger('submit')
    await settle()
    expect(wrapper.text()).toContain('Este campo es obligatorio.')
    expect(wrapper.find('input[name="email"]').attributes('aria-invalid')).toBe('true')
    expect(calls.filter((u) => u.includes('/auth/login'))).toHaveLength(0)
    server.events.removeAllListeners()
    wrapper.unmount()
  })

  it('correo mal escrito', async () => {
    const { wrapper } = await renderAt('/entrar')
    await fillAndSubmit(wrapper, 'no-es-correo', 'x')
    expect(wrapper.text()).toContain('Escribe un correo válido')
    wrapper.unmount()
  })

  it('invalid_credentials ⇒ mensaje amable y limpia la contraseña', async () => {
    const { wrapper } = await renderAt('/entrar')
    await fillAndSubmit(wrapper, 'estudiante@unimagdalena.edu.co', 'equivocada123')
    expect(wrapper.find('[data-test="form-error"]').text()).toContain(
      'El correo o la contraseña no son correctos.',
    )
    expect((wrapper.find('input[name="password"]').element as HTMLInputElement).value).toBe('')
    wrapper.unmount()
  })

  it('email_not_verified ⇒ botón para reenviar la verificación', async () => {
    const { wrapper } = await renderAt('/entrar')
    await fillAndSubmit(wrapper, 'pendiente@unimagdalena.edu.co', DEMO_PASSWORD)
    expect(wrapper.text()).toContain('Aún no has verificado tu correo')
    await wrapper.find('[data-test="resend"]').trigger('click')
    await settle()
    expect(wrapper.text()).toContain('te enviamos un nuevo enlace')
    wrapper.unmount()
  })

  it('account_inactive ⇒ mensaje propio', async () => {
    const { wrapper } = await renderAt('/entrar')
    await fillAndSubmit(wrapper, 'inactivo@unimagdalena.edu.co', DEMO_PASSWORD)
    expect(wrapper.text()).toContain('Tu cuenta está desactivada')
    wrapper.unmount()
  })

  it('rate_limited ⇒ cuenta atrás con Retry-After y botón deshabilitado', async () => {
    const { wrapper } = await renderAt('/entrar')
    await fillAndSubmit(wrapper, RATE_LIMITED_EMAIL, 'loquesea1234')
    expect(wrapper.text()).toContain('Podrás intentarlo de nuevo en 30 s')
    expect(wrapper.find('button[type="submit"]').attributes('disabled')).toBeDefined()
    wrapper.unmount()
  })

  it('éxito ⇒ guarda la sesión (remember) y vuelve a next', async () => {
    let body: unknown
    server.events.on('request:start', async ({ request }) => {
      if (request.url.endsWith('/auth/login')) body = await request.clone().json()
    })
    const { wrapper, router, pinia } = await renderAt('/entrar?next=/labdigital/app/perfil')
    await fillAndSubmit(wrapper, 'estudiante@unimagdalena.edu.co', DEMO_PASSWORD)
    expect(body).toEqual({
      email: 'estudiante@unimagdalena.edu.co',
      password: DEMO_PASSWORD,
      remember: true,
    })
    expect(useSessionStore(pinia).me?.email).toBe('estudiante@unimagdalena.edu.co')
    await vi.waitFor(() => expect(router.currentRoute.value.name).toBe('profile'))
    expect(db.access).not.toBeNull()
    server.events.removeAllListeners()
    wrapper.unmount()
  })

  it('muestra aviso cuando llega por sesión caducada', async () => {
    const { wrapper } = await renderAt('/entrar?expired=1')
    expect(wrapper.text()).toContain('Tu sesión terminó')
    wrapper.unmount()
  })
})
