import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import { createMemoryHistory, createRouter } from 'vue-router'
import LdAlert from './LdAlert.vue'
import LdButton from './LdButton.vue'
import LdPasswordField from './LdPasswordField.vue'
import LdTextField from './LdTextField.vue'

describe('componentes base', () => {
  it('LdTextField: label asociado, ayuda y error accesibles', () => {
    const w = mount(LdTextField, {
      props: { label: 'Correo', help: 'Ayuda', error: 'Mal', id: 'x' },
    })
    expect(w.find('label').attributes('for')).toBe('x')
    const input = w.find('input')
    expect(input.attributes('aria-invalid')).toBe('true')
    expect(input.attributes('aria-describedby')).toBe('x-help x-error')
    expect(w.find('#x-error').attributes('aria-live')).toBe('polite')
    expect(w.find('#x-error').text()).toBe('Mal')
  })

  it('LdPasswordField: mostrar/ocultar', async () => {
    const w = mount(LdPasswordField, { props: { label: 'Contraseña' } })
    expect(w.find('input').attributes('type')).toBe('password')
    const toggle = w.find('button')
    expect(toggle.attributes('aria-pressed')).toBe('false')
    await toggle.trigger('click')
    expect(w.find('input').attributes('type')).toBe('text')
    expect(toggle.attributes('aria-pressed')).toBe('true')
    expect(toggle.text()).toBe('Ocultar contraseña')
  })

  it('LdButton: loading deshabilita y marca aria-busy', () => {
    const w = mount(LdButton, { props: { loading: true }, slots: { default: 'Enviar' } })
    expect(w.find('button').attributes('disabled')).toBeDefined()
    expect(w.find('button').attributes('aria-busy')).toBe('true')
  })

  it('LdButton con `to` renderiza un enlace con href (y `href` externo tal cual)', async () => {
    const router = createRouter({
      history: createMemoryHistory('/labdigital/'),
      routes: [{ path: '/', name: 'x', component: { template: '<div />' } }],
    })
    await router.push('/')
    const w = mount(LdButton, {
      props: { to: { name: 'x' } },
      slots: { default: 'Ir' },
      global: { plugins: [router] },
    })
    expect(w.find('a').attributes('href')).toBe('/labdigital/')
    const ext = mount(LdButton, { props: { href: 'https://ejemplo.co/' } })
    expect(ext.find('a').attributes('href')).toBe('https://ejemplo.co/')
  })

  it('LdAlert: danger usa role=alert, info role=status', () => {
    expect(mount(LdAlert, { props: { variant: 'danger' } }).attributes('role')).toBe('alert')
    expect(mount(LdAlert, { props: { variant: 'info' } }).attributes('role')).toBe('status')
  })
})
