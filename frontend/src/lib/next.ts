import { config } from '@/config'

/**
 * Valida el parámetro `next` (contrato §1): sólo rutas relativas del mismo origen que empiecen por `/labdigital/`.
 * Devuelve la ruta normalizada o `null` si no es segura (evita open redirects).
 */
export function safeNext(raw: unknown): string | null {
  if (typeof raw !== 'string' || raw.length === 0 || raw.length > 2048) return null
  if (!raw.startsWith(config.basePath)) return null
  // Barras invertidas y caracteres de control: algunos navegadores los tratan como "/".
  if (/[\\\u0000-\u001f]/.test(raw)) return null
  const base = 'https://labdigital.invalid'
  let url: URL
  try {
    url = new URL(raw, base)
  } catch {
    return null
  }
  if (url.origin !== base) return null
  if (!url.pathname.startsWith(config.basePath)) return null // p. ej. /labdigital/../evil
  return url.pathname + url.search + url.hash
}

/** `next` seguro o la ruta privada por defecto. */
export function nextOrDefault(raw: unknown): string {
  return safeNext(raw) ?? config.defaultAfterLogin
}

/** Convierte una ruta absoluta `/labdigital/x` en ruta del router (`/x`); `null` si queda fuera de la SPA. */
export function toRouterPath(absolute: string): string | null {
  const base = config.basePath.replace(/\/$/, '')
  if (absolute !== base && !absolute.startsWith(config.basePath)) return null
  const rest = absolute.slice(base.length) || '/'
  return rest
}

/** Rutas (con prefijo) que maneja la SPA; el resto (p. ej. `/labdigital/fpga/`) exige navegación completa. */
export function isSpaPath(absolute: string): boolean {
  const routerPath = toRouterPath(absolute)
  if (routerPath === null) return false
  const path = routerPath.split(/[?#]/)[0] ?? '/'
  return !/^\/(fpga|api|circuitos|micro)(\/|$)/.test(path)
}

/** `fullPath` del router → ruta absoluta con prefijo, para usar como `next`. */
export function absoluteFromRouter(fullPath: string): string {
  return config.basePath.replace(/\/$/, '') + fullPath
}

/** Navegación completa fuera de la SPA (indirecta para poder simularla en tests). */
export const browserNav = {
  assign(url: string): void {
    window.location.assign(url)
  },
}
