// Module der linken Navigation. Welche erscheinen, hängt von der aktiven
// Organisation ab: freigeschaltete Module und Berechtigungen der Rolle.
import type { ReactNode } from 'react'
import { PERM } from './api/orgs.ts'
import type { OrgSummary } from './api/orgs.ts'
import type { DeptSummary, PortalEntry } from './api/portal.ts'
import { financeAccess, financeSections } from './pages/finanzen/access.ts'
import { memberSections, membersVisible } from './pages/members/access.ts'
import { websiteSections } from './pages/website/sections.ts'
import { circularsVisible } from './pages/circulars/access.ts'
import { portalNav } from './pages/portal/sections.ts'
import { departmentSections } from './pages/department/sections.ts'
import { musicSections, scoresOwnEntry } from './pages/music/access.ts'
import { hasUnitsPage } from './pages/settings/units.ts'
import { settingsItems } from './pages/settings/items.ts'
import { partnerAccess } from './pages/partners/access.ts'
import { t } from './i18n/index.ts'
import type { SubNavItem } from './components/subnav.ts'

export interface Workspace {
  dept: DeptSummary | null
  portal: PortalEntry | null
}

export interface AppModule {
  id: string
  group: 'alltag' | 'planen' | 'verein' | 'vereinsleben' | 'kommunikation' | 'verwaltung'
  label: string
  /** Bezeichnung je Einheit, z. B. „Züge“ statt „Untereinheiten“ */
  labelFor?: (org: OrgSummary | null, ws?: Workspace) => string
  path: string
  /** Weitere Pfade, unter denen der Menüpunkt als aktiv gilt */
  also?: string[]
  /** Ziel des Menüpunkts, wenn es nicht immer path ist */
  linkFor?: (org: OrgSummary | null, ws: Workspace) => string
  icon: ReactNode
  visible: (org: OrgSummary | null, ws: Workspace) => boolean
  /** Unterpunkte, in der Seitenleiste unter dem aktiven Modul */
  children?: (org: OrgSummary | null, ws?: Workspace) => SubNavItem[]
}

const NO_WS: Workspace = { dept: null, portal: null }

function partnersVisible(org: OrgSummary | null): boolean {
  return (
    !!org &&
    (org.type === 'club' || org.type === 'federation' || org.type === 'unit') &&
    partnerAccess(org.permissions).view
  )
}

function competitionsVisible(org: OrgSummary | null): boolean {
  return (
    !!org &&
    (org.type === 'club' || org.type === 'federation') &&
    org.modules.includes('competitions') &&
    [
      PERM.competitionsView,
      PERM.resultsView,
      PERM.competitionsManage,
      PERM.competitionsResults,
    ].some((p) => org.permissions.includes(p))
  )
}

function entriesVisible(org: OrgSummary | null): boolean {
  return (
    !!org &&
    (org.type === 'club' || org.type === 'federation') &&
    (org.modules.includes('entries') || org.modules.includes('calls')) &&
    [PERM.entriesView, PERM.callsView, PERM.entriesSubmit, PERM.entriesManage].some((p) =>
      org.permissions.includes(p),
    )
  )
}

/** Welche Teile von Material & Räume die Person sieht (Organisation oder Abteilung). */
function stockAccess(org: OrgSummary | null, ws: Workspace) {
  const perms = org ? org.permissions : (ws.dept?.permissions ?? [])
  const materialOn = org ? org.modules.includes('material') : !!ws.dept?.material_enabled
  const facilityOn = org
    ? org.modules.includes('infrastructure')
    : !!ws.dept?.infrastructure_enabled
  const material = materialOn && perms.includes('material.view')
  const facility = facilityOn && perms.includes('infrastructure.view')
  // Belegung ist ein eigenes Modul (module-neustruktur, M2a)
  const bookingsOn = org ? org.modules.includes('bookings') : ws.dept?.bookings_enabled !== false
  const bookingsAllowed =
    bookingsOn && (org ? org.type === 'club' || org.type === 'federation' : !!ws.dept)
  const bookings =
    bookingsAllowed &&
    ((materialOn && (perms.includes('material.view') || perms.includes('bookings.view'))) ||
      (facilityOn && (perms.includes('infrastructure.view') || perms.includes('bookings.view'))))
  return { material, facility, bookings }
}

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

/** Benannte Gruppen der Seitenleiste (UX-Audit S-02, Gestalt: gemeinsame Region) */
export const GROUP_LABELS: Record<AppModule['group'], string> = {
  alltag: t('Alltag'),
  planen: t('Planen'),
  verein: t('Verein'),
  vereinsleben: t('Vereinsleben'),
  kommunikation: t('Kommunikation'),
  verwaltung: t('Verwaltung'),
}

export const modules: AppModule[] = [
  {
    id: 'start',
    group: 'alltag',
    label: t('Startseite'),
    path: '/',
    icon: icon('M4 11 12 4l8 7M6 9.5V20h12V9.5M10 20v-5h4v5M16 7.5V4.5h2.5v5.2'),
    visible: () => true,
  },
  // Persönlicher Bereich gehört zum Alltag, nicht zum Verein (Menüprüfung M-20)
  {
    id: 'mein-bereich',
    group: 'alltag',
    label: t('Mein Bereich'),
    path: '/mein-bereich',
    icon: icon('M12 4a4 4 0 1 1 0 8 4 4 0 0 1 0-8M4.5 21c.4-4 3.6-6.5 7.5-6.5s7.1 2.5 7.5 6.5'),
    visible: (_org, ws) => !!ws.portal,
    children: (_org, ws) => portalNav(ws?.portal ?? null),
  },
  // Planen: Termine und was daran hängt (Menüprüfung 2, N-01)
  {
    id: 'termine',
    group: 'planen',
    label: t('Termine'),
    path: '/termine',
    icon: icon('M4 6.5h16v13.5H4zM4 10.5h16M8.5 4v4M15.5 4v4M8 14h2M14 14h2M8 17h2'),
    visible: (org, ws) =>
      org
        ? (org.type === 'club' || org.type === 'federation') &&
          org.modules.includes('events') &&
          org.permissions.includes(PERM.eventsView)
        : !!(
            (ws.dept?.events_enabled && ws.dept.permissions.includes(PERM.eventsView)) ||
            ws.portal?.events_enabled
          ),
  },
  {
    id: 'versammlungen',
    group: 'planen',
    label: t('Versammlungen'),
    path: '/versammlungen',
    icon: icon('M4 20h16M6 20v-6h12v6M9 14V9.5M15 14V9.5M12 4a2.5 2.5 0 1 1 0 5 2.5 2.5 0 0 1 0-5'),
    visible: (org, ws) =>
      org
        ? (org.type === 'club' || org.type === 'federation') &&
          org.modules.includes('meetings') &&
          org.permissions.includes(PERM.meetingsView)
        : !!(ws.dept?.meetings_enabled && ws.dept.permissions.includes(PERM.meetingsView)),
  },
  // Training und Anwesenheit, mit Schießsport auch Schießbuch (Lückenliste 20.11., B1)
  {
    id: 'training',
    group: 'planen',
    label: t('Training'),
    path: '/training',
    icon: icon('M4 20h16M6 20V9l6-5 6 5v11M10 20v-5h4v5M9.5 11.5l1.5 1.5 3-3'),
    visible: (org, ws) =>
      org
        ? org.type === 'club' &&
          org.modules.includes('training') &&
          (org.permissions.includes(PERM.trainingView) ||
            org.permissions.includes(PERM.trainingEdit))
        : !!(
            ws.dept?.training_enabled &&
            (ws.dept.permissions.includes(PERM.trainingView) ||
              ws.dept.permissions.includes(PERM.trainingEdit))
          ),
  },
  {
    id: 'helferdienste',
    group: 'planen',
    label: t('Helferdienste'),
    path: '/helferdienste',
    icon: icon(
      'M8 7a3 3 0 1 0 0-.01M16 7a3 3 0 1 0 0-.01M3 20v-2a5 5 0 0 1 10 0v2M11 20v-2a5 5 0 0 1 10 0v2',
    ),
    visible: (org, ws) =>
      org
        ? (org.type === 'club' || org.type === 'federation') &&
          org.modules.includes('helpers') &&
          org.permissions.includes(PERM.helpersView)
        : !!(ws.dept?.helpers_enabled && ws.dept.permissions.includes(PERM.helpersView)),
  },
  {
    id: 'aufgaben',
    group: 'planen',
    label: t('Aufgaben'),
    path: '/aufgaben',
    icon: icon('M4 5h16v15H4zM8 12l3 3 5-7'),
    visible: (org, ws) =>
      !!(org?.permissions.includes('todos.view') || ws.dept?.permissions.includes('todos.view')),
  },
  {
    id: 'fristenkalender',
    group: 'planen',
    label: t('Fristenkalender'),
    path: '/fristenkalender',
    icon: icon('M4 6.5h16v13.5H4zM4 10.5h16M8.5 4v4M15.5 4v4M12 13v3.5M12 18.4v.1'),
    visible: (org) =>
      !!org &&
      (org.type === 'club' || org.type === 'federation') &&
      org.modules.includes('obligations') &&
      org.permissions.includes(PERM.obligationsView),
  },
  {
    id: 'mitglieder',
    group: 'verein',
    label: t('Mitglieder'),
    path: '/mitglieder',
    icon: icon(
      'M9 4.5a3.5 3.5 0 1 1 0 7 3.5 3.5 0 0 1 0-7M2.5 20c0-3.6 2.9-6 6.5-6s6.5 2.4 6.5 6M15.5 5.2a3 3 0 1 1 1.2 5.6M17.5 14.2c2.4.5 4 2.6 4 5.8',
    ),
    visible: membersVisible,
    children: memberSections,
  },
  {
    // Untereinheiten (z. B. Züge), benannt nach der Bezeichnung der Einheit
    id: 'untereinheiten',
    group: 'verein',
    label: t('Untereinheiten'),
    labelFor: (org) =>
      org?.department_terms?.pl || org?.department_label_plural || t('Untereinheiten'),
    path: '/untereinheiten',
    icon: icon(
      'M12 3.5v5M12 8.5H6v4M12 8.5h6v4M3.5 12.5h5v4h-5zM9.5 12.5h5v4h-5zM15.5 12.5h5v4h-5zM9.5 17.5v3h5v-3',
    ),
    visible: (org) => !!org && hasUnitsPage(org, (perm) => org.permissions.includes(perm)),
  },
  {
    id: 'abteilung',
    group: 'verein',
    label: t('Abteilung'),
    path: '/abteilung',
    icon: icon(
      'M12 6.5a2.5 2.5 0 1 1 0 5 2.5 2.5 0 0 1 0-5M5 9a2 2 0 1 1 0 4 2 2 0 0 1 0-4M19 9a2 2 0 1 1 0 4 2 2 0 0 1 0-4M7 20c0-2.8 2.2-5 5-5s5 2.2 5 5M2 19c0-2 1.3-3.5 3-3.8M22 19c0-2-1.3-3.5-3-3.8',
    ),
    visible: (_org, ws) => !!ws.dept,
    children: (_org, ws) => {
      const items = departmentSections(ws?.dept ?? null)
      return items.length > 1 ? items : []
    },
  },
  {
    id: 'chronik',
    group: 'verein',
    label: t('Chronik'),
    path: '/chronik',
    icon: icon('M4 5h11a3 3 0 0 1 3 3v12H7a3 3 0 0 1-3-3zM18 8h2v12M8 9h6M8 13h6'),
    visible: (org) =>
      !!org &&
      (org.type === 'club' || org.type === 'federation') &&
      org.modules.includes('chronicle') &&
      org.permissions.includes(PERM.chronicleView),
  },
  // Vereinsleben: was der Verein tut (Wettbewerbe mit Meldungen, Musik), getrennt von
  // „Verein“ mit Mitgliedern, Gliederung und Chronik (Menüprüfung 3)
  {
    id: 'wettbewerbe',
    group: 'vereinsleben',
    label: t('Wettbewerbe'),
    path: '/wettbewerbe',
    icon: icon(
      'M8 4h8v5a4 4 0 0 1-8 0zM8 6H5a3 3 0 0 0 3 4M16 6h3a3 3 0 0 1-3 4M12 13v4M8.5 20h7M10 17h4v3h-4z',
    ),
    // Meldungen stehen als Unterpunkt hier, solange es den Menüpunkt Wettbewerbe gibt (VW-33)
    also: ['/meldungen'],
    visible: competitionsVisible,
    children: (org) => [
      { to: '/wettbewerbe', label: t('Wettbewerbe') },
      { to: '/wettbewerbe/statistik', label: t('Statistik') },
      { to: '/wettbewerbe/reihen', label: t('Reihen') },
      { to: '/wettbewerbe/pokale', label: t('Wanderpokale') },
      { to: '/wettbewerbe/titel', label: t('Titel und Sieger') },
      { to: '/wettbewerbe/urkunden', label: t('Urkundenvorlagen') },
      ...(entriesVisible(org) ? [{ to: '/meldungen', label: t('Meldungen') }] : []),
      // Modul-Einstellungen heißen überall „Einrichtung“ und stehen zuletzt (docs/begriffe.md)
      { to: '/wettbewerbe/einrichtung', label: t('Einrichtung') },
    ],
  },
  {
    id: 'meldungen',
    group: 'vereinsleben',
    label: t('Meldungen'),
    path: '/meldungen',
    icon: icon('M5 4h10l4 4v12H5zM15 4v4h4M8.5 12.5l2 2 4-4.5M8.5 17.5h7'),
    // Eigener Menüpunkt nur ohne Wettbewerbe; sonst Unterpunkt dort (VW-33)
    visible: (org) => entriesVisible(org) && !competitionsVisible(org),
  },
  {
    id: 'musik',
    group: 'vereinsleben',
    label: t('Musik'),
    path: '/musik',
    icon: icon('M9 18V5l11-2v13M9 8l11-2M9 18a3 3 0 1 1-3-3M20 16a3 3 0 1 1-3-3'),
    visible: (org) => !!org?.modules.includes('music') && org.permissions.includes('music.view'),
    children: musicSections,
  },
  {
    id: 'noten',
    group: 'vereinsleben',
    label: t('Noten'),
    path: '/noten',
    // Notenblatt, damit sich Noten von Musik unterscheiden (Menüprüfung 2, N-13)
    icon: icon('M6 3h9l3 3v15H6zM15 3v3h3M11 17v-7l4-1M11 17a2 2 0 1 1-2-2'),
    visible: (org) => scoresOwnEntry(org),
  },
  {
    id: 'rundschreiben',
    group: 'kommunikation',
    label: t('Rundschreiben'),
    path: '/rundschreiben',
    icon: icon('M3 6h18v12H3zM3 6l9 7 9-7'),
    visible: (org, ws) => circularsVisible(org, ws.dept),
  },
  // Umfragen und Meinungsbilder fragen die Mitglieder: Austausch, keine Planung (Menüprüfung 3)
  {
    id: 'umfragen',
    group: 'kommunikation',
    label: t('Umfragen'),
    path: '/umfragen',
    icon: icon('M5 4h14v16H5zM8.5 8.5h7M8.5 12h7M8.5 15.5h4'),
    visible: (org, ws) =>
      org
        ? org.type === 'club' &&
          org.modules.includes('surveys') &&
          org.permissions.includes(PERM.surveysView)
        : !!(ws.dept?.surveys_enabled && ws.dept.permissions.includes(PERM.surveysView)),
  },
  // Pinnwand: kurze Neuigkeiten an die Mitglieder (Lückenliste 20.11., A3)
  {
    id: 'pinnwand',
    group: 'kommunikation',
    label: t('Pinnwand'),
    path: '/pinnwand',
    icon: icon('M4 4h16v13H4zM8 21l4-4 4 4M8 8.5h8M8 12h5'),
    visible: (org, ws) =>
      org
        ? org.type === 'club' &&
          org.modules.includes('pinboard') &&
          (org.permissions.includes(PERM.pinboardView) ||
            org.permissions.includes(PERM.pinboardEdit))
        : !!(
            ws.dept?.pinboard_enabled &&
            (ws.dept.permissions.includes(PERM.pinboardView) ||
              ws.dept.permissions.includes(PERM.pinboardEdit))
          ),
  },
  {
    id: 'dokumente',
    group: 'kommunikation',
    label: t('Dokumente'),
    path: '/dokumente',
    icon: icon('M6 3h8.5L19 7.5V21H6zM14.5 3v4.5H19M9 12h7M9 15.5h7M9 19h4'),
    visible: (org, ws) =>
      org
        ? (org.type === 'club' || org.type === 'federation') &&
          org.permissions.includes(PERM.docsView)
        : !!(
            ws.dept?.permissions.includes(PERM.docsView) ||
            (ws.portal && ws.portal.docs_enabled !== false)
          ),
  },
  {
    id: 'webseite',
    group: 'kommunikation',
    label: t('Webseite'),
    path: '/webseite',
    icon: icon('M3 5h18v14H3zM3 9h18M6 7h.01M8.5 7h.01M7 13h6M7 16h10'),
    visible: (org) =>
      !!org &&
      (org.type === 'club' || org.type === 'federation' || org.type === 'unit') &&
      org.modules.includes('website') &&
      [PERM.webcontentView, PERM.websiteView, PERM.websiteManage, PERM.websiteContent].some((p) =>
        org.permissions.includes(p),
      ),
    children: websiteSections,
  },
  // Untereinheit: Auslagen sachlich bestätigen; im Verein unter Finanzen › Auslagen
  {
    id: 'auslagen',
    group: 'verwaltung',
    label: t('Auslagen'),
    path: '/auslagen',
    icon: icon('M4 4h12l4 4v12H4zM8 12h8M8 16h5M12 6v4'),
    visible: (org, ws) =>
      !org && !!(ws.dept?.expenses_enabled && ws.dept.permissions.includes(PERM.expensesView)),
  },
  {
    id: 'finanzen',
    group: 'verwaltung',
    label: t('Finanzen'),
    path: '/finanzen',
    icon: icon('M3 6h18v12H3zM3 10h18M7 14.5h4'),
    visible: (org) => financeSections(financeAccess(org)).length > 0,
    children: (org) => financeSections(financeAccess(org)),
  },
  // Geschäftspartner (konzepte/geschaeftspartner.md): eigener Menüpunkt, ohne Modul (GP-2).
  // Außenkontakte von Kasse und Rechnungen: Verwaltung, direkt nach Finanzen (Menüprüfung 3)
  {
    id: 'geschaeftspartner',
    group: 'verwaltung',
    label: t('Geschäftspartner'),
    path: '/geschaeftspartner',
    icon: icon('M3 8h18v12H3zM8 8V5h8v3M3 13h18M11 12h2v3h-2z'),
    visible: (org) => partnersVisible(org),
  },
  // Datenschutz-Werkzeuge (Lückenliste 20.11.2026, B5): Pflicht jedes Vereins, kein Modul
  {
    id: 'dsgvo',
    group: 'verwaltung',
    label: t('DSGVO'),
    path: '/dsgvo',
    icon: icon('M12 3l7 3v5c0 4.5-3 8.5-7 10-4-1.5-7-5.5-7-10V6zM9.5 12l2 2 3.5-4'),
    visible: (org) =>
      !!org &&
      (org.type === 'club' || org.type === 'federation') &&
      org.permissions.includes(PERM.privacyView),
  },
  {
    // Material, Räume und Anlagen und Belegung: ein Ablauf, ein Menüpunkt (Menüprüfung M-02)
    id: 'material',
    group: 'verwaltung',
    label: t('Material & Räume'),
    labelFor: (org, ws) => {
      const s = stockAccess(org, ws ?? NO_WS)
      if (s.material && s.facility) return t('Material & Räume')
      if (s.material) return t('Material')
      return s.facility ? t('Räume und Anlagen') : t('Belegung')
    },
    path: '/material',
    also: ['/infrastruktur', '/belegung'],
    linkFor: (org, ws) => {
      const s = stockAccess(org, ws)
      return s.material ? '/material' : s.facility ? '/infrastruktur' : '/belegung'
    },
    icon: icon('M4 7l8-4 8 4v10l-8 4-8-4zM4 7l8 4 8-4M12 11v10'),
    visible: (org, ws) => {
      const s = stockAccess(org, ws)
      return s.material || s.facility || s.bookings
    },
    children: (org, ws) => {
      const s = stockAccess(org, ws ?? NO_WS)
      const items = [
        ...(s.material ? [{ to: '/material', label: t('Material') }] : []),
        // Musikausstattung als Ansicht des Materials (Menüprüfung 2, N-05)
        ...(s.material && org?.modules.includes('music') && org.permissions.includes('music.view')
          ? [{ to: '/material/musik', label: t('Instrumente und Uniformen') }]
          : []),
        ...(s.facility ? [{ to: '/infrastruktur', label: t('Räume und Anlagen') }] : []),
        ...(s.bookings ? [{ to: '/belegung', label: t('Belegung') }] : []),
      ]
      return items.length > 1 ? items : []
    },
  },
  // Sammelbestellungen: Vereinskleidung, Festschrift, Größenabfragen (Lückenliste 20.11., B4)
  {
    id: 'bestellungen',
    group: 'verwaltung',
    label: t('Bestellungen'),
    path: '/bestellungen',
    icon: icon('M6 7h12l-1 13H7zM9 7a3 3 0 0 1 6 0'),
    visible: (org) =>
      !!org &&
      org.type === 'club' &&
      org.modules.includes('orders') &&
      (org.permissions.includes(PERM.ordersView) || org.permissions.includes(PERM.ordersEdit)),
  },
  {
    id: 'einstellungen',
    group: 'verwaltung',
    label: t('Einstellungen'),
    path: '/einstellungen',
    icon: icon(
      'M4 7h8M16 7h4M4 17h4M12 17h8M14 5a2 2 0 1 1 0 4 2 2 0 0 1 0-4M10 15a2 2 0 1 1 0 4 2 2 0 0 1 0-4',
    ),
    // Ohne einen lesbaren Unterpunkt kein Menüpunkt (UX-Audit 08.11., W-01)
    visible: (org) =>
      !!org &&
      (org.type !== 'unit' || org.permissions.includes(PERM.rolesManage)) &&
      settingsItems(org).length > 0,
  },
  {
    id: 'plattform',
    group: 'verwaltung',
    label: t('Plattform'),
    path: '/plattform',
    icon: icon('M3 21h18M5 21V8l7-5 7 5v13M10 21v-5h4v5M9 11h.01M15 11h.01'),
    visible: (org) => !!org && org.permissions.includes(PERM.platformManage),
  },
]

/** Nie in der unteren Leiste: selten gebraucht und im Menü unter „Mehr“ gut zu finden. */
const BOTTOM_NAV_NEVER = new Set(['einstellungen', 'plattform'])

/**
 * Untere Leiste auf dem Handy (UX-Audit 16.11., VW-32): Start und zwei Bereiche, zuerst nach
 * dem Schwerpunkt der Rolle (Kasse: Finanzen, Schriftführung: Versammlungen), dann Termine,
 * Mitglieder und Mein Bereich, danach der Reihe nach, was die Rolle sonst sehen darf. So hat
 * jede Rolle drei Bereiche plus „Mehr“.
 */
export function bottomNavIds(visibleIds: string[], focus: string[] | undefined): string[] {
  const preferred = [
    ...(focus?.includes('finance') ? ['finanzen'] : []),
    ...(focus?.includes('minutes') ? ['versammlungen'] : []),
    'termine',
    'mitglieder',
    'mein-bereich',
  ]
  const rest = visibleIds.filter((id) => id !== 'start' && !BOTTOM_NAV_NEVER.has(id))
  const ordered = ['start', ...preferred.filter((id) => rest.includes(id)), ...rest]
  return [...new Set(ordered)].filter((id) => id === 'start' || visibleIds.includes(id)).slice(0, 3)
}
