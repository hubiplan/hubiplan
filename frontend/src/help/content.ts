// Hilfe: Anleitungen und Seitenhilfen (konzepte/hilfe-funktion.md, docs/hilfe.md).
//
// Jeder Eintrag ist eine Markdown-Datei je Sprache unter ./de und ./en mit gleichem
// Dateinamen. Oben steht ein Kopf zwischen zwei Zeilen „---“:
//
//   key: guide.password          eindeutiger Schlüssel (guide.… oder page.…)
//   titel: Passwort ändern
//
// Wo ein Eintrag in der Hilfe steht (Gruppe und Menüpunkt), folgt aus der Route und der
// Seitenleiste (help/menu.ts), nicht aus einem eigenen Feld (konzepte/hilfe-neustruktur.md).
//   reihe: 10                    optional: Reihenfolge im Menüpunkt (Ablauf), sonst nach Titel
//   menue: /mein-konto           optional: Menüpunkt, wenn nicht die erste Route gilt
//   modul: members               nur, wenn das Modul freigeschaltet ist (leer: immer)
//   rechte: [members.edit]       eines davon nötig (leer: alle Angemeldeten)
//   routen: [/mein-konto/anmeldung]
//   stichworte: [Kennwort, Login]
//   siehe: [guide.fee_run]       nur Seitenhilfen: verwandte Anleitungen anderer Seiten
//
// Seitenhilfen (Ordner seiten/) gehören zu ihren Routen; Anleitungen (anleitungen/)
// erscheinen auf diesen Routen als „Häufige Aufgaben“. Bilder: ![Text](bild:name),
// erzeugt von scripts/hilfe-bilder.sh nach src/help/bilder.json.
import type { Lang } from '../i18n/index.ts'
import { variants } from './synonyms.ts'

export type HelpKind = 'guide' | 'page'

export interface HelpEntry {
  key: string
  kind: HelpKind
  file: string
  /** Adresse unter /hilfe/, z. B. „passwort-aendern“ oder „seite/mein-konto“ */
  slug: string
  title: string
  /** Reihenfolge innerhalb des Menüpunkts (kleiner zuerst); ohne Angabe nach Titel */
  order?: number
  /** Menüpunkt, falls nicht die erste Route (z. B. /mein-konto) */
  menu?: string
  module?: string
  rights: string[]
  routes: string[]
  keywords: string[]
  /** Seitenhilfe: Schlüssel verwandter Anleitungen, die nicht zur selben Route gehören */
  see: string[]
  body: string
}

const LIST_FIELDS = new Set(['rechte', 'routen', 'stichworte', 'siehe'])
const KNOWN_FIELDS = new Set(['key', 'titel', 'modul', 'reihe', 'menue', ...LIST_FIELDS])

/** Kopf und Text einer Hilfedatei lesen. Wirft bei Formfehlern (Test prüft alle Dateien). */
export function parseHelpFile(file: string, raw: string): HelpEntry {
  const m = /^---\n([\s\S]*?)\n---\n?([\s\S]*)$/.exec(raw.replace(/\r\n/g, '\n'))
  if (!m) throw new Error(`${file}: Kopf fehlt`)
  const meta: Record<string, string | string[]> = {}
  // Eingerückte Zeilen gehören zur Zeile davor (Prettier bricht lange Listen um)
  for (const line of m[1].replace(/\n[ \t]+/g, ' ').split('\n')) {
    if (!line.trim() || line.trim().startsWith('#')) continue
    const kv = /^([a-z]+):\s*(.*)$/.exec(line)
    if (!kv) throw new Error(`${file}: Zeile „${line}“ unverständlich`)
    const [, name, value] = kv
    if (!KNOWN_FIELDS.has(name)) throw new Error(`${file}: Feld „${name}“ unbekannt`)
    if (LIST_FIELDS.has(name)) {
      const list = /^\[(.*)\]$/.exec(value.trim())
      if (!list) throw new Error(`${file}: ${name} braucht [a, b]`)
      meta[name] = list[1]
        .split(',')
        .map((s) => s.trim())
        .filter(Boolean)
    } else meta[name] = value.trim()
  }
  const str = (k: string) => (typeof meta[k] === 'string' ? (meta[k] as string) : '')
  const list = (k: string) => (Array.isArray(meta[k]) ? (meta[k] as string[]) : [])
  const key = str('key')
  const kind: HelpKind = key.startsWith('page.') ? 'page' : 'guide'
  if (!/^(guide|page)\.[a-z0-9_]+$/.test(key)) throw new Error(`${file}: key „${key}“ ungültig`)
  if (!str('titel')) throw new Error(`${file}: titel fehlt`)
  if (str('reihe') && !/^\d+$/.test(str('reihe')))
    throw new Error(`${file}: reihe braucht eine Zahl`)
  return {
    key,
    kind,
    file,
    slug: file
      .replace(/^anleitungen\//, '')
      .replace(/^seiten\//, 'seite/')
      .replace(/\.md$/, ''),
    title: str('titel'),
    order: str('reihe') ? Number(str('reihe')) : undefined,
    menu: str('menue') || undefined,
    module: str('modul') || undefined,
    rights: list('rechte'),
    routes: list('routen'),
    keywords: list('stichworte'),
    see: list('siehe'),
    body: m[2].trim(),
  }
}

type Loader = () => Promise<string>
// Nur die gewählte Sprache wird geladen, und erst, wenn jemand die Hilfe öffnet
const FILES: Record<Lang, Record<string, Loader>> = {
  de: import.meta.glob('./de/**/*.md', { query: '?raw', import: 'default' }) as Record<
    string,
    Loader
  >,
  en: import.meta.glob('./en/**/*.md', { query: '?raw', import: 'default' }) as Record<
    string,
    Loader
  >,
}

/** Dateiname ohne Sprachordner, z. B. „anleitungen/passwort.md“ */
export const relName = (path: string) => path.replace(/^\.\/(de|en)\//, '')

const cache = new Map<Lang, Promise<HelpEntry[]>>()

/** Alle Einträge einer Sprache (fehlt eine englische Datei, gilt die deutsche). */
export function loadHelp(language: Lang): Promise<HelpEntry[]> {
  let p = cache.get(language)
  if (!p) {
    p = (async () => {
      const de = FILES.de
      const own = FILES[language]
      const byName = new Map(Object.entries(own).map(([path, load]) => [relName(path), load]))
      return Promise.all(
        Object.entries(de).map(async ([path, load]) => {
          const name = relName(path)
          const raw = await (byName.get(name) ?? load)()
          return parseHelpFile(name, raw)
        }),
      )
    })()
    cache.set(language, p)
    // Fehler nicht zwischenspeichern, beim nächsten Öffnen erneut versuchen
    p.catch(() => cache.delete(language))
  }
  return p
}

/** Darf diese Person den Eintrag sehen? Modul freigeschaltet und eines der Rechte. */
export function visibleFor(
  entry: Pick<HelpEntry, 'module' | 'rights'>,
  hasModule: (m: string) => boolean,
  hasRight: (r: string) => boolean,
): boolean {
  if (entry.module && !hasModule(entry.module)) return false
  return entry.rights.length === 0 || entry.rights.some(hasRight)
}

/** Was die Person an Arbeitsbereichen und Schaltern hat (für Einträge ohne eigenes Modul). */
export interface HelpSetting {
  /** Eigener Mitgliederbereich vorhanden oder Modul Mitgliederbereich an */
  portal: boolean
  /** Rolle in einer Untereinheit vorhanden oder Modul Mitglieder an */
  dept: boolean
  /** Menüpunkt für Untereinheiten sichtbar (Einstellungen › Bezeichnungen) */
  units: boolean
  /** Zusatzfunktion Zählprotokoll eingeschaltet */
  cashCounts: boolean
}

const under = (route: string, base: string) => route === base || route.startsWith(`${base}/`)

/**
 * Gehört der Eintrag zu einem Bereich, den es für diese Person gar nicht gibt? Hilfen zu
 * „Mein Bereich“ nur mit Mitgliederbereich, zur Abteilung nur mit Rolle dort, zu Untereinheiten
 * nur mit dem Menüpunkt, zur Kassenzählung nur mit dem Zusatz (z. B. reines Kassenbuch).
 */
export function inReach(entry: Pick<HelpEntry, 'routes'>, s: HelpSetting): boolean {
  const all = (base: string) => entry.routes.length > 0 && entry.routes.every((r) => under(r, base))
  if (all('/mein-bereich')) return s.portal
  if (all('/abteilung')) return s.dept
  if (all('/untereinheiten')) return s.units
  if (all('/finanzen/kassenzaehlung')) return s.cashCounts
  return true
}

/** Fehlende Rechte für einen Eintrag, dessen Modul freigeschaltet ist („Warum sehe ich das
 *  nicht?“). Leer, wenn der Eintrag sichtbar ist oder sein Modul fehlt. */
export function missingRights(
  entry: Pick<HelpEntry, 'module' | 'rights'>,
  hasModule: (m: string) => boolean,
  hasRight: (r: string) => boolean,
): string[] {
  if (entry.module && !hasModule(entry.module)) return []
  if (entry.rights.length === 0 || entry.rights.some(hasRight)) return []
  return entry.rights
}

/** Passt die Route zur Adresse? Gleich oder darunter (/mitglieder passt zu /mitglieder/5).
 *  „:id“ steht für eine Nummer (/mitglieder/:id passt zu /mitglieder/42, nicht zu /mitglieder/neu). */
export function routeMatches(route: string, pathname: string): boolean {
  // Die Startseite gilt nur für sich, nicht für alle Seiten darunter
  if (route === '/') return pathname === '/'
  const want = route.replace(/\/$/, '').split('/')
  const have = pathname.replace(/\/$/, '').split('/')
  if (have.length < want.length) return false
  return want.every((seg, i) => (seg === ':id' ? /^\d+$/.test(have[i]) : seg === have[i]))
}

/** Seitenhilfe zur Adresse: die Route mit dem längsten Treffer gewinnt. */
export function pageHelpFor(entries: HelpEntry[], pathname: string): HelpEntry | null {
  let best: HelpEntry | null = null
  let len = -1
  for (const e of entries) {
    if (e.kind !== 'page') continue
    for (const r of e.routes)
      if (routeMatches(r, pathname) && r.length > len) {
        best = e
        len = r.length
      }
  }
  return best
}

/** Anleitungen für die Seite (genau diese Route oder eine darüber). */
export function guidesFor(entries: HelpEntry[], pathname: string): HelpEntry[] {
  return entries.filter(
    (e) => e.kind === 'guide' && e.routes.some((r) => routeMatches(r, pathname)),
  )
}

/** Anleitungen einer Seitenhilfe: die der Route, dann die unter `siehe` genannten. */
export function guidesOfPage(
  entries: HelpEntry[],
  page: Pick<HelpEntry, 'see'> | null,
  routeGuides: HelpEntry[],
): HelpEntry[] {
  if (!page?.see.length) return routeGuides
  const have = new Set(routeGuides.map((g) => g.key))
  const more = page.see
    .map((key) => entries.find((e) => e.kind === 'guide' && e.key === key))
    .filter((e): e is HelpEntry => !!e && !have.has(e.key))
  return [...routeGuides, ...more]
}

const queryWords = (query: string) => query.toLocaleLowerCase().split(/\s+/).filter(Boolean)
const haystack = (texts: (string | undefined)[]) =>
  texts.filter(Boolean).join(' ').toLocaleLowerCase()
const hasWord = (hay: string, word: string) => variants(word).some((v) => hay.includes(v))

/** Alle Wörter der Suche müssen vorkommen (Groß-/Kleinschreibung egal); gleichbedeutende
 *  Wörter zählen mit (help/synonyms.ts: „Homepage“ findet „Webseite“). */
export function matchesQuery(query: string, ...texts: (string | undefined)[]): boolean {
  const words = queryWords(query)
  if (!words.length) return true
  const hay = haystack(texts)
  return words.every((w) => hasWord(hay, w))
}

/** Wie matchesQuery, aber nur die getippten Wörter selbst (für die Reihenfolge der Treffer). */
export function matchesLiteral(query: string, ...texts: (string | undefined)[]): boolean {
  const hay = haystack(texts)
  return queryWords(query).every((w) => hay.includes(w))
}

/** Bei mehreren Suchwörtern: Welches eine Wort fehlt, wenn alle anderen vorkommen?
 *  null, wenn alle passen, mehr als eines fehlt oder nur ein Wort gesucht wird. */
export function missingWord(query: string, ...texts: (string | undefined)[]): string | null {
  const words = queryWords(query)
  if (words.length < 2) return null
  const hay = haystack(texts)
  const missing = words.filter((w) => !hasWord(hay, w))
  return missing.length === 1 ? missing[0] : null
}

/** Bilder im Text: bild:name → Datei der Sprache. */
export const IMAGE_PREFIX = 'bild:'
export const imageUrl = (name: string, language: Lang) => `/hilfe-bilder/${language}/${name}.png`

/** Namen aller Bilder in einem Text */
export function imagesIn(body: string): string[] {
  return [...body.matchAll(/!\[[^\]]*\]\(bild:([a-z0-9-]+)\)/g)].map((m) => m[1])
}
