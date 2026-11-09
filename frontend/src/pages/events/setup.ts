// Einrichtung des Kalenders (Menüprüfung M-01): eine Quelle für die Reiter unter
// Termine › Einrichtung und die Übersicht Einstellungen › Einrichtung (S-02).
import { t } from '../../i18n/index.ts'

export interface EventSetupTab {
  to: string
  label: string
}

/** Reiter der Einrichtung: Kategorien und fremde Kalender, Weitergabe und Link nur zum Verwalten. */
export function eventSetupTabs(manage: boolean, categories: boolean): EventSetupTab[] {
  return [
    ...(categories ? [{ to: '/termine/einrichtung/kategorien', label: t('Kategorien') }] : []),
    ...(categories ? [{ to: '/termine/einrichtung/fremde', label: t('Fremde Kalender') }] : []),
    ...(manage ? [{ to: '/termine/einrichtung/weitergabe', label: t('Weitergabe') }] : []),
    ...(manage ? [{ to: '/termine/einrichtung/link', label: t('Öffentlicher Link') }] : []),
  ]
}
