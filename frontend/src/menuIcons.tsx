// Zusätzliche Zeichen für eigene Hauptmenüpunkte (Menü frei anordnen). Die Kennungen stehen
// auch in backend/organizations/menu_standard.json ("icons"), damit das Backend sie annimmt.
import type { ReactNode } from 'react'
import { t } from './i18n/index.ts'

export const svgIcon = (d: string): ReactNode => (
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

export interface ExtraIcon {
  id: string
  label: string
  path: string
}

/** Kennungen beginnen mit „z-“, damit sie nie mit einem Bereich oder Menüpunkt kollidieren */
export const EXTRA_ICONS: ExtraIcon[] = [
  {
    id: 'z-stern',
    label: t('Stern'),
    path: 'M12 3.5l2.6 5.3 5.9.9-4.25 4.1 1 5.8L12 16.9l-5.25 2.7 1-5.8L3.5 9.7l5.9-.9z',
  },
  { id: 'z-fahne', label: t('Fahne'), path: 'M5 21V4M5 4h12l-2.5 4 2.5 4H5' },
  {
    id: 'z-zielscheibe',
    label: t('Zielscheibe'),
    path: 'M12 3a9 9 0 1 1 0 18 9 9 0 0 1 0-18M12 7.5a4.5 4.5 0 1 1 0 9 4.5 4.5 0 0 1 0-9M12 11a1 1 0 1 1 0 2 1 1 0 0 1 0-2',
  },
  {
    id: 'z-note',
    label: t('Note'),
    path: 'M9 18V5.5l11-2V16M9 9.5l11-2M6.5 15.5a2.5 2.5 0 1 1 0 5 2.5 2.5 0 0 1 0-5M17.5 13.5a2.5 2.5 0 1 1 0 5 2.5 2.5 0 0 1 0-5',
  },
  {
    id: 'z-herz',
    label: t('Herz'),
    path: 'M12 20s-7.5-4.6-7.5-10A4.3 4.3 0 0 1 12 7.3 4.3 4.3 0 0 1 19.5 10c0 5.4-7.5 10-7.5 10',
  },
  {
    id: 'z-kamera',
    label: t('Kamera'),
    path: 'M3 8h4l2-3h6l2 3h4v11H3zM12 10a3.5 3.5 0 1 1 0 7 3.5 3.5 0 0 1 0-7',
  },
  {
    id: 'z-buch',
    label: t('Buch'),
    path: 'M4 5.5h6a2 2 0 0 1 2 2V20a2 2 0 0 0-2-2H4zM20 5.5h-6a2 2 0 0 0-2 2V20a2 2 0 0 1 2-2h6z',
  },
  {
    id: 'z-glocke',
    label: t('Glocke'),
    path: 'M6 16V11a6 6 0 0 1 12 0v5l1.5 2h-15zM10 20.5h4',
  },
  { id: 'z-blitz', label: t('Blitz'), path: 'M13 3 5 13.5h6L10 21l8-10.5h-6z' },
  {
    id: 'z-blatt',
    label: t('Blatt'),
    path: 'M5 19c0-8 5-13 14-14 0 9-5 14-13 14M5 19l7-7',
  },
  {
    id: 'z-schild',
    label: t('Wappen'),
    path: 'M12 3l8 3v5.5c0 5-3.5 8.3-8 9.5-4.5-1.2-8-4.5-8-9.5V6zM12 3v18M4 11h16',
  },
  { id: 'z-krone', label: t('Krone'), path: 'M4 8l4 4 4-6 4 6 4-4-1.5 10h-13zM5.5 20.5h13' },
  {
    id: 'z-ball',
    label: t('Ball'),
    path: 'M12 3a9 9 0 1 1 0 18 9 9 0 0 1 0-18M12 7.5l3.5 2.5-1.3 4h-4.4l-1.3-4zM12 3v4.5M15.5 10l5-1.5M14.2 14l3 4.5M9.8 14l-3 4.5M8.5 10l-5-1.5',
  },
  {
    id: 'z-kompass',
    label: t('Kompass'),
    path: 'M12 3a9 9 0 1 1 0 18 9 9 0 0 1 0-18M15.5 8.5l-2 5-5 2 2-5z',
  },
  {
    id: 'z-werkzeug',
    label: t('Werkzeug'),
    path: 'M14.5 6.5a4 4 0 0 1 5-1.5l-2.5 2.5.5 2 2 .5 2.5-2.5a4 4 0 0 1-5.5 5L8 20.5a2 2 0 0 1-3-3l7.5-8.5a4 4 0 0 1 2-2.5',
  },
  {
    id: 'z-geschenk',
    label: t('Geschenk'),
    path: 'M4 9h16v4H4zM5.5 13h13v8h-13zM12 9v12M12 9c-1-3-5-4-5-1.5S10.5 9 12 9M12 9c1-3 5-4 5-1.5S13.5 9 12 9',
  },
  {
    id: 'z-sonne',
    label: t('Sonne'),
    path: 'M12 8a4 4 0 1 1 0 8 4 4 0 0 1 0-8M12 2.5v2M12 19.5v2M2.5 12h2M19.5 12h2M5.3 5.3l1.4 1.4M17.3 17.3l1.4 1.4M5.3 18.7l1.4-1.4M17.3 6.7l1.4-1.4',
  },
  {
    id: 'z-zelt',
    label: t('Zelt'),
    path: 'M3 20 12 4l9 16zM12 4v16M9 20l3-6 3 6',
  },
  {
    id: 'z-tasse',
    label: t('Tasse'),
    path: 'M5 9h11v6a4 4 0 0 1-4 4H9a4 4 0 0 1-4-4zM16 10.5h1.5a2.5 2.5 0 0 1 0 5H16M8 3.5v2.5M11 3.5v2.5',
  },
  {
    id: 'z-gluehbirne',
    label: t('Glühbirne'),
    path: 'M9 17.5h6M10 21h4M12 3a6 6 0 0 1 3.5 10.9c-.6.5-.9 1-.9 1.6v2h-5.2v-2c0-.6-.3-1.1-.9-1.6A6 6 0 0 1 12 3',
  },
  {
    id: 'z-paket',
    label: t('Paket'),
    path: 'M12 3 20.5 7.5v9L12 21l-8.5-4.5v-9zM3.5 7.5 12 12l8.5-4.5M12 12v9M7.75 5.25l8.5 4.5',
  },
  {
    id: 'z-landkarte',
    label: t('Landkarte'),
    path: 'M3 6l6-2.5 6 2.5 6-2.5v14.5l-6 2.5-6-2.5-6 2.5zM9 3.5v14.5M15 6v14.5',
  },
]
