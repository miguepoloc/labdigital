import { http, HttpResponse } from 'msw'
import { describe, expect, it } from 'vitest'
import { config } from '@/config'
import { findUserByEmail } from '@/mocks/db'
import { server } from '@/mocks/node'
import { renderAt, settle } from '@/test/utils'

type W = Awaited<ReturnType<typeof renderAt>>['wrapper']

async function fill(w: W, v: { name?: string; email?: string; pw?: string; accept?: boolean }) {
  if (v.name !== undefined) await w.find('input[name="full_name"]').setValue(v.name)
  if (v.email !== undefined) await w.find('input[name="email"]').setValue(v.email)
  if (v.pw !== undefined) await w.find('input[name="password"]').setValue(v.pw)
  if (v.accept !== undefined) await w.find('input[name="accept_data_policy"]').setValue(v.accept)
  await w.find('form').trigger('submit')
  await settle()
}

describe('RegisterPage (/registro)', () => {
  it('enlaza la política de datos configurable', async () => {
    const { wrapper } = await renderAt('/registro')
    expect(wrapper.find(`a[href="${config.dataPolicyUrl}"]`).exists()).toBe(true)
    wrapper.unmount()
  })

  it('valida todos los campos, incluida la aceptación de la política', async () => {
    const { wrapper } = await renderAt('/registro')
    await fill(wrapper, {})
    const text = wrapper.text()
    expect(text).toContain('Revisa los campos marcados.')
    expect(text).toContain('Debes aceptar la política de protección de datos')
    expect(wrapper.findAll('[aria-invalid="true"]')).toHaveLength(4)
    wrapper.unmount()
  })

  it('exige contraseña de al menos 10 caracteres', async () => {
    const { wrapper } = await renderAt('/registro')
    await fill(wrapper, {
      name: 'Nueva Persona',
      email: 'n@unimagdalena.edu.co',
      pw: 'corta',
      accept: true,
    })
    expect(wrapper.text()).toContain('al menos 10 caracteres')
    expect(findUserByEmail('n@unimagdalena.edu.co')).toBeUndefined()
    wrapper.unmount()
  })

  it('el medidor de seguridad reacciona a la contraseña', async () => {
    const { wrapper } = await renderAt('/registro')
    await wrapper.find('input[name="password"]').setValue('Muy-Segura-2026!')
    expect(wrapper.text()).toContain('Seguridad de la contraseña: muy buena')
    wrapper.unmount()
  })

  it('éxito ⇒ pantalla "revisa tu correo" y crea la cuenta sin verificar', async () => {
    const { wrapper } = await renderAt('/registro')
    await fill(wrapper, {
      name: 'Nueva Persona',
      email: 'nueva@unimagdalena.edu.co',
      pw: 'una-clave-larga',
      accept: true,
    })
    expect(wrapper.find('[data-test="register-done"]').text()).toContain(
      'nueva@unimagdalena.edu.co',
    )
    expect(findUserByEmail('nueva@unimagdalena.edu.co')?.email_verified).toBe(false)
    wrapper.unmount()
  })

  it('validation_error del servidor se muestra en el campo', async () => {
    server.use(
      http.post('/labdigital/api/v1/auth/register', () =>
        HttpResponse.json(
          {
            error: {
              code: 'validation_error',
              message: 'Datos no válidos',
              details: { fields: { password: 'Esa contraseña es demasiado común.' } },
            },
          },
          { status: 422 },
        ),
      ),
    )
    const { wrapper } = await renderAt('/registro')
    await fill(wrapper, {
      name: 'Nueva Persona',
      email: 'x@unimagdalena.edu.co',
      pw: 'contraseña1',
      accept: true,
    })
    expect(wrapper.text()).toContain('Esa contraseña es demasiado común.')
    expect(wrapper.text()).toContain('Algunos datos no son válidos')
    wrapper.unmount()
  })
})
