// Gemeinsame Helfer, Typen und Konstanten von BookingsPage.
import type { BookingKind } from '../../api/finance.ts'
import { t } from '../../i18n/index.ts'

export const KIND_LABEL: Record<BookingKind, string> = {
  income: t('Einnahme'),
  expense: t('Ausgabe'),
  transfer: t('Umbuchung'),
}
