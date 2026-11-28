// Gemeinsame Helfer, Typen und Konstanten von BookingsPage.
import { locale } from '../../i18n/index.ts'
import './bookings.css'
import { ZONE } from './format.ts'

export function stamp(value: string) {
  return new Date(value).toLocaleString(locale(), {
    timeZone: ZONE,
    dateStyle: 'short',
    timeStyle: 'short',
  })
}
