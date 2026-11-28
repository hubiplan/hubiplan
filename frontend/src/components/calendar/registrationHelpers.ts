// Verbindliche Anmeldung mit Teilnahmegebühr am Termin (konzepte/veranstaltungen-anmeldung-gebuehr.md,
// Stufen A1–A3): Verwaltung richtet Tarife, Preisstufen, Warteliste und Stornostaffel ein und
// sieht alle Anmeldungen, Mitglieder melden sich und ihre Familie an und ab.
// Diese Datei: gemeinsame Helfer, Typen und Konstanten des Bereichs.
import type { Price } from '../../api/registrations.ts'
import { berlin, formatDay } from './time.ts'
import { lang, t } from '../../i18n/index.ts'

export function priceName(p: Price): string {
  return lang() === 'en' && p.name_en ? p.name_en : p.name
}

export function when(iso: string): string {
  const d = berlin(iso)
  return t('{x}, {time} Uhr', { x: formatDay(d.date), time: d.time })
}
