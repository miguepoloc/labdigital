/**
 * Markdown limitado y seguro para enunciados de labs.
 *
 * No produce HTML: convierte el texto en un árbol (bloques e inlines) que `LdMarkdown.vue` pinta con
 * `h()`. Todo el texto acaba en nodos de texto (Vue lo escapa), así que el HTML crudo del enunciado se ve
 * literal y no se ejecuta. Los enlaces sólo admiten `http:`, `https:`, `mailto:` y rutas relativas.
 *
 * Soporta: encabezados `#`, párrafos, saltos con dos espacios, listas `-`/`*`/`1.`, citas `>`,
 * bloques ``` de código, `código`, **negrita**, *cursiva* o _cursiva_, [enlaces](url) y separadores `---`.
 * Las imágenes `![alt](url)` se muestran como su texto alternativo.
 */

export type Inline =
  | { t: 'text'; v: string }
  | { t: 'code'; v: string }
  | { t: 'strong'; c: Inline[] }
  | { t: 'em'; c: Inline[] }
  | { t: 'link'; href: string | null; c: Inline[] }
  | { t: 'br' }

export type Block =
  | { t: 'heading'; level: number; c: Inline[] }
  | { t: 'p'; c: Inline[] }
  | { t: 'list'; ordered: boolean; start: number; items: Inline[][] }
  | { t: 'code'; lang: string; v: string }
  | { t: 'quote'; c: Block[] }
  | { t: 'hr' }

/** Límite defensivo: un enunciado razonable cabe de sobra. */
const MAX_SOURCE = 100_000

/** Devuelve la URL si es segura, o null (el enlace se pinta como texto). */
export function safeHref(raw: string): string | null {
  const href = raw.trim()
  // Quitar caracteres de control/espacios que los navegadores ignoran (`java\tscript:`).
  const compact = href.replace(/[\x00-\x20\x7f]/g, '').toLowerCase()
  if (/^(https?:|mailto:)/.test(compact)) return href
  if (/^[a-z][a-z0-9+.-]*:/.test(compact)) return null // cualquier otro esquema (javascript:, data:…)
  if (compact.startsWith('//')) return null // protocolo relativo a otro host
  if (/^[/#?]/.test(href) || /^[\w.-]/.test(href)) return href
  return null
}

const ESCAPABLE = /[\\`*_[\]()#+\-.!>]/
const WORD = /[\p{L}\p{N}]/u

export function parseInline(src: string): Inline[] {
  const out: Inline[] = []
  let buf = ''
  const flush = () => {
    if (buf) out.push({ t: 'text', v: buf })
    buf = ''
  }
  let i = 0
  while (i < src.length) {
    const c = src[i]!
    const next = src[i + 1]
    if (c === '\\' && next && ESCAPABLE.test(next)) {
      buf += next
      i += 2
      continue
    }
    if (c === '\n') {
      if (buf.endsWith('  ')) {
        buf = buf.replace(/ +$/, '')
        flush()
        out.push({ t: 'br' })
      } else buf += ' '
      i++
      continue
    }
    if (c === '`') {
      const end = src.indexOf('`', i + 1)
      if (end > i + 1) {
        flush()
        out.push({ t: 'code', v: src.slice(i + 1, end) })
        i = end + 1
        continue
      }
    }
    if (c === '*' && next === '*') {
      const end = src.indexOf('**', i + 2)
      if (end > i + 2) {
        flush()
        out.push({ t: 'strong', c: parseInline(src.slice(i + 2, end)) })
        i = end + 2
        continue
      }
    }
    if (c === '*' || (c === '_' && (i === 0 || !WORD.test(src[i - 1]!)))) {
      let end = src.indexOf(c, i + 1)
      // `_` de cierre no puede ir pegado a una palabra (snake_case no es cursiva).
      while (c === '_' && end !== -1 && end + 1 < src.length && WORD.test(src[end + 1]!)) {
        end = src.indexOf(c, end + 1)
      }
      if (end > i + 1 && src[i + 1] !== ' ') {
        flush()
        out.push({ t: 'em', c: parseInline(src.slice(i + 1, end)) })
        i = end + 1
        continue
      }
    }
    if (c === '!' && next === '[') {
      const m = /^!\[([^\]]*)\]\(([^)\s]*)\)/.exec(src.slice(i))
      if (m) {
        buf += m[1] ?? ''
        i += m[0].length
        continue
      }
    }
    if (c === '[') {
      const m = /^\[([^\]]+)\]\(([^)\s]+)\)/.exec(src.slice(i))
      if (m) {
        flush()
        out.push({ t: 'link', href: safeHref(m[2]!), c: parseInline(m[1]!) })
        i += m[0].length
        continue
      }
    }
    buf += c
    i++
  }
  flush()
  return out
}

const RE_FENCE = /^\s*```\s*([\w+-]*)\s*$/
const RE_HEADING = /^(#{1,6})\s+(.*?)\s*#*\s*$/
const RE_HR = /^\s*([-*_])(\s*\1){2,}\s*$/
const RE_QUOTE = /^\s*>\s?(.*)$/
const RE_UL = /^\s*[-*+]\s+(.*)$/
const RE_OL = /^\s*(\d{1,9})[.)]\s+(.*)$/

function isBlockStart(line: string): boolean {
  return (
    RE_FENCE.test(line) ||
    RE_HEADING.test(line) ||
    RE_HR.test(line) ||
    RE_QUOTE.test(line) ||
    RE_UL.test(line) ||
    RE_OL.test(line)
  )
}

function parseLines(lines: string[], depth: number): Block[] {
  const blocks: Block[] = []
  let i = 0
  while (i < lines.length) {
    const line = lines[i]!
    if (!line.trim()) {
      i++
      continue
    }
    const fence = RE_FENCE.exec(line)
    if (fence) {
      const body: string[] = []
      i++
      while (i < lines.length && !RE_FENCE.test(lines[i]!)) body.push(lines[i++]!)
      i++ // cierre (o fin del texto)
      blocks.push({ t: 'code', lang: fence[1] ?? '', v: body.join('\n') })
      continue
    }
    const heading = RE_HEADING.exec(line)
    if (heading) {
      blocks.push({ t: 'heading', level: heading[1]!.length, c: parseInline(heading[2]!) })
      i++
      continue
    }
    if (RE_HR.test(line)) {
      blocks.push({ t: 'hr' })
      i++
      continue
    }
    if (RE_QUOTE.test(line)) {
      const inner: string[] = []
      while (i < lines.length && RE_QUOTE.test(lines[i]!))
        inner.push(RE_QUOTE.exec(lines[i++]!)![1]!)
      blocks.push({ t: 'quote', c: depth < 3 ? parseLines(inner, depth + 1) : [] })
      continue
    }
    const ul = RE_UL.exec(line)
    const ol = RE_OL.exec(line)
    if (ul || ol) {
      const ordered = !ul
      const re = ordered ? RE_OL : RE_UL
      const items: string[] = []
      const start = ol ? Number(ol[1]) : 1
      while (i < lines.length) {
        const l = lines[i]!
        const m = re.exec(l)
        if (m) {
          items.push((ordered ? m[2] : m[1]) ?? '')
          i++
        } else if (l.trim() && /^\s+/.test(l) && items.length) {
          items[items.length - 1] += '\n' + l.trim() // continuación sangrada
          i++
        } else break
      }
      blocks.push({ t: 'list', ordered, start, items: items.map(parseInline) })
      continue
    }
    const para: string[] = []
    while (i < lines.length && lines[i]!.trim() && !(para.length && isBlockStart(lines[i]!))) {
      para.push(lines[i++]!)
    }
    blocks.push({ t: 'p', c: parseInline(para.join('\n').trim()) })
  }
  return blocks
}

export function parseMarkdown(source: string | null | undefined): Block[] {
  const text = (source ?? '').slice(0, MAX_SOURCE).replace(/\r\n?/g, '\n')
  return parseLines(text.split('\n'), 0)
}
