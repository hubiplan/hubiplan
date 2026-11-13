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
    ...(entry.todos_enabled !== false
      ? [
          {
            to: '/mein-bereich/aufgaben',
            label: t('Aufgaben'),
            tile: {
              title: t('Aufgaben'),
              text: t('Freigegebene Aufgaben ansehen und übernehmen'),
            },
          },
        ]
      : []),
    ...(entry.cards_enabled !== false
      ? [
          {
            to: '/mein-bereich/ausweis',
            label: t('Ausweis'),
            tile: {
              title: t('Ausweis zeigen'),
              text: t('QR-Code vorzeigen oder als PDF speichern'),
            },
            account: t('Mein Ausweis'),
          },
        ]
      : []),
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
    ...(entry.helpers_enabled
      ? [
          {
            to: '/mein-bereich/helferdienste',
            label: t('Helferdienste'),
            tile: {
              title: t('Helferdienste'),
              text: t('Für Dienste eintragen und eigene Dienste sehen'),
            },
          },
        ]
      : []),
    ...(entry.meetings_enabled
      ? [
          {
            to: '/mein-bereich/versammlungen',
            label: t('Versammlungen'),
            tile: {
              title: t('Versammlungen'),
              text: t('Einladungen mit Tagesordnung und Protokolle'),
            },
          },
        ]
      : []),
    // Meldungen und Ergebnisse auf einer Seite (Menüprüfung 2, N-09)
    ...(entry.entries_enabled || entry.competitions_enabled
      ? [
          {
            to: '/mein-bereich/wettbewerbe',
            label: t('Wettbewerbe'),
            tile: {
              title: t('Meine Wettbewerbe'),
              text: t('Meldungen, Plätze, Werte und Titel'),
            },
          },
        ]
      : []),
    ...(entry.musician
      ? [
          {
            to: '/mein-bereich/musik',
            label: t('Musik'),
            tile: { title: t('Meine Musik'), text: t('Auftritte, Proben und Verfügbarkeit') },
          },
        ]
      : []),
    ...(entry.company
      ? [
          {
            to: '/mein-bereich/firma',
            label: t('Mitarbeiter'),
            tile: {
              title: t('Mitarbeiter'),
              text: t('Mitarbeiter melden, für die die Firma zahlt'),
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
    ...(entry.circulars_enabled !== false
      ? [
          {
            to: '/mein-bereich/rundschreiben',
            label: t('Mitteilungen'),
            tile: { title: t('Mitteilungen'), text: t('Mitteilungen des Vereins lesen') },
          },
        ]
      : []),
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
