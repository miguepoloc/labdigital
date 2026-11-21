import { describe, expect, it } from 'vitest'
import { isSpaPath, nextOrDefault, safeNext, toRouterPath } from './next'

describe('safeNext (contrato §1: sólo /labdigital/…)', () => {
  it.each([
    ['/labdigital/app', '/labdigital/app'],
    ['/labdigital/fpga/?p=1#x', '/labdigital/fpga/?p=1#x'],
    ['/labdigital/app/perfil', '/labdigital/app/perfil'],
  ])('acepta %s', (input, expected) => {
    expect(safeNext(input)).toBe(expected)
  })

  it.each([
    'https://evil.example/labdigital/',
    '//evil.example/labdigital/',
    '/labdigital/../evil',
    '/\\evil.example',
    '/labdigital\\@evil',
    '/otra/ruta',
    'javascript:alert(1)',
    '',
    undefined,
    ['/labdigital/app'],
  ])('rechaza %s', (input) => {
    expect(safeNext(input)).toBeNull()
  })

  it('usa /labdigital/app por defecto', () => {
    expect(nextOrDefault('https://evil.example')).toBe('/labdigital/app')
  })

  it('distingue rutas de la SPA de los módulos', () => {
    expect(isSpaPath('/labdigital/app/perfil')).toBe(true)
    expect(isSpaPath('/labdigital/fpga/')).toBe(false)
    expect(toRouterPath('/labdigital/app?x=1')).toBe('/app?x=1')
    expect(toRouterPath('/labdigital/')).toBe('/')
  })
})
