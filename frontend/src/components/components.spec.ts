import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
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

  it('LdAlert: danger usa role=alert, info role=status', () => {
    expect(mount(LdAlert, { props: { variant: 'danger' } }).attributes('role')).toBe('alert')
    expect(mount(LdAlert, { props: { variant: 'info' } }).attributes('role')).toBe('status')
  })
})
