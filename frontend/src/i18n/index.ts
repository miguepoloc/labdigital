import { es, type Messages } from './es'

/** Claves en notación de puntos de los textos que son cadenas (`login.title`, `errors.rate_limited`…). */
type StringPaths<T, P extends string = ''> = {
  [K in keyof T & string]: T[K] extends string
    ? `${P}${K}`
    : T[K] extends readonly unknown[]
      ? never
      : StringPaths<T[K], `${P}${K}.`>
}[keyof T & string]

export type MessageKey = StringPaths<Messages>

const messages: Messages = es

function lookup(path: string): unknown {
  return path.split('.').reduce<unknown>((acc, part) => {
    if (acc && typeof acc === 'object') return (acc as Record<string, unknown>)[part]
    return undefined
  }, messages)
}

/** Traduce una clave e interpola `{param}`. Si la clave no existe devuelve la propia clave. */
export function t(key: MessageKey, params?: Record<string, string | number>): string {
  const value = lookup(key)
  if (typeof value !== 'string') return key
  if (!params) return value
  return value.replace(/\{(\w+)\}/g, (_, name: string) =>
    name in params ? String(params[name]) : `{${name}}`,
  )
}

/** Comprueba si existe una clave (útil para mapear códigos de error dinámicos). */
export function hasKey(key: string): key is MessageKey {
  return typeof lookup(key) === 'string'
}

export { messages }
