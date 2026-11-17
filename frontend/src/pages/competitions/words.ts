// Wörter des Moduls Wettbewerbe: mit Schießsport die Begriffe der Schützen, sonst neutrale
// (UX-Audit 16.11. VW-13). Ein Turn- oder Schachverein liest sonst „Schüsse je Schütze“.
// Beide Fassungen stehen als fester Text hier, damit die Übersetzungsprüfung sie findet.
import { t } from '../../i18n/index.ts'
import { useOptionalOrg } from '../../org/OrgContext.tsx'

type Params = Record<string, string | number | null | undefined>
type Pair = [(p?: Params) => string, (p?: Params) => string]

const WORDS = {
  ['Schütze']: [(p) => t('Schütze', p), (p) => t('Teilnehmer/in', p)],
  ['Schützen']: [(p) => t('Schützen', p), (p) => t('Teilnehmende', p)],
  ['Noch keine Schützen.']: [
    (p) => t('Noch keine Schützen.', p),
    (p) => t('Noch keine Teilnehmenden.', p),
  ],
  ['Bester Schütze']: [(p) => t('Bester Schütze', p), (p) => t('Beste Einzelwertung', p)],
  ['Eigene Schützen']: [(p) => t('Eigene Schützen', p), (p) => t('Eigene Teilnehmende', p)],
  ['· {count} Schützen']: [
    (p) => t('· {count} Schützen', p),
    (p) => t('· {count} Teilnehmende', p),
  ],
  ['Schuss Nr.']: [(p) => t('Schuss Nr.', p), (p) => t('Wertung Nr.', p)],
  ['Schüsse']: [(p) => t('Schüsse', p), (p) => t('Wertungen', p)],
  ['Schüsse insgesamt']: [(p) => t('Schüsse insgesamt', p), (p) => t('Wertungen insgesamt', p)],
  ['Die besten {n} Schüsse zählen.']: [
    (p) => t('Die besten {n} Schüsse zählen.', p),
    (p) => t('Die besten {n} Wertungen zählen.', p),
  ],
  ['Alle Schüsse zählen.']: [
    (p) => t('Alle Schüsse zählen.', p),
    (p) => t('Alle Wertungen zählen.', p),
  ],
  ['Weniger Schützen: die Einheit wird nicht gewertet.']: [
    (p) => t('Weniger Schützen: die Einheit wird nicht gewertet.', p),
    (p) => t('Weniger Teilnehmende: die Einheit wird nicht gewertet.', p),
  ],
  ['Grundlage: Schießdurchgang']: [
    (p) => t('Grundlage: Schießdurchgang', p),
    (p) => t('Grundlage: Durchgang', p),
  ],
  ['Schüsse je Schütze']: [
    (p) => t('Schüsse je Schütze', p),
    (p) => t('Wertungen je Teilnehmer/in', p),
  ],
  ['Welche Schüsse zählen?']: [
    (p) => t('Welche Schüsse zählen?', p),
    (p) => t('Welche Wertungen zählen?', p),
  ],
  ['Alle Schüsse']: [(p) => t('Alle Schüsse', p), (p) => t('Alle Wertungen', p)],
  ['Höchstwert je Schuss']: [
    (p) => t('Höchstwert je Schuss', p),
    (p) => t('Höchstwert je Wertung', p),
  ],
  ['Schüsse im Stechen (Vorschlag)']: [
    (p) => t('Schüsse im Stechen (Vorschlag)', p),
    (p) => t('Wertungen in der Entscheidungsrunde (Vorschlag)', p),
  ],
  ['beim Anlegen des Stechens vor Ort änderbar']: [
    (p) => t('beim Anlegen des Stechens vor Ort änderbar', p),
    (p) => t('beim Anlegen der Entscheidungsrunde vor Ort änderbar', p),
  ],
  ['gewerteten Schüssen']: [(p) => t('gewerteten Schüssen', p), (p) => t('gezählten Wertungen', p)],
  [' Höchstwert je Schuss {x}, {x2}.']: [
    (p) => t(' Höchstwert je Schuss {x}, {x2}.', p),
    (p) => t(' Höchstwert je Wertung {x}, {x2}.', p),
  ],
  ['ganze Ringe']: [(p) => t('ganze Ringe', p), (p) => t('ganze Punkte', p)],
  ['Stechen']: [(p) => t('Stechen', p), (p) => t('Entscheidungsrunde', p)],
  [': Stechen nötig. Erst danach lässt sich der Wettbewerb endgültig abschließen.']: [
    (p) => t(': Stechen nötig. Erst danach lässt sich der Wettbewerb endgültig abschließen.', p),
    (p) =>
      t(
        ': Entscheidungsrunde nötig. Erst danach lässt sich der Wettbewerb endgültig abschließen.',
        p,
      ),
  ],
  ['* Gleichstand: Stechen nötig']: [
    (p) => t('* Gleichstand: Stechen nötig', p),
    (p) => t('* Gleichstand: Entscheidungsrunde nötig', p),
  ],
  ['Standmodus (Vollbild, Handy, offline)']: [
    (p) => t('Standmodus (Vollbild, Handy, offline)', p),
    (p) => t('Erfassung vor Ort (Vollbild, Handy, offline)', p),
  ],
  ['Schießliste nach Name']: [
    (p) => t('Schießliste nach Name', p),
    (p) => t('Startliste nach Name', p),
  ],
  ['Leere Schießliste']: [(p) => t('Leere Schießliste', p), (p) => t('Leere Startliste', p)],
  ['Zum Eintragen am Stand, erfasste Werte sind eingedruckt']: [
    (p) => t('Zum Eintragen am Stand, erfasste Werte sind eingedruckt', p),
    (p) => t('Zum Eintragen vor Ort, erfasste Werte sind eingedruckt', p),
  ],
  ['Vier Karten je Seite mit Startnummer und Kästchen für die Schüsse']: [
    (p) => t('Vier Karten je Seite mit Startnummer und Kästchen für die Schüsse', p),
    (p) => t('Vier Karten je Seite mit Startnummer und Kästchen für die Wertungen', p),
  ],
  ['Ergebnisse und Schützen löschen']: [
    (p) => t('Ergebnisse und Schützen löschen', p),
    (p) => t('Ergebnisse und Teilnehmende löschen', p),
  ],
  ['„{title}“ mit allen Startern, Ergebnissen und Stechen löschen?']: [
    (p) => t('„{title}“ mit allen Startern, Ergebnissen und Stechen löschen?', p),
    (p) => t('„{title}“ mit allen Startern, Ergebnissen und Entscheidungsrunden löschen?', p),
  ],
  ['„{name}“ mit allen Ergebnissen und Stechen löschen?']: [
    (p) => t('„{name}“ mit allen Ergebnissen und Stechen löschen?', p),
    (p) => t('„{name}“ mit allen Ergebnissen und Entscheidungsrunden löschen?', p),
  ],
  ['Schießbedingungen']: [(p) => t('Schießbedingungen', p), (p) => t('Wertungsregeln', p)],
  ['nur, wenn auf Papier gezählt wurde; live zählt der Standmodus']: [
    (p) => t('nur, wenn auf Papier gezählt wurde; live zählt der Standmodus', p),
    (p) => t('nur, wenn auf Papier gezählt wurde; live zählt die Erfassung vor Ort', p),
  ],
  ['Schießen mit Einzel- und Zugwertung']: [
    (p) => t('Schießen mit Einzel- und Zugwertung', p),
    (p) => t('Wettbewerb mit Einzel- und Gruppenwertung', p),
  ],
  ['z. B. Bürger-Schützenverein']: [
    (p) => t('z. B. Bürger-Schützenverein', p),
    (p) => t('z. B. Nachbarverein', p),
  ],
  ['Schießliste nach Zug']: [
    (p) => t('Schießliste nach Zug', p),
    (p) => t('Startliste nach Untereinheit', p),
  ],
  ['Je Zug eine Tabelle mit Feldern für die Zugwertung']: [
    (p) => t('Je Zug eine Tabelle mit Feldern für die Zugwertung', p),
    (p) => t('Je Untereinheit eine Tabelle mit Feldern für die Gruppenwertung', p),
  ],
} satisfies Record<string, Pair>

export type SportKey = keyof typeof WORDS
/** alle Schlüssel, für die Prüfung der neutralen Fassung */
export const SPORT_KEYS = Object.keys(WORDS) as SportKey[]
export type SportText = (key: SportKey, params?: Params) => string

/** Text aus der Tabelle oben; `shooting`: Modul Schießsport ist eingeschaltet. */
export function sportText(shooting: boolean): SportText {
  return (key, params) => {
    return WORDS[key][shooting ? 0 : 1](params)
  }
}

/** Für die gewählte Einheit. Ohne Einheit (z. B. Live-Anzeige) die Begriffe der Schützen. */
export function useSportText(): SportText {
  const active = useOptionalOrg()?.active
  return sportText(active ? active.modules.includes('shooting') : true)
}
