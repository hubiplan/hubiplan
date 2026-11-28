// Zustand und Abläufe von Layout (Layout.tsx); die Darstellung steht dort.
import { useCallback, useEffect, useRef, useState } from 'react'
import { buildNavTree } from './subnav.ts'
import type { SubNavItem } from './subnav.ts'
import { confirmLeave } from './leaveGuard.ts'
import { useLocation, useNavigate } from 'react-router-dom'
import { useAuth } from '../auth/AuthContext.tsx'
import { getSession } from '../api/auth.ts'
import { bottomNavIds, modules } from '../modules.tsx'
import { areaOf, arrangedAreas } from '../menuLayout.ts'
import { currentMemberArea, memberAreas } from './memberAreas.tsx'
import type { QuickPage } from './QuickSearch.tsx'
import { portalSections } from '../pages/portal/sections.ts'
import { calendarBase } from '../api/events.ts'
import { leaveTo, ssoApi } from '../api/peering.ts'
import type { SsoAccount } from '../api/peering.ts'
import { useOrg } from '../org/OrgContext.tsx'
import { usePlatform } from '../theme/platform.ts'
import { useUndo } from './undo.ts'
import { alertDialog } from './dialog.ts'
import { preloadPagesGently } from '../lazyPages.ts'
import type { PersonalArea } from './AccountMenu.tsx'
import { rolePreviewApi } from '../api/orgs.ts'
import { t } from '../i18n/index.ts'
import { atMost, BP_MEDIUM } from '../theme/breakpoints.ts'

/** Merkt die zuletzt gewählte Einheit der Verwaltung für den Wechsel der Sicht */
const ADMIN_KEY = 'hubiplan.verwaltung'
/** Merkt je Gerät, ob das Bereichsmenü eingeklappt ist */
const MENU_KEY = 'hubiplan.bereichsmenue'
// Je Konto gemerkt: einmal zur Einrichtung der Zwei-Faktor-Anmeldung geführt
const MFA_GUIDE_KEY = 'hubiplan.2fa-gefuehrt'

export function useLayout() {
  const { user, logout, setUser } = useAuth()
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
  // Die Frist entsteht erst, wenn der Server zum ersten Mal Rechte des Kontos prüft, also nach
  // der Anmeldung: Sind die Einheiten geladen, das Konto einmal je Sitzung neu lesen, sonst
  // greift die Führung erst beim nächsten Laden
  const mfaKnown = !!user?.mfa_required_by
  useEffect(() => {
    if (loading || !userId || mfaKnown) return
    const key = `${MFA_GUIDE_KEY}-gelesen:${userId}`
    try {
      if (window.sessionStorage.getItem(key)) return
      window.sessionStorage.setItem(key, '1')
    } catch {
      return
    }
    void getSession()
      .then((next) => {
        if (next?.id === userId && next.mfa_required_by) setUser(next)
      })
      .catch(() => undefined)
  }, [loading, userId, mfaKnown, setUser])
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
  return {
    user,
    logout,
    setUser,
    navigate,
    pathname,
    navOpen,
    setNavOpen,
    mfaDue,
    userId,
    mfaKnown,
    menuClosed,
    setMenuClosed,
    toggleMenu,
    subNav,
    setSubNav,
    setSub,
    toggleRef,
    navRef,
    topbarRef,
    focusAfterClose,
    firstPath,
    remoteAccounts,
    setRemoteAccounts,
    narrow,
    setNarrow,
    closeNav,
    choseInNav,
    undoBase,
    version,
    previewVersion,
    setPreviewVersion,
    previewOrg,
    previewChanged,
    handleLogout,
    switchOrg,
    adminKeys,
    twoViews,
    showMemberView,
    showAdminView,
    personal,
    portalInPicker,
    ws,
    visible,
    bottomNav,
    menuLayout,
    nestedOf,
    nested,
    areas,
    modulePaths,
    inModule,
    contextCount,
    instance,
    brandName,
    brandTheme,
    brandLogo,
    brandLogoDark,
    matchesPath,
    quickPages,
    quickMemberOrg,
    quickEventBase,
    currentModule,
    overviewOf,
    currentArea,
    moduleLabel,
    moduleLink,
    fixedChildren,
    moduleTree,
    flat,
    areaHasMenu,
    memberNav,
    memberCurrent,
    railItems,
    railCurrent,
    hasMenu,
    menuTitle,
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
  }
}
