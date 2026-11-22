/** Validación en cliente de los archivos de una entrega (contrato §4, Archivos). */
import type { FileKind } from '@/api/submissions'
import { t } from '@/i18n'

export const MB = 1024 * 1024
export const MAX_FILE_BYTES = 25 * MB
export const MAX_SUBMISSION_BYTES = 100 * MB
/** Tipos admitidos por la API. */
export const ALLOWED_EXTENSIONS = [
  '.bit',
  '.pdf',
  '.docx',
  '.png',
  '.jpg',
  '.jpeg',
  '.mp4',
] as const

/** Tipos por clase de archivo dentro del diálogo. */
export const KIND_EXTENSIONS: Record<FileKind, readonly string[]> = {
  report: ['.pdf', '.docx'],
  bitstream: ['.bit'],
  attachment: ALLOWED_EXTENSIONS,
}

export function extensionOf(name: string): string {
  const i = name.lastIndexOf('.')
  return i >= 0 ? name.slice(i).toLowerCase() : ''
}

const sizeFmt = new Intl.NumberFormat('es-CO', { maximumFractionDigits: 1 })

export function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < MB) return `${sizeFmt.format(bytes / 1024)} KB`
  return `${sizeFmt.format(bytes / MB)} MB`
}

/** Error de un archivo suelto (tipo y tamaño), o null si es válido. */
export function validateFile(file: { name: string; size: number }, kind: FileKind): string | null {
  const ext = extensionOf(file.name)
  const allowed = KIND_EXTENSIONS[kind]
  if (!allowed.includes(ext)) {
    return t('submit.errType', { name: file.name, types: allowed.join(', ') })
  }
  if (file.size > MAX_FILE_BYTES) {
    return t('submit.errFileSize', { name: file.name, max: formatBytes(MAX_FILE_BYTES) })
  }
  if (file.size === 0) return t('submit.errEmpty', { name: file.name })
  return null
}

/** Error del conjunto (100 MB por entrega), o null. */
export function validateTotal(files: { size: number }[]): string | null {
  const total = files.reduce((acc, f) => acc + f.size, 0)
  return total > MAX_SUBMISSION_BYTES
    ? t('submit.errTotalSize', {
        total: formatBytes(total),
        max: formatBytes(MAX_SUBMISSION_BYTES),
      })
    : null
}
