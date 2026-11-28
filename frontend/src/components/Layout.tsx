import { Suspense, useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { OfflineBanner } from './OfflineBanner.tsx'
import { SubNavContext, buildNavTree } from './subnav.ts'
import type { SubNavItem } from './subnav.ts'
import { SubNavList } from './SubNavList.tsx'
import { formatTitle, useTitleOverride } from './pageTitle.ts'
import { NavTrailContext, navTrail, trailTitle } from './navTrail.ts'
import type { TrailItem } from './navTrail.ts'
import { PageSlotProvider } from './PageHeader.tsx'
import { confirmLeave } from './leaveGuard.ts'
import { Link, NavLink, Outlet, useLocation, useNavigate } from 'react-router-dom'
import { useAuth } from '../auth/AuthContext.tsx'
import { bottomNavIds, modules } from '../modules.tsx'
import { areaOf, arrangedAreas } from '../menuLayout.ts'
import { NewMenu } from './NewMenu.tsx'
import { TodoMenu } from './TodoMenu.tsx'
import { currentMemberArea, memberAreas } from './memberAreas.tsx'
import { actionCatalog, deptCatalog } from './home/roleActions.ts'
import { QuickSearch } from './QuickSearch.tsx'
import type { QuickPage } from './QuickSearch.tsx'
import { portalSections } from '../pages/portal/sections.ts'
import { displayName } from '../api/orgs.ts'
import { calendarBase } from '../api/events.ts'
import { leaveTo, ssoApi } from '../api/peering.ts'
import type { SsoAccount } from '../api/peering.ts'
import { useOrg } from '../org/OrgContext.tsx'
import { AppFooter } from './ImprintFooter.tsx'
import { Logo } from './Logo.tsx'
import { usePlatform } from '../theme/platform.ts'
import { UndoControls } from './UndoControls.tsx'
import { useUndo } from './undo.ts'
import { alertDialog } from './dialog.ts'
import { preloadPagesGently } from '../lazyPages.ts'
import { PageErrorBoundary } from './PageErrorBoundary.tsx'
import { LearningProvider } from '../learning/LearningContext.tsx'
import { HelpProvider } from '../help/HelpContext.tsx'
import { HelpButton, HelpPanel } from '../help/HelpPanel.tsx'
import { ACCOUNT_PATH, accountSectionLabel } from '../pages/settings/accountNav.ts'
import { AccountMenu } from './AccountMenu.tsx'
import type { PersonalArea } from './AccountMenu.tsx'
import { RolePreviewBanner, RolePreviewSelect } from './RolePreview.tsx'
import { UpdateNotice } from '../news/UpdateNotice.tsx'
import { NewReleaseNotice } from '../news/NewReleaseNotice.tsx'
import { PERM, rolePreviewApi } from '../api/orgs.ts'
import { locale, t } from '../i18n/index.ts'
import { atMost, BP_MEDIUM } from '../theme/breakpoints.ts'

/** Merkt die zuletzt gewählte Einheit der Verwaltung für den Wechsel der Sicht */
const ADMIN_KEY = 'hubiplan.verwaltung'
/** Merkt je Gerät, ob das Bereichsmenü eingeklappt ist */
const MENU_KEY = 'hubiplan.bereichsmenue'
// Je Konto gemerkt: einmal zur Einrichtung der Zwei-Faktor-Anmeldung geführt
const MFA_GUIDE_KEY = 'hubiplan.2fa-gefuehrt'

// Seiten außerhalb der Bereiche in der Seitenleiste
const OTHER_PAGES: Record<string, string> = {
  '/mein-konto': t('Mein Konto'),
  '/hilfe': t('Hilfe'),
  '/hilfe/anleitungen': t('{label} · {modLabel}', {
    label: t('Anleitungen'),
    modLabel: t('Hilfe'),
  }),
  '/hilfe/seiten': t('{label} · {modLabel}', { label: t('Seiten'), modLabel: t('Hilfe') }),
  '/hilfe/begriffe': t('{label} · {modLabel}', { label: t('Begriffe'), modLabel: t('Hilfe') }),
  '/hilfe/neuigkeiten': t('{label} · {modLabel}', {
    label: t('Neuigkeiten'),
    modLabel: t('Hilfe'),
  }),
  '/briefvorlage': t('Briefvorlage'),
}

export function Layout() {
  const { user, logout } = useAuth()
  const {
    orgs,
    departments,
    portal,
    active,
    activeKey,
    activeDept,
    activePortal,
    select,
    loading,
    refresh,
  } = useOrg()
  const navigate = useNavigate()
  const { pathname } = useLocation()
  const [navOpen, setNavOpen] = useState(false)
  // Pflicht-2FA: ein neues Konto mit heiklen Rechten einmal von der Startseite direkt zur
  // Einrichtung führen, statt es erst beim Buchen scheitern zu lassen. Danach bleibt der Hinweis.
  // Nicht bei schon ruhenden Rechten: Dort nennt die Startseite selbst den nächsten Schritt
  const mfaDue = !!user?.mfa_required_by && !user?.mfa_overdue
  const userId = user?.id
  useEffect(() => {
    if (!mfaDue || !userId || pathname !== '/' || user?.must_change_password) return
    const key = `${MFA_GUIDE_KEY}:${userId}`
    try {
      if (window.localStorage.getItem(key)) return
      window.localStorage.setItem(key, '1')
    } catch {
      return // Ohne Speicher nicht bei jedem Aufruf umleiten
    }
    navigate('/mein-konto/anmeldung#zwei-faktor')
  }, [mfaDue, userId, pathname, navigate, user?.must_change_password])
  // Bereichsmenü neben der Bereichsleiste: einklappbar, damit breite Listen mehr Platz haben
  const [menuClosed, setMenuClosed] = useState(() => {
    try {
      return window.localStorage.getItem(MENU_KEY) === 'zu'
    } catch {
      return false
    }
  })
  function toggleMenu() {
    setMenuClosed((closed) => {
      try {
        window.localStorage.setItem(MENU_KEY, closed ? 'auf' : 'zu')
      } catch {
        // Ohne Speicher gilt die Wahl bis zum Neuladen
      }
      return !closed
    })
  }
  // Unterpunkte der aktuellen Seite (früher Reiter), siehe subnav.ts
  const [subNav, setSubNav] = useState<Record<string, SubNavItem[]>>({})
  const setSub = useCallback((id: string, items: SubNavItem[] | null) => {
    setSubNav((old) => {
      if (items === null) {
        if (!(id in old)) return old
        const rest = { ...old }
        delete rest[id]
        return rest
      }
      if (JSON.stringify(old[id]) === JSON.stringify(items)) return old
      return { ...old, [id]: items }
    })
  }, [])

  const toggleRef = useRef<HTMLButtonElement>(null)
  const navRef = useRef<HTMLElement>(null)
  const topbarRef = useRef<HTMLElement>(null)
  // Höhe der Kopfzeile für die feste Seitenleiste (index.css --topbar-height)
  useEffect(() => {
    const el = topbarRef.current
    if (!el || typeof ResizeObserver === 'undefined') return
    const root = document.documentElement
    const measure = () => root.style.setProperty('--topbar-height', `${el.offsetHeight}px`)
    measure()
    const ro = new ResizeObserver(measure)
    ro.observe(el)
    return () => {
      ro.disconnect()
      root.style.removeProperty('--topbar-height')
    }
  }, [])

  // Übrige Bereiche nach der Anmeldung im Hintergrund nachladen, damit spätere
  // Seitenwechsel ohne Wartezeit gehen
  useEffect(() => {
    let stop = () => undefined as void
    const timer = setTimeout(() => {
      stop = preloadPagesGently()
    }, 2000)
    return () => {
      clearTimeout(timer)
      stop()
    }
  }, [])

  // Ausgeklappte Navigation (Handy): Fokus hinein, Esc schließt, Fokus zurück zum Knopf.
  // Der Fokus wandert erst nach dem Rendern, wenn Kopf und Inhalt nicht mehr „inert“
  // sind; nach der Wahl eines Bereichs auf den neuen Inhalt (UI-Audit NUI-01).
  const focusAfterClose = useRef<'toggle' | 'main' | null>(null)
  useEffect(() => {
    if (navOpen) {
      navRef.current?.querySelector<HTMLElement>('a, button')?.focus()
      const onKey = (e: KeyboardEvent) => {
        if (e.key !== 'Escape') return
        focusAfterClose.current = 'toggle'
        setNavOpen(false)
      }
      window.addEventListener('keydown', onKey)
      return () => window.removeEventListener('keydown', onKey)
    }
    const target = focusAfterClose.current
    focusAfterClose.current = null
    if (target === 'toggle') toggleRef.current?.focus()
    else if (target === 'main') document.getElementById('inhalt')?.focus()
  }, [navOpen])

  // Seitenwechsel (anderer Pfad): Fokus auf die Überschrift der neuen Seite, damit
  // Screenreader den Wechsel ansagen und Tastaturnutzer oben im Inhalt weitermachen
  // (WCAG 2.4.3). Ein Eingabefeld, das die Seite selbst fokussiert, bleibt fokussiert.
  const firstPath = useRef(true)
  useEffect(() => {
    if (firstPath.current) {
      firstPath.current = false
      return
    }
    let tries = 0
    const timer = setInterval(() => {
      const main = document.getElementById('inhalt')
      const heading = main?.querySelector<HTMLElement>('h1')
      if (!heading && ++tries < 20) return
      clearInterval(timer)
      if (!main) return
      // Liegt schon ein Dialog über der Seite (Seite „inert“), bleibt der Fokus dort.
      if (main.closest('[inert]')) return
      const current = document.activeElement
      if (
        current instanceof HTMLElement &&
        main.contains(current) &&
        current.matches('input, select, textarea')
      )
        return
      const target = heading ?? main
      if (target !== main && !target.hasAttribute('tabindex')) target.setAttribute('tabindex', '-1')
      target.focus({ preventScroll: true })
    }, 50)
    return () => clearInterval(timer)
  }, [pathname])

  // Verknüpfte Zugänge auf anderen Instanzen (Verbund): stehen mit in der Einheitenauswahl
  const [remoteAccounts, setRemoteAccounts] = useState<SsoAccount['accounts']>([])
  useEffect(() => {
    let alive = true
    ssoApi
      .account()
      .then((d) => alive && setRemoteAccounts(d.accounts))
      .catch(() => alive && setRemoteAccounts([]))
    return () => {
      alive = false
    }
  }, [])

  // Handy/Tablet (W-05): Rückgängig, Rollenansicht und Einheitenwahl stehen im Menü statt im Kopf
  const [narrow, setNarrow] = useState(() => atMost(BP_MEDIUM))
  // Breiter als der Handy-Umbruch: Navigation steht fest, also zuklappen
  useEffect(() => {
    const wide = window.matchMedia?.(`not all and (max-width: ${BP_MEDIUM})`)
    if (!wide) return
    const onChange = () => {
      setNarrow(!wide.matches)
      if (wide.matches) setNavOpen(false)
    }
    wide.addEventListener?.('change', onChange)
    return () => wide.removeEventListener?.('change', onChange)
  }, [])

  function closeNav() {
    focusAfterClose.current = 'toggle'
    setNavOpen(false)
  }
  function choseInNav() {
    if (navOpen) focusAfterClose.current = 'main'
    setNavOpen(false)
  }
  // Nach Rückgängig/Wiederherstellen lädt die Seite ihre Daten neu
  const undoBase = active
    ? `/api/orgs/${active.id}`
    : activeDept
      ? `/api/depts/${activeDept.id}`
      : null
  const { version } = useUndo(undoBase)

  // Ansicht als Rolle: nach dem Wechsel Rechte neu laden und die Seite neu aufbauen
  const [previewVersion, setPreviewVersion] = useState(0)
  const previewOrg = orgs.find((o) => o.role_preview?.active) ?? null
  const previewChanged = useCallback(async () => {
    await refresh()
    setPreviewVersion((v) => v + 1)
  }, [refresh])

  async function handleLogout() {
    try {
      if (!(await logout())) return
    } catch {
      await alertDialog({
        title: t('Abmelden hat nicht geklappt'),
        message: t(
          'Der Server hat die Abmeldung nicht bestätigt. Du bist noch angemeldet. Bitte erneut versuchen.',
        ),
      })
      return
    }
    navigate('/anmelden')
  }

  async function switchOrg(key: string, to = '/') {
    // Erst Offenes speichern; scheitert das und bleibt man, ändert sich nichts (NMF-01)
    if (!(await confirmLeave())) return
    const remote = remoteAccounts.find((a) => `r:${a.id}` === key)
    if (remote) {
      // Einheit auf einer anderen Instanz: dort gleich über diese Instanz angemeldet
      leaveTo.go(remote.url)
      return
    }
    // Die Ansicht als Rolle gilt nur in ihrer Einheit: beim Wechsel endet sie
    if (previewOrg && key !== String(previewOrg.id)) {
      try {
        await rolePreviewApi.stop(previewOrg.id)
        await refresh()
      } catch {
        // Ohne Antwort bleibt die Ansicht bestehen; der Hinweis zeigt sie weiter
      }
    }
    select(key)
    setNavOpen(false)
    navigate(to)
  }

  // Zwei Sichten (Konzept Web-Oberfläche W3): „Mein Verein“ zeigt, was die Person als Mitglied
  // sieht, „Verwaltung“ die Einheiten, in denen sie mitarbeitet. Der Schalter erscheint nur,
  // wenn es beides gibt.
  const adminKeys = [...orgs.map((o) => String(o.id)), ...departments.map((d) => `d:${d.id}`)]
  const twoViews = portal.length > 0 && adminKeys.length > 0
  useEffect(() => {
    if (!activeKey || activeKey.startsWith('p:')) return
    try {
      window.localStorage.setItem(ADMIN_KEY, activeKey)
    } catch {
      // Ohne Speicher führt „Verwaltung“ zur ersten Einheit
    }
  }, [activeKey])
  function showMemberView() {
    const club = active?.id ?? activeDept?.club_id
    const entry = portal.find((p) => p.club_id === club) ?? portal[0]
    void switchOrg(`p:${entry.id}`)
  }
  function showAdminView() {
    let last: string | null = null
    try {
      last = window.localStorage.getItem(ADMIN_KEY)
    } catch {
      last = null
    }
    const own = String(activePortal?.club_id ?? '')
    void switchOrg(
      last && adminKeys.includes(last) ? last : adminKeys.includes(own) ? own : adminKeys[0],
    )
  }

  // Persönliches im Kontomenü (UX-Audit 10.7); die Auswahl oben zeigt nur Verwaltungsbereiche
  const personal: PersonalArea[] = portal.map((p) => ({
    key: `p:${p.id}`,
    // Mehrere Zugänge (z. B. zwei Kinder im selben Verein): am Namen unterscheidbar (VW-25)
    title:
      portal.length > 1
        ? `${p.member_kind === 'organization' ? (p.member_name ?? '') : p.first_name} · ${
            p.club_display_name || p.club_name
          }`
        : undefined,
    links: portalSections(p).flatMap((s) => (s.account ? [{ to: s.to, label: s.account }] : [])),
  }))
  const portalInPicker = portal.filter((p) => activeKey === `p:${p.id}`)

  const ws = { dept: activeDept, portal: activePortal }
  const visible = modules.filter((m) => m.visible(active, ws))
  // Untere Leiste auf dem Handy: drei Bereiche nach der Rolle plus „Mehr“ (VW-32)
  const bottomNav = bottomNavIds(
    visible.map((m) => m.id),
    active?.home_focus,
  )
    .map((id) => visible.find((m) => m.id === id))
    .filter((m): m is (typeof visible)[number] => !!m)
  // Bereiche der Bereichsleiste mit ihren sichtbaren Menüpunkten (Konzept Web-Oberfläche)
  // Hat ein Bereich für die Person nur einen Menüpunkt, trägt er dessen Namen und Zeichen
  // (z. B. „Züge“ statt „Mitglieder“): Hinter dem Namen steckt dann genau diese Seite.
  // Anordnung der Einheit (Menü frei anordnen); Untereinheiten übernehmen die ihres Vereins
  const menuLayout = active?.menu_layout ?? activeDept?.menu_layout ?? null
  // Menüpunkte, die im selben Bereich wie ihr Elternpunkt stehen, erscheinen als dessen
  // Unterpunkt (nestUnder, z. B. DSGVO unter Einstellungen); sonst als eigener Eintrag
  const nestedOf = (p: (typeof modules)[number]) =>
    visible.filter(
      (n) => n.nestUnder?.id === p.id && areaOf(menuLayout, n) === areaOf(menuLayout, p),
    )
  const nested = new Set(visible.flatMap((p) => nestedOf(p).map((n) => n.id)))
  const areas = arrangedAreas(menuLayout)
    .map((a) => {
      // Ein Menüpunkt als Hauptmenüpunkt steht vor den Menüpunkten, die ihm zugeordnet sind
      const items = visible
        .filter((m) => areaOf(menuLayout, m) === a.id && !nested.has(m.id))
        .sort((x, y) => Number(y.id === a.id) - Number(x.id === a.id))
      // Ein selbst benannter Bereich behält seinen Namen auch mit nur einem Menüpunkt
      const only = items.length === 1 && a.id !== 'start' && !a.named ? items[0] : null
      return only
        ? {
            ...a,
            items,
            label:
              only.id === 'abteilung' && activeDept
                ? activeDept.label
                : (only.labelFor?.(active, ws) ?? only.label),
            icon: only.icon,
          }
        : { ...a, items }
    })
    .filter((a) => a.items.length > 0)
  const modulePaths = (m: (typeof modules)[number]) => [m.path, ...(m.also ?? [])]
  const inModule = (m: (typeof modules)[number]) =>
    [m, ...nestedOf(m)]
      .flatMap(modulePaths)
      .some((p) => pathname === p || pathname.startsWith(`${p}/`))
  const contextCount =
    orgs.length + departments.length + portalInPicker.length + remoteAccounts.length
  // Im Kopf steht immer der volle Name, der Kurzname nur in der Auswahl.
  // Ohne Einheit: Name und Logo der Instanz (White Label, Vorgabe „HUBIplan“)
  const instance = usePlatform()
  const brandName = active?.name ?? activeDept?.name ?? activePortal?.club_name ?? instance.name
  // Helles und dunkles Logo kommen immer von derselben Stelle
  const brandTheme = [active?.theme, activeDept?.theme, activePortal?.theme].find(
    (tm) => tm?.logo_url != null || tm?.logo_dark_url != null,
  )
  const brandLogo = brandTheme ? brandTheme.logo_url : instance.logo_url
  const brandLogoDark = brandTheme
    ? (brandTheme.logo_dark_url ?? null)
    : (instance.logo_dark_url ?? null)

  // Seitentitel im Browser-Tab: Bereich · Arbeitsbereich · HUBIplan (WCAG 2.4.2)
  // Pfad der Seite aus der Menüstruktur (Seitenkopf S-05, W-02): Modul › Unterpunkt ›
  // angemeldeter Unterpunkt der Seite. Seitentitel, h1 und Pfadzeile nutzen ihn.
  const matchesPath = (path: string) => pathname === path || pathname.startsWith(`${path}/`)
  // Schnellsuche (Design „Frisch“ D7): alle sichtbaren Menüpunkte samt Unterpunkten
  const quickPages: QuickPage[] = visible.flatMap((m) => {
    const label = m.labelFor?.(active, ws) ?? m.label
    const to = m.linkFor?.(active, ws) ?? m.path
    const children = (m.children?.(active, ws) ?? [])
      .filter((c) => c.to !== to)
      .map((c) => ({ to: c.to, label: c.label, parent: label }))
    return [{ to, label }, ...children]
  })
  const quickMemberOrg =
    active?.type === 'club' && visible.some((m) => m.id === 'mitglieder') ? active.id : null
  // VW-59: Termine des gewählten Bereichs in der Schnellsuche, wenn der Kalender im Menü steht
  const quickEventBase = !visible.some((m) => m.id === 'termine')
    ? null
    : active
      ? calendarBase.org(active.id)
      : activeDept
        ? calendarBase.dept(activeDept.id)
        : activePortal
          ? calendarBase.portal(activePortal.id)
          : null
  const currentModule = visible
    .filter((m) => modulePaths(m).some(matchesPath))
    .sort((a, b) => b.path.length - a.path.length)[0]
  // Gewählter Bereich: der des aktuellen Menüpunkts; Seiten außerhalb (Hilfe, Mein Konto)
  // gehören zu keinem
  // Die Bereichsübersicht (/bereich/…) gehört zu ihrem Bereich
  const overviewOf = /^\/bereich\/([a-z0-9-]+)$/.exec(pathname)?.[1]
  const currentArea =
    areas.find(
      (a) => a.id === (overviewOf ?? (currentModule ? areaOf(menuLayout, currentModule) : null)),
    ) ?? null
  const moduleLabel = (m: (typeof modules)[number]) =>
    m.id === 'abteilung' && activeDept ? activeDept.label : (m.labelFor?.(active, ws) ?? m.label)
  const moduleLink = (m: (typeof modules)[number]) => m.linkFor?.(active, ws) ?? m.path
  // Feste Unterpunkte eines Menüpunkts samt eingehängter Menüpunkte (nestUnder), diese
  // hinter dem letzten Unterpunkt ihrer Zwischenüberschrift
  const fixedChildren = (m: (typeof modules)[number]) => {
    const list = [...(m.children?.(active, ws) ?? [])]
    for (const n of nestedOf(m)) {
      const item = { to: moduleLink(n), label: moduleLabel(n), section: n.nestUnder?.section }
      const last = list.map((c) => c.section).lastIndexOf(item.section)
      if (last < 0) list.push(item)
      else list.splice(last + 1, 0, item)
    }
    return list
  }
  const moduleTree = (m: (typeof modules)[number]) =>
    buildNavTree(
      m.path,
      fixedChildren(m),
      // Als Reiter gezeigte Unterpunkte stehen im Inhalt, nicht im Menü (W6)
      inModule(m) ? Object.values(subNav).filter((g) => !g.some((i) => i.tab)) : [],
    )
  // Heißt der Menüpunkt wie sein Bereich (Mitglieder, Finanzen), stehen seine Unterpunkte
  // direkt im Bereichsmenü: eine Ebene weniger
  const flat = (m: (typeof modules)[number]) =>
    (m.flat || m.id === areaOf(menuLayout, m)) && moduleTree(m).some((n) => n.to === moduleLink(m))
  // Ein Bereich mit nur einer Seite (Start) braucht kein Bereichsmenü
  const areaHasMenu =
    !!currentArea && (currentArea.items.length > 1 || moduleTree(currentArea.items[0]).length > 0)
  // Sicht „Mein Verein“: vier Bereiche wie in den Apps statt der Gliederung der Verwaltung
  const memberNav = activePortal
    ? memberAreas(
        activePortal,
        visible.some((m) => m.id === 'dokumente'),
      )
    : null
  const memberCurrent = memberNav ? currentMemberArea(memberNav, pathname) : null
  const railItems = memberNav
    ? memberNav.map((a) => ({ id: a.id, label: a.label, icon: a.icon, to: a.links[0].to }))
    : areas.map((a) => ({ id: a.id, label: a.label, icon: a.icon, to: moduleLink(a.items[0]) }))
  const railCurrent = memberNav ? memberCurrent?.id : currentArea?.id
  const hasMenu = memberNav ? (memberCurrent?.links.length ?? 0) > 1 : areaHasMenu
  const menuTitle = memberNav ? memberCurrent?.label : currentArea?.label
  const viewSwitch = twoViews && (
    <div className="segmented view-switch" role="group" aria-label={t('Sicht')}>
      <button
        type="button"
        className="button button-ghost"
        aria-pressed={!!activePortal}
        onClick={() => !activePortal && showMemberView()}
      >
        {t('Mein Verein')}
      </button>
      <button
        type="button"
        className="button button-ghost"
        aria-pressed={!activePortal}
        onClick={() => activePortal && showAdminView()}
      >
        {t('Verwaltung')}
      </button>
    </div>
  )
  const newActions = active ? actionCatalog(active) : activeDept ? deptCatalog(activeDept) : []
  // Unterpunkte, die das Menü fest zeigt: Seiten melden sie nicht noch einmal als Reiter an
  const fixedKey = JSON.stringify((currentModule?.children?.(active, ws) ?? []).map((c) => c.to))
  const subNavApi = useMemo(
    () => ({ set: setSub, fixed: JSON.parse(fixedKey) as string[] }),
    [setSub, fixedKey],
  )
  const trail = currentModule
    ? navTrail(
        pathname,
        {
          path: currentModule.path,
          link: currentModule.linkFor?.(active, ws),
          label:
            currentModule.id === 'abteilung' && activeDept
              ? activeDept.label
              : (currentModule.labelFor?.(active, ws) ?? currentModule.label),
        },
        currentModule.children?.(active, ws) ?? [],
        Object.values(subNav),
      )
    : []
  const trailKey = JSON.stringify(trail)
  // Einheit im Seitenkopf nur, wenn die Person mehrere Einheiten wählen kann (W-06)
  const unitName =
    contextCount > 1 ? (active ? displayName(active) : (activeDept?.name ?? null)) : null
  const navTrailValue = useMemo(
    () => ({ trail: JSON.parse(trailKey) as TrailItem[], unit: unitName }),
    [trailKey, unitName],
  )
  const pageLabel = (() => {
    if (!currentModule) {
      const section = accountSectionLabel(pathname)
      if (section && pathname !== ACCOUNT_PATH) return t('{section} · Mein Konto', { section })
      if (overviewOf) return currentArea?.label ?? null
      return OTHER_PAGES[pathname] ?? null
    }
    return trailTitle(trail)
  })()
  const titleOverride = useTitleOverride()
  useEffect(() => {
    // formatTitle hängt den Namen der Instanz an und lässt ihn hier dann weg
    document.title = formatTitle(titleOverride ?? pageLabel, brandName)
  }, [titleOverride, pageLabel, brandName, instance.name])

  // Lernhilfen nur in der Oberfläche der Bearbeitenden, nie im Mitgliederbereich
  const headerTools = (
    <>
      {undoBase && !previewOrg && (
        <UndoControls
          base={undoBase}
          logTo={
            active?.permissions.includes(PERM.auditView) ? '/einstellungen/protokoll' : undefined
          }
        />
      )}
      {/* In der Sicht „Mein Verein“ wechselt der Schalter der Sichten zurück zur Verwaltung */}
      {contextCount > 1 && !(twoViews && activePortal) && (
        <label className="org-switch">
          <span className="sr-only">{t('Einheit wechseln')}</span>
          <select
            value={activeKey ?? ''}
            onChange={(e) => void switchOrg(e.target.value)}
            aria-label={t('Einheit wechseln')}
          >
            {orgs.map((o) => (
              <option key={o.id} value={String(o.id)}>
                {displayName(o)} ({o.type_label})
              </option>
            ))}
            {departments.map((d) => (
              <option key={`d${d.id}`} value={`d:${d.id}`}>
                {d.path?.includes('›') ? d.path : displayName(d)} (
                {d.club_display_name || d.club_name})
              </option>
            ))}
            {portalInPicker.map((p) => (
              <option key={`p${p.id}`} value={`p:${p.id}`}>
                {p.member_kind === 'organization'
                  ? t('Mein Bereich: {member} als Ansprechpartner ({club})', {
                      member: p.member_name ?? '',
                      club: p.club_display_name || p.club_name,
                    })
                  : t('Mein Bereich: {first_name} ({club})', {
                      first_name: p.first_name,
                      club: p.club_display_name || p.club_name,
                    })}
              </option>
            ))}
            {remoteAccounts.length > 0 && (
              <optgroup label={t('Auf anderen Instanzen')}>
                {remoteAccounts.map((a) => (
                  <option key={`r${a.id}`} value={`r:${a.id}`}>
                    {a.base_url.replace(/^https:\/\//, '')} {t('öffnen')}
                  </option>
                ))}
              </optgroup>
            )}
          </select>
        </label>
      )}
    </>
  )

  return (
    <SubNavContext.Provider value={subNavApi}>
      <NavTrailContext.Provider value={navTrailValue}>
        <PageSlotProvider>
          <LearningProvider off={!active && !activeDept}>
            <HelpProvider>
              <div
                className={`app-shell${navOpen ? ' nav-open' : ''}${
                  hasMenu && !menuClosed ? '' : ' area-menu-off'
                }`}
              >
                <a href="#inhalt" className="skip-link">
                  {t('Zum Inhalt springen')}
                </a>
                <header className="topbar" inert={navOpen || undefined} ref={topbarRef}>
                  <button
                    type="button"
                    className="nav-toggle"
                    ref={toggleRef}
                    aria-label={navOpen ? t('Navigation schließen') : t('Navigation öffnen')}
                    aria-expanded={navOpen}
                    aria-controls="hauptnavigation"
                    onClick={() => setNavOpen((o) => !o)}
                  >
                    <span />
                    <span />
                    <span />
                  </button>
                  <NavLink to="/" className="topbar-brand">
                    <Logo name={brandName} logoUrl={brandLogo} logoDarkUrl={brandLogoDark} />
                  </NavLink>
                  {/* Suche in der Mitte: der schnellste Weg zu jeder Seite, jedem Mitglied und Termin */}
                  {!narrow && (
                    <div className="topbar-search">
                      <QuickSearch
                        pages={quickPages}
                        memberOrg={quickMemberOrg}
                        eventBase={quickEventBase}
                      />
                    </div>
                  )}
                  <div className={`topbar-user${twoViews && !narrow ? ' topbar-tight' : ''}`}>
                    {!narrow && viewSwitch}
                    {!previewOrg && <NewMenu actions={newActions} />}
                    {active &&
                      !previewOrg &&
                      (active.type === 'club' || active.type === 'federation') && (
                        <TodoMenu org={active} />
                      )}
                    {!narrow && headerTools}
                    {/* VW-02: auch am Handy erreichbar, dort nur als Zeichen mit Namen */}
                    <HelpButton compact={narrow || twoViews} />
                    <AccountMenu
                      email={user?.email}
                      onLogout={handleLogout}
                      extra={
                        active && (
                          <RolePreviewSelect org={active} onChanged={previewChanged} labelled />
                        )
                      }
                      personal={personal}
                      onPersonal={(key, to) => void switchOrg(key, to)}
                    />
                  </div>
                </header>

                <nav
                  className="sidebar"
                  id="hauptnavigation"
                  aria-label={t('Hauptmenü')}
                  ref={navRef}
                >
                  <button type="button" className="sidebar-close" onClick={closeNav}>
                    <span aria-hidden="true">×</span> {t('Navigation schließen')}
                  </button>
                  {narrow && (
                    <div className="sidebar-tools">
                      {/* Am Handy steht die Schnellsuche im Menü: oben ist kein Platz neben dem Namen */}
                      <QuickSearch
                        pages={quickPages}
                        memberOrg={quickMemberOrg}
                        eventBase={quickEventBase}
                        onNavigate={choseInNav}
                      />
                      {viewSwitch}
                      {headerTools}
                    </div>
                  )}
                  {narrow ? (
                    <>
                      {/* Handy und Tablet: das ganze Menü, je Bereich eine Überschrift mit eigener
                          Liste, damit Hilfstechnik die Bereiche ansagt (UX-Audit 16.11. VW-28) */}
                      <ul className="sidebar-groups">
                        {memberNav?.map((a, index) => (
                          <li key={a.id} className={index > 0 ? 'sidebar-group-start' : undefined}>
                            <h2 className="sidebar-group-label" id={`menue-gruppe-${a.id}`}>
                              {a.label}
                            </h2>
                            <ul aria-labelledby={`menue-gruppe-${a.id}`}>
                              {a.links.map((l) => (
                                <li key={l.to}>
                                  <NavLink
                                    to={l.to}
                                    end={l.to === '/' || l.to === '/mein-bereich'}
                                    className="sidebar-link"
                                    onClick={choseInNav}
                                  >
                                    <span>{l.label}</span>
                                  </NavLink>
                                </li>
                              ))}
                            </ul>
                          </li>
                        ))}
                        {(memberNav ? [] : areas).map((a, index) => (
                          <li key={a.id} className={index > 0 ? 'sidebar-group-start' : undefined}>
                            <h2 className="sidebar-group-label" id={`menue-gruppe-${a.id}`}>
                              {a.label}
                            </h2>
                            <ul aria-labelledby={`menue-gruppe-${a.id}`}>
                              {a.items.map((m) => (
                                <li key={m.id}>
                                  <NavLink
                                    to={moduleLink(m)}
                                    end={m.path === '/'}
                                    className="sidebar-link"
                                    onClick={choseInNav}
                                  >
                                    {m.icon}
                                    <span>{moduleLabel(m)}</span>
                                  </NavLink>
                                  {inModule(m) && (
                                    <SubNavList
                                      nodes={moduleTree(m)}
                                      pathname={pathname}
                                      onChoose={choseInNav}
                                    />
                                  )}
                                </li>
                              ))}
                            </ul>
                          </li>
                        ))}
                      </ul>
                      {/* Immer am selben Ort erreichbar, unabhängig vom Modul (UI-Audit H-NUI-C) */}
                      <div className="sidebar-help">
                        <NavLink to="/hilfe" className="sidebar-link" onClick={choseInNav}>
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
                            <circle cx="12" cy="12" r="9" />
                            <path d="M9.5 9.5a2.5 2.5 0 1 1 3.5 2.3c-.6.3-1 .9-1 1.6V14M12 17.5h.01" />
                          </svg>
                          <span>{t('Hilfe')}</span>
                        </NavLink>
                      </div>
                    </>
                  ) : (
                    <>
                      {/* Bereichsleiste in Vereinsfarbe: sieben feste Bereiche, immer sichtbar */}
                      <div className="area-rail">
                        <ul aria-label={t('Bereiche')}>
                          {railItems.map((a) => (
                            <li key={a.id}>
                              <Link
                                to={a.to}
                                className={`area-rail-link${a.id === railCurrent ? ' active' : ''}`}
                                aria-current={a.id === railCurrent ? 'true' : undefined}
                              >
                                {a.icon}
                                <span>{a.label}</span>
                              </Link>
                            </li>
                          ))}
                        </ul>
                        <div className="area-rail-end">
                          {hasMenu && (
                            <button
                              type="button"
                              className="area-rail-link area-rail-toggle"
                              aria-expanded={!menuClosed}
                              aria-controls="bereichsmenue"
                              onClick={toggleMenu}
                            >
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
                                <path d="M4 5h16v14H4zM9.5 5v14" />
                                <path
                                  d={
                                    menuClosed
                                      ? 'M13.5 9.5 16 12l-2.5 2.5'
                                      : 'M16 9.5 13.5 12l2.5 2.5'
                                  }
                                />
                              </svg>
                              <span>{t('Menü')}</span>
                            </button>
                          )}
                          <NavLink to="/hilfe" className="area-rail-link">
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
                              <circle cx="12" cy="12" r="9" />
                              <path d="M9.5 9.5a2.5 2.5 0 1 1 3.5 2.3c-.6.3-1 .9-1 1.6V14M12 17.5h.01" />
                            </svg>
                            <span>{t('Hilfe')}</span>
                          </NavLink>
                        </div>
                      </div>
                      {/* Bereichsmenü: nur die Seiten des gewählten Bereichs, hell und ruhig */}
                      {hasMenu && (
                        <div className="area-menu" id="bereichsmenue" hidden={menuClosed}>
                          <h2 className="area-menu-title" id="bereichsmenue-titel">
                            {/* Der Name des Bereichs führt zu seiner Übersicht (W4) */}
                            {!memberNav &&
                            currentArea &&
                            currentArea.id !== 'finanzen' &&
                            currentArea.items.length > 1 ? (
                              <NavLink
                                to={`/bereich/${currentArea.id}`}
                                aria-label={t('Übersicht des Bereichs {area}', {
                                  area: currentArea.label,
                                })}
                              >
                                {menuTitle}
                              </NavLink>
                            ) : (
                              menuTitle
                            )}
                          </h2>
                          <ul aria-labelledby="bereichsmenue-titel">
                            {memberCurrent?.links.map((l) => (
                              <li key={l.to}>
                                <NavLink
                                  to={l.to}
                                  end={l.to === '/mein-bereich'}
                                  className="sidebar-link"
                                  onClick={choseInNav}
                                >
                                  <span>{l.label}</span>
                                </NavLink>
                              </li>
                            ))}
                            {(memberNav ? [] : (currentArea?.items ?? [])).map((m) =>
                              flat(m) ? (
                                <li key={m.id} className="area-menu-flat">
                                  <SubNavList
                                    nodes={moduleTree(m)}
                                    pathname={pathname}
                                    onChoose={choseInNav}
                                  />
                                </li>
                              ) : (
                                <li key={m.id}>
                                  <NavLink
                                    to={moduleLink(m)}
                                    end={m.path === '/'}
                                    className="sidebar-link"
                                    onClick={choseInNav}
                                  >
                                    <span>{moduleLabel(m)}</span>
                                  </NavLink>
                                  {inModule(m) && (
                                    <SubNavList
                                      nodes={moduleTree(m)}
                                      pathname={pathname}
                                      onChoose={choseInNav}
                                    />
                                  )}
                                </li>
                              ),
                            )}
                          </ul>
                        </div>
                      )}
                    </>
                  )}
                </nav>
                <div className="sidebar-backdrop" aria-hidden="true" onClick={closeNav} />
                {narrow && (
                  // Handy und Tablet: die wichtigsten Bereiche unten im Daumenbereich, „Mehr“
                  // öffnet das ganze Menü (Design „Frisch“ D3, konzepte/design-frisch.md)
                  <nav
                    className="bottom-nav"
                    aria-label={t('Schnellwahl')}
                    inert={navOpen || undefined}
                  >
                    {memberNav?.map((a) => (
                      <Link
                        key={a.id}
                        to={a.links[0].to}
                        className={`bottom-nav-link${a.id === memberCurrent?.id ? ' active' : ''}`}
                        aria-current={a.id === memberCurrent?.id ? 'true' : undefined}
                      >
                        {a.icon}
                        <span>{a.label}</span>
                      </Link>
                    ))}
                    {(memberNav ? [] : bottomNav).map((m) => (
                      <NavLink
                        key={m.id}
                        to={m.linkFor?.(active, ws) ?? m.path}
                        end={m.path === '/'}
                        className="bottom-nav-link"
                      >
                        {m.icon}
                        <span>
                          {m.id === 'start' ? t('Start') : (m.labelFor?.(active, ws) ?? m.label)}
                        </span>
                      </NavLink>
                    ))}
                    <button
                      type="button"
                      className="bottom-nav-link"
                      aria-controls="hauptnavigation"
                      aria-expanded={navOpen}
                      onClick={() => setNavOpen(true)}
                    >
                      <svg
                        viewBox="0 0 24 24"
                        width="20"
                        height="20"
                        aria-hidden="true"
                        fill="none"
                        stroke="currentColor"
                        strokeWidth="2"
                        strokeLinecap="round"
                      >
                        <path d="M4 7h16M4 12h16M4 17h16" />
                      </svg>
                      <span>{t('Mehr')}</span>
                    </button>
                  </nav>
                )}

                <main className="content" id="inhalt" tabIndex={-1} inert={navOpen || undefined}>
                  {previewOrg && <RolePreviewBanner org={previewOrg} onChanged={previewChanged} />}
                  <OfflineBanner />
                  {user?.mfa_platform && <MfaPlatformNotice />}
                  {user?.mfa_required_by && (
                    <MfaNotice by={user.mfa_required_by} overdue={!!user.mfa_overdue} />
                  )}
                  {/* Verwalter (Rechte in einer Einheit) sehen nach einem Release-Update „Das ist neu“ */}
                  {orgs.length > 0 && !previewOrg && <UpdateNotice />}
                  {/* Betreiber: neueres Release verfügbar (tägliche Prüfung, abschaltbar) */}
                  {!previewOrg &&
                    orgs.some(
                      (o) => o.type === 'platform' && o.permissions.includes(PERM.platformManage),
                    ) && <NewReleaseNotice />}
                  {loading ? (
                    <p className="muted" role="status">
                      {t('Wird geladen …')}
                    </p>
                  ) : (
                    <PageErrorBoundary resetKey={pathname}>
                      <Suspense
                        fallback={
                          <p className="muted" role="status">
                            {t('Wird geladen …')}
                          </p>
                        }
                      >
                        <Outlet key={`${version}-${previewVersion}`} />
                      </Suspense>
                    </PageErrorBoundary>
                  )}
                  <AppFooter />
                </main>
                <HelpPanel />
              </div>
            </HelpProvider>
          </LearningProvider>
        </PageSlotProvider>
      </NavTrailContext.Provider>
    </SubNavContext.Provider>
  )
}

/**
 * Pflicht-2FA für heikle Rechte (Gesamtaudit 31.10.b, Frage 1). W-07 (UX-Audit 08.11.): ein
 * Hinweismuster auf allen Seiten, gleiche Kurzfassung, die Begründung hinter „Mehr erfahren“.
 */
function MfaPlatformNotice() {
  return (
    <div className="alert alert-error mfa-hint" role="status">
      <p>
        {t('Die Plattform-Verwaltung ruht, bis du die Zwei-Faktor-Anmeldung einrichtest.')}{' '}
        <NavLink to="/mein-konto/anmeldung#zwei-faktor">{t('Jetzt einrichten')}</NavLink>
      </p>
    </div>
  )
}

function MfaNotice({ by, overdue }: { by: string; overdue: boolean }) {
  const date = new Date(by).toLocaleDateString(locale())
  return (
    <div className={`alert ${overdue ? 'alert-error' : 'alert-info'} mfa-hint`} role="status">
      <p>
        {overdue
          ? t('Zwei-Faktor-Anmeldung fehlt: Deine Verwaltungsrechte ruhen.')
          : t(
              'Zwei-Faktor-Anmeldung nötig ab {date}. Rundschreiben, Exporte und das Buchen in der Kasse ruhen schon jetzt.',
              { date },
            )}{' '}
        <NavLink to="/mein-konto/anmeldung#zwei-faktor">{t('Jetzt einrichten')}</NavLink>
      </p>
      <details>
        <summary>{t('Mehr erfahren')}</summary>
        <p className="small">
          {overdue
            ? t(
                'Alle Rechte in Verein und Abteilungen ruhen, bis du die Zwei-Faktor-Anmeldung einrichtest. Dein eigener Mitgliederbereich und „Mein Konto“ gehen weiter.',
              )
            : t(
                'Für deine Rechte brauchst du ab dem {date} die Zwei-Faktor-Anmeldung. Bis dahin ruhen schon Rundschreiben, Exporte und das Buchen in der Kasse.',
                { date },
              )}
        </p>
      </details>
    </div>
  )
}
