import { t } from '@/i18n'

const bytesFmt = new Intl.NumberFormat('es-CO', { maximumFractionDigits: 1 })

/** "512 B", "3,4 KB", "1,2 MB". */
export function formatBytes(n: number): string {
  if (n < 1024) return `${n} B`
  if (n < 1024 * 1024) return `${bytesFmt.format(n / 1024)} KB`
  return `${bytesFmt.format(n / (1024 * 1024))} MB`
}

/** Tiempo transcurrido corto: "3 s", "5 min", "2 h". */
export function formatAgo(fromMs: number, nowMs: number): string {
  const s = Math.max(0, Math.round((nowMs - fromMs) / 1000))
  if (s < 60) return t('projects.fpga.ago.seconds', { n: s })
  const m = Math.floor(s / 60)
  if (m < 60) return t('projects.fpga.ago.minutes', { n: m })
  return t('projects.fpga.ago.hours', { n: Math.floor(m / 60) })
}
