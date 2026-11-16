// Hilfen der Auslagen: Beträge, Art, Fehler aus dem Server.
import { ApiError } from '../../api/client.ts'
import type { ExpenseKind } from '../../api/expenses.ts'
import { errorMessage } from '../../components/forms.ts'
import { formatEuro } from '../../i18n/format.ts'
import { t } from '../../i18n/index.ts'

/** Betrag aus dem Server (Dezimaltext) als Euro */
export function euro(value: string | null | undefined): string {
  return formatEuro(Number(value ?? 0))
}

/** Betrag aus der Eingabe (Komma oder Punkt) als Dezimaltext für den Server */
export function amountText(value: string): string {
  return value
    .trim()
    .replace(/\s/g, '')
    .replace(/\.(?=\d{3}(\D|$))/g, '')
    .replace(',', '.')
}

export function kindLabel(kind: ExpenseKind): string {
  if (kind === 'mileage') return t('Fahrtkosten')
  if (kind === 'advance') return t('Vorschuss')
  return t('Auslage mit Beleg')
}

/** Feldfehler und Gesamtmeldung einer Antwort des Servers für ``ClaimForm`` */
export function formErrors(err: unknown): Record<string, string> {
  const fields = err instanceof ApiError ? err.fieldErrors : {}
  return { ...fields, detail: errorMessage(err) }
}

export function expenseTabs() {
  return [
    { to: '/finanzen/auslagen', label: t('Auslagen') },
    { to: '/finanzen/auslagen/sammelueberweisung', label: t('Sammelüberweisung') },
    { to: '/finanzen/auslagen/links', label: t('Links ohne Zugang') },
    { to: '/finanzen/auslagen/einstellungen', label: t('Einstellungen') },
  ]
}
