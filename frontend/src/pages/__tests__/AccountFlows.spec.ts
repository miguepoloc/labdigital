import { describe, expect, it, vi } from 'vitest'
import { browserNav } from '@/lib/next'
import { db, DEMO_PASSWORD, expireAccess, expireAll, findUserByEmail, signIn } from '@/mocks/db'
import { renderAt, settle } from '@/test/utils'

describe('VerifyPage (/verificar?t=)', () => {
  it('token válido ⇒ correo verificado', async () => {
    const { wrapper } = await renderAt('/verificar?t=demo-verify')
    expect(wrapper.find('[data-test="verify-ok"]').exists()).toBe(true)
    expect(findUserByEmail('pendiente@unimagdalena.edu.co')?.email_verified).toBe(true)
    wrapper.unmount()
  })

  it('token inválido ⇒ mensaje y formulario para reenviar', async () => {
    const { wrapper } = await renderAt('/verificar?t=caducado')
    expect(wrapper.find('[data-test="verify-error"]').text()).toContain('no es válido o ya caducó')
    await wrapper.find('input[type="email"]').setValue('pendiente@unimagdalena.edu.co')
    await wrapper.find('form').trigger('submit')
    await settle()
    expect(wrapper.text()).toContain('te enviamos un nuevo enlace')
    wrapper.unmount()
  })
})

describe('ForgotPage (/recuperar)', () => {
  it('respuesta neutra (no revela si existe la cuenta)', async () => {
    const { wrapper } = await renderAt('/recuperar')
    await wrapper.find('input[name="email"]').setValue('nadie@ejemplo.co')
    await wrapper.find('form').trigger('submit')
    await settle()
    expect(wrapper.find('[data-test="forgot-done"]').text()).toContain(
      'Si existe una cuenta con nadie@ejemplo.co',
    )
    wrapper.unmount()
  })
})

describe('ResetPage (/restablecer?t=)', () => {
  it('valida que las contraseñas coincidan', async () => {
    const { wrapper } = await renderAt('/restablecer?t=demo-reset')
    const [a, b] = wrapper.findAll('input')
    await a!.setValue('nueva-clave-segura')
    await b!.setValue('otra-cosa-distinta')
    await wrapper.find('form').trigger('submit')
    await settle()
    expect(wrapper.text()).toContain('Las contraseñas no coinciden.')
    wrapper.unmount()
  })

  it('token inválido ⇒ ofrece pedir otro enlace', async () => {
    const { wrapper } = await renderAt('/restablecer?t=malo')
    const [a, b] = wrapper.findAll('input')
    await a!.setValue('nueva-clave-segura')
    await b!.setValue('nueva-clave-segura')
    await wrapper.find('form').trigger('submit')
    await settle()
    expect(wrapper.find('[data-test="form-error"]').text()).toContain('Pedir otro enlace')
    wrapper.unmount()
  })

  it('éxito ⇒ cambia la contraseña y revoca las sesiones', async () => {
    signIn()
    const { wrapper } = await renderAt('/restablecer?t=demo-reset')
    const [a, b] = wrapper.findAll('input')
    await a!.setValue('nueva-clave-segura')
    await b!.setValue('nueva-clave-segura')
    await wrapper.find('form').trigger('submit')
    await settle()
    expect(wrapper.find('[data-test="reset-done"]').exists()).toBe(true)
    expect(findUserByEmail('estudiante@unimagdalena.edu.co')?.password).toBe('nueva-clave-segura')
    expect(db.access).toBeNull()
    wrapper.unmount()
  })
})

describe('SessionPage (/sesion?next=)', () => {
  it('refresh válido ⇒ vuelve a next del módulo con navegación completa', async () => {
    signIn()
    expireAccess()
    const assign = vi.spyOn(browserNav, 'assign').mockImplementation(() => {})
    const { wrapper } = await renderAt('/sesion?next=/labdigital/fpga/?p=1')
    await vi.waitFor(() => expect(assign).toHaveBeenCalledWith('/labdigital/fpga/?p=1'))
    expect(db.calls.refresh).toBe(1)
    wrapper.unmount()
  })

  it('refresh válido y next de la SPA ⇒ navega con el router', async () => {
    signIn()
    expireAccess()
    const { wrapper, router } = await renderAt('/sesion?next=/labdigital/app/sesiones')
    await vi.waitFor(() => expect(router.currentRoute.value.name).toBe('sessions'))
    wrapper.unmount()
  })

  it('refresh fallido ⇒ /entrar?next=', async () => {
    expireAll()
    const { wrapper, router } = await renderAt('/sesion?next=/labdigital/fpga/')
    await vi.waitFor(() => expect(router.currentRoute.value.name).toBe('login'))
    expect(router.currentRoute.value.query.next).toBe('/labdigital/fpga/')
    wrapper.unmount()
  })

  it('next inseguro se descarta', async () => {
    expireAll()
    const { wrapper, router } = await renderAt('/sesion?next=https://evil.example/')
    await vi.waitFor(() => expect(router.currentRoute.value.name).toBe('login'))
    expect(router.currentRoute.value.query.next).toBeUndefined()
    wrapper.unmount()
  })
})

describe('ProfilePage (/app/perfil)', () => {
  it('actualiza el nombre', async () => {
    signIn()
    const { wrapper } = await renderAt('/app/perfil')
    await wrapper.find('input[name="full_name"]').setValue('Ana M. Estudiante')
    await wrapper.find('[data-test="name-form"]').trigger('submit')
    await settle()
    expect(wrapper.text()).toContain('Nombre actualizado.')
    expect(findUserByEmail('estudiante@unimagdalena.edu.co')?.full_name).toBe('Ana M. Estudiante')
    expect(wrapper.find('.ld-shell__user-name').text()).toBe('Ana M. Estudiante')
    wrapper.unmount()
  })

  it('contraseña actual incorrecta ⇒ error en ese campo', async () => {
    signIn()
    const { wrapper } = await renderAt('/app/perfil')
    const inputs = wrapper.find('[data-test="password-form"]').findAll('input')
    await inputs[0]!.setValue('no-es-la-actual')
    await inputs[1]!.setValue('nueva-clave-segura')
    await inputs[2]!.setValue('nueva-clave-segura')
    await wrapper.find('[data-test="password-form"]').trigger('submit')
    await settle()
    expect(wrapper.text()).toContain('La contraseña actual no es correcta.')
    expect(findUserByEmail('estudiante@unimagdalena.edu.co')?.password).toBe(DEMO_PASSWORD)
    wrapper.unmount()
  })

  it('cambia la contraseña', async () => {
    signIn()
    const { wrapper } = await renderAt('/app/perfil')
    const inputs = wrapper.find('[data-test="password-form"]').findAll('input')
    await inputs[0]!.setValue(DEMO_PASSWORD)
    await inputs[1]!.setValue('nueva-clave-segura')
    await inputs[2]!.setValue('nueva-clave-segura')
    await wrapper.find('[data-test="password-form"]').trigger('submit')
    await settle()
    expect(wrapper.text()).toContain('Contraseña actualizada.')
    wrapper.unmount()
  })
})

describe('SessionsPage (/app/sesiones)', () => {
  it('lista, cierra una y cierra las demás', async () => {
    signIn() // + la sesión sembrada en Android
    signIn()
    const { wrapper } = await renderAt('/app/sesiones')
    expect(wrapper.findAll('[data-test="session-item"]')).toHaveLength(3)
    expect(wrapper.text()).toContain('Esta sesión')
    expect(wrapper.text()).toContain('Firefox en Android')

    await wrapper.find('[data-test="revoke"]').trigger('click')
    await settle()
    expect(wrapper.findAll('[data-test="session-item"]')).toHaveLength(2)
    expect(wrapper.text()).toContain('Sesión cerrada.')

    await wrapper.find('[data-test="revoke-others"]').trigger('click')
    await settle()
    expect(wrapper.findAll('[data-test="session-item"]')).toHaveLength(1)
    expect(wrapper.text()).toContain('No hay otras sesiones activas.')
    wrapper.unmount()
  })
})

describe('AppShell', () => {
  it('cerrar sesión desde el menú de usuario', async () => {
    signIn()
    const { wrapper, router } = await renderAt('/app')
    expect(wrapper.text()).toContain('Hola, Ana')
    const userBtn = wrapper.find('.ld-shell__user-btn')
    await userBtn.trigger('click')
    expect(userBtn.attributes('aria-expanded')).toBe('true')
    const logout = wrapper.findAll('[role="menuitem"]').find((b) => b.text() === 'Cerrar sesión')!
    await logout.trigger('click')
    await settle()
    await vi.waitFor(() => expect(router.currentRoute.value.name).toBe('login'))
    expect(db.access).toBeNull()
    wrapper.unmount()
  })
})
