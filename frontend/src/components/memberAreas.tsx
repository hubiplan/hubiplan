// Sicht „Mein Verein“ (Konzept Web-Oberfläche W3): Mitglieder sehen vier Bereiche wie in den
// Apps, Start, Termine, Neues und Ich, statt der Gliederung der Verwaltung. Die Seiten bleiben
// dieselben wie unter „Mein Bereich“; hier steht nur, in welchem Bereich sie erscheinen.
import type { ReactNode } from 'react'
import type { PortalEntry } from '../api/portal.ts'
import { portalNav } from '../pages/portal/sections.ts'
import { t } from '../i18n/index.ts'

export interface MemberArea {
  id: 'start' | 'termine' | 'neues' | 'ich'
  label: string
  icon: ReactNode
  links: { to: string; label: string }[]
}

/** Seiten, die Neuigkeiten des Vereins zeigen (Bereich „Neues“) */
const NEWS = ['/mein-bereich/pinnwand', '/mein-bereich/rundschreiben']

const icon = (d: string) => (
  <svg
    viewBox="0 0 24 24"
    width="20"
    height="20"
    aria-hidden="true"
    fill="none"
    stroke="currentColor"
    strokeWidth="2"
    strokeLinecap="round"
    strokeLinejoin="round"
  >
    <path d={d} />
  </svg>
)

/** Bereiche der Sicht „Mein Verein“ für den Zugang eines Mitglieds; leere Bereiche fehlen. */
export function memberAreas(entry: PortalEntry, documents: boolean): MemberArea[] {
  const sections = portalNav(entry)
  const areas: MemberArea[] = [
    {
      id: 'start',
      label: t('Start'),
      icon: icon('M4 11 12 4l8 7M6 9.5V20h12V9.5M10 20v-5h4v5'),
      links: [{ to: '/', label: t('Startseite') }],
    },
    {
      id: 'termine',
      label: t('Termine'),
      icon: icon('M4 6.5h16v13.5H4zM4 10.5h16M8.5 4v4M15.5 4v4M8 14h2M14 14h2M8 17h2'),
      links: entry.events_enabled ? [{ to: '/termine', label: t('Termine') }] : [],
    },
    {
      id: 'neues',
      label: t('Neues'),
      icon: icon('M4 4h16v13H4zM8 21l4-4 4 4M8 8.5h8M8 12h5'),
      links: sections.filter((s) => NEWS.includes(s.to)),
    },
    {
      id: 'ich',
      label: t('Ich'),
      icon: icon('M12 4a4 4 0 1 1 0 8 4 4 0 0 1 0-8M4.5 21c.4-4 3.6-6.5 7.5-6.5s7.1 2.5 7.5 6.5'),
      links: [
        ...sections.filter((s) => !NEWS.includes(s.to)),
        ...(documents ? [{ to: '/dokumente', label: t('Dokumente') }] : []),
      ],
    },
  ]
  return areas.filter((a) => a.links.length > 0)
}

/** Bereich der aktuellen Seite: der mit dem längsten passenden Pfad. */
export function currentMemberArea(areas: MemberArea[], pathname: string): MemberArea | null {
  let best: { area: MemberArea; length: number } | null = null
  for (const area of areas)
    for (const l of area.links) {
      const hit =
        l.to === '/' ? pathname === '/' : pathname === l.to || pathname.startsWith(`${l.to}/`)
      if (hit && (!best || l.to.length > best.length)) best = { area, length: l.to.length }
    }
  return best?.area ?? null
}
