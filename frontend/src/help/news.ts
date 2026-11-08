// Hilfe › Neuigkeiten: Überblick nach Monaten (help/neuigkeiten/<sprache>.md), darunter das
// Änderungsprotokoll je Version (konzepte/hilfe-neustruktur.md, HN2).
//
// Aufbau der Datei: einleitende Absätze, dann je Monat eine Zeile „November 2026:“ mit den
// Punkten darunter, der neueste Monat oben.
import type { Lang } from '../i18n/index.ts'

export interface NewsMonth {
  title: string
  body: string
}

export interface MonthlyNews {
  intro: string
  months: NewsMonth[]
}

/** Wie viele Monate aufgeklappt erscheinen; ältere sind zugeklappt. */
export const OPEN_MONTHS = 3

const MONTH_LINE = /^(\S.*\d{4}):\s*$/

export function parseNews(raw: string): MonthlyNews {
  const lines = raw.replace(/\r\n/g, '\n').split('\n')
  const intro: string[] = []
  const months: NewsMonth[] = []
  for (const line of lines) {
    const m = MONTH_LINE.exec(line)
    if (m) months.push({ title: m[1], body: '' })
    else if (months.length) months[months.length - 1].body += `${line}\n`
    else intro.push(line)
  }
  return {
    intro: intro.join('\n').trim(),
    months: months.map((m) => ({ ...m, body: m.body.trim() })),
  }
}

type Loader = () => Promise<string>
const FILES = import.meta.glob('./neuigkeiten/*.md', {
  query: '?raw',
  import: 'default',
}) as Record<string, Loader>

/** Überblick der Sprache (fehlt er, der deutsche). */
export async function loadNews(language: Lang): Promise<MonthlyNews> {
  const load = FILES[`./neuigkeiten/${language}.md`] ?? FILES['./neuigkeiten/de.md']
  return parseNews(await load())
}
