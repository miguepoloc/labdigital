import { describe, expect, it } from 'vitest'
import { signIn } from '@/mocks/db'
import { renderAt } from '@/test/utils'

describe('LandingPage (/)', () => {
  it('muestra las secciones del diseño aprobado y los CTA', async () => {
    const { wrapper } = await renderAt('/')
    for (const id of ['modulos', 'funciones', 'docentes', 'agente', 'equipo']) {
      expect(wrapper.find(`section#${id}`).exists()).toBe(true)
    }
    expect(wrapper.find('h1').text()).toBe('Del primer AND al bitstream, en el navegador.')
    const hrefs = wrapper.findAll('a').map((a) => a.attributes('href'))
    expect(hrefs).toContain('/labdigital/registro')
    expect(hrefs).toContain('/labdigital/entrar')
    expect(hrefs.some((h) => h?.includes('JGFPGA-Agente-1.1.0-win64.zip'))).toBe(true)
    expect(hrefs.some((h) => h?.includes('JGFPGA-Agente-1.1.0-mac.zip'))).toBe(true)
    // Ilustración de la placa: 16 LEDs y 16 switches.
    expect(wrapper.findAll('.b-led')).toHaveLength(16)
    expect(wrapper.findAll('.b-knob rect')).toHaveLength(16)
    // Sin el distintivo de vista previa.
    expect(wrapper.text()).not.toContain('Vista previa del diseño')
    expect(wrapper.find('[data-test="landing-login"]').attributes('href')).toBe(
      '/labdigital/entrar',
    )
    wrapper.unmount()
  })

  it('con sesión iniciada el botón superior lleva a mis laboratorios', async () => {
    signIn()
    const { wrapper } = await renderAt('/')
    const btn = wrapper.find('[data-test="landing-app"]')
    expect(btn.text()).toBe('Ir a mis laboratorios')
    expect(btn.attributes('href')).toBe('/labdigital/app')
    expect(wrapper.find('[data-test="landing-login"]').exists()).toBe(false)
    wrapper.unmount()
  })
})
