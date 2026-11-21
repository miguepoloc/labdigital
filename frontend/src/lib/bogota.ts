/**
 * Fechas de cursos y labs: siempre en la zona de la universidad (America/Bogota, UTC−5 sin horario de
 * verano) y con formato colombiano, sin importar la zona del navegador.
 */
export const BOGOTA_TZ = 'America/Bogota'
const OFFSET = '-05:00'
const OFFSET_MS = 5 * 60 * 60 * 1000

const longFmt = new Intl.DateTimeFormat('es-CO', {
  timeZone: BOGOTA_TZ,
  weekday: 'long',
  day: 'numeric',
  month: 'long',
  year: 'numeric',
  hour: 'numeric',
  minute: '2-digit',
  hour12: true,
})

const shortFmt = new Intl.DateTimeFormat('es-CO', {
  timeZone: BOGOTA_TZ,
  day: '2-digit',
  month: '2-digit',
  year: 'numeric',
  hour: 'numeric',
  minute: '2-digit',
  hour12: true,
})

function valid(iso: string | null | undefined): Date | null {
  if (!iso) return null
  const d = new Date(iso)
  return Number.isNaN(d.getTime()) ? null : d
}

/** «viernes, 5 de febrero de 2027, 11:59 p. m.» */
export function formatBogota(iso: string | null | undefined): string {
  const d = valid(iso)
  return d ? longFmt.format(d) : ''
}

/** «05/02/2027, 11:59 p. m.» */
export function formatBogotaShort(iso: string | null | undefined): string {
  const d = valid(iso)
  return d ? shortFmt.format(d) : ''
}

/** ISO UTC → valor de `<input type="datetime-local">` en hora de Bogotá (`YYYY-MM-DDTHH:mm`). */
export function toBogotaInput(iso: string | null | undefined): string {
  const d = valid(iso)
  if (!d) return ''
  return new Date(d.getTime() - OFFSET_MS).toISOString().slice(0, 16)
}

/** Valor de `datetime-local` interpretado en hora de Bogotá → ISO UTC (o null si está vacío/no válido). */
export function fromBogotaInput(local: string): string | null {
  if (!/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$/.test(local)) return null
  const d = new Date(`${local}:00${OFFSET}`)
  return Number.isNaN(d.getTime()) ? null : d.toISOString()
}
