import { t, type MessageKey } from '@/i18n'

/** Título de la pestaña: "<página> · LabDigital" o el nombre completo en la landing. */
export function pageTitle(key: MessageKey | undefined): string {
  return key ? `${t(key)} · ${t('app.name')}` : t('app.fullName')
}
