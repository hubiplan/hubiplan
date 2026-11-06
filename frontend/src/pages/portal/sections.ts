// Mein Bereich: eine Liste für Seitenleiste, Kacheln und Kontomenü (Menüprüfung M-07).
// Die Seitenleiste nennt die Punkte ohne „Mein/Meine“, Kacheln und Kontomenü mit dem
// gleichen Wort (Ausweis, Termine, Rechnungen).
import type { PortalEntry } from '../../api/portal.ts'
import { t } from '../../i18n/index.ts'

export interface PortalSection {
  to: string
  /** Bezeichnung in der Seitenleiste; ohne Wert erscheint der Punkt dort nicht */
  label?: string
  /** Kachel auf Startseite und Übersicht; ohne Wert keine Kachel */
  tile?: { title: string; text: string }
  /** Eintrag im Kontomenü „Mein Konto“ */
  account?: string
}

export function portalSections(entry: PortalEntry | null): PortalSection[] {
  if (!entry) return []
  return [
    { to: '/mein-bereich', label: t('Übersicht'), account: t('Übersicht') },
    {
      to: '/mein-bereich/aufgaben',
      label: t('Aufgaben'),
      tile: { title: t('Aufgaben'), text: t('Freigegebene Aufgaben ansehen und übernehmen') },
    },
    {
      to: '/mein-bereich/ausweis',
      label: t('Ausweis'),
      tile: { title: t('Ausweis zeigen'), text: t('QR-Code vorzeigen oder als PDF speichern') },
      account: t('Mein Ausweis'),
    },
    // Termine haben einen eigenen Menüpunkt, hier nur Kachel und Kontomenü
    ...(entry.events_enabled
      ? [
          {
            to: '/termine',
            tile: { title: t('Meine Termine'), text: t('Termine ansehen, zu- oder absagen') },
            account: t('Meine Termine'),
          },
        ]
      : []),
    ...(entry.bookings_enabled
      ? [
          {
            to: '/mein-bereich/belegung',
            label: t('Belegung'),
            tile: { title: t('Belegung'), text: t('Schützenhaus, Stand oder Material anfragen') },
          },
        ]
      : []),
    ...(entry.entries_enabled
      ? [
          {
            to: '/mein-bereich/gemeldet',
            label: t('Meldungen'),
            tile: {
              title: t('Meine Meldungen'),
              text: t('Wettbewerbe, für die der Verein dich gemeldet hat'),
            },
          },
        ]
      : []),
    ...(entry.competitions_enabled
      ? [
          {
            to: '/mein-bereich/ergebnisse',
            label: t('Ergebnisse'),
            tile: {
              title: t('Meine Ergebnisse'),
              text: t('Plätze, Werte und Titel aus Wettbewerben'),
            },
          },
        ]
      : []),
    {
      to: '/mein-bereich/rechnungen',
      label: t('Rechnungen'),
      tile: { title: t('Rechnungen'), text: t('Beiträge, offene Beträge und Lastschrift') },
      account: t('Meine Rechnungen'),
    },
    {
      to: '/mein-bereich/rundschreiben',
      label: t('Mitteilungen'),
      tile: { title: t('Mitteilungen'), text: t('Mitteilungen des Vereins lesen') },
    },
    {
      to: '/mein-bereich/daten',
      label: t('Meine Daten'),
      tile: {
        title: t('Meine Daten'),
        text: t('Anschrift und Kontakt ansehen, Änderungen melden'),
      },
    },
  ]
}

/** Unterpunkte von „Mein Bereich“ in der Seitenleiste */
export function portalNav(entry: PortalEntry | null): { to: string; label: string }[] {
  return portalSections(entry).flatMap((s) => (s.label ? [{ to: s.to, label: s.label }] : []))
}
