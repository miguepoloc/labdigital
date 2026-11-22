/**
 * Cookie indicadora `ld_session=1` (contrato §6.1): NO HttpOnly, la pone la API en login/refresh y la borra al
 * cerrar o revocar la sesión. Sólo sirve para que las páginas públicas no pidan `/me` (y su refresh) a un
 * visitante sin sesión, que dejaría dos 401 en la consola. Nunca se usa para autorizar.
 */
export const SESSION_HINT_COOKIE = 'ld_session'

export function hasSessionHint(): boolean {
  if (typeof document === 'undefined') return true
  return document.cookie.split(';').some((c) => c.trim() === `${SESSION_HINT_COOKIE}=1`)
}
