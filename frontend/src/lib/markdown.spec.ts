import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import LdMarkdown from '@/components/LdMarkdown.vue'
import { parseInline, parseMarkdown, safeHref } from './markdown'

describe('parseMarkdown', () => {
  it('reconoce encabezados, listas, código y citas', () => {
    const blocks = parseMarkdown(
      '# Título\n\nTexto **fuerte** y *suave*.\n\n- uno\n- dos\n\n1. a\n2. b\n\n```vhdl\nx <= y;\n```\n\n> cita',
    )
    expect(blocks.map((b) => b.t)).toEqual(['heading', 'p', 'list', 'list', 'code', 'quote'])
  })

  it('snake_case no es cursiva', () => {
    expect(parseInline('señal clk_div y rst_n')).toEqual([
      { t: 'text', v: 'señal clk_div y rst_n' },
    ])
  })
})

describe('safeHref', () => {
  it.each([
    ['https://ghdl.github.io/', 'https://ghdl.github.io/'],
    ['mailto:docente@unimagdalena.edu.co', 'mailto:docente@unimagdalena.edu.co'],
    ['/labdigital/app', '/labdigital/app'],
    ['javascript:alert(1)', null],
    ['JaVaScRiPt:alert(1)', null],
    ['java\tscript:alert(1)', null],
    ['data:text/html;base64,PHNjcmlwdD4=', null],
    ['vbscript:msgbox', null],
    ['//evil.example/x', null],
  ])('%s → %s', (input, expected) => {
    expect(safeHref(input)).toBe(expected)
  })
})

describe('LdMarkdown (render seguro, sin XSS)', () => {
  const evil = [
    '# Hola <img src=x onerror="alert(1)">',
    '',
    '<script>alert("xss")</script>',
    '',
    '[clic](javascript:alert(1)) [bien](https://ghdl.github.io/)',
    '',
    '<a href="javascript:alert(2)" onclick="alert(3)">enlace</a>',
    '',
    '![img](x" onerror="alert(4))',
    '',
    '<iframe src="https://evil.example"></iframe> <svg onload=alert(5)>',
  ].join('\n')

  it('no crea elementos ni atributos peligrosos y muestra el HTML como texto', () => {
    const w = mount(LdMarkdown, { props: { source: evil } })
    const root = w.element as HTMLElement
    expect(root.querySelector('script, img, iframe, svg, object, embed, style')).toBeNull()
    for (const el of Array.from(root.querySelectorAll('*'))) {
      for (const attr of Array.from(el.attributes)) {
        expect(attr.name.startsWith('on')).toBe(false)
        expect(attr.value.toLowerCase()).not.toContain('javascript:')
      }
    }
    // Sólo queda el enlace seguro, con rel de protección.
    const links = root.querySelectorAll('a')
    expect(links).toHaveLength(1)
    expect(links[0]!.getAttribute('href')).toBe('https://ghdl.github.io/')
    expect(links[0]!.getAttribute('rel')).toContain('noopener')
    // El texto peligroso se ve literal (escapado).
    expect(root.textContent).toContain('<script>alert("xss")</script>')
    expect(root.innerHTML).toContain('&lt;script&gt;')
    w.unmount()
  })

  it('pinta el enunciado con niveles de encabezado bajo el h1 de la página', () => {
    const w = mount(LdMarkdown, {
      props: { source: '# Objetivo\n\n## Pasos\n\n1. Uno\n2. Dos\n\nUse `clk` y **rst**.' },
    })
    expect(w.find('h2').text()).toBe('Objetivo')
    expect(w.find('h3').text()).toBe('Pasos')
    expect(w.findAll('ol li')).toHaveLength(2)
    expect(w.find('code').text()).toBe('clk')
    expect(w.find('strong').text()).toBe('rst')
    w.unmount()
  })
})
