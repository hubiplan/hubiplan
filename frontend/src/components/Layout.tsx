import { Suspense, useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { SubNavContext, buildNavTree } from './subnav.ts'
import type { SubNavItem } from './subnav.ts'
import { SubNavList } from './SubNavList.tsx'
import { formatTitle, useTitleOverride } from './pageTitle.ts'
import { NavTrailContext, navTrail, trailTitle } from './navTrail.ts'
import type { TrailItem } from './navTrail.ts'
import { PageSlotProvider } from './PageHeader.tsx'
import { confirmLeave } from './leaveGuard.ts'
import { NavLink, Outlet, useLocation, useNavigate } from 'react-router-dom'
import { useAuth } from '../auth/AuthContext.tsx'
import { GROUP_LABELS, modules } from '../modules.tsx'
import { portalSections } from '../pages/portal/sections.ts'
import { displayName } from '../api/orgs.ts'
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
  const subNavApi = useMemo(() => ({ set: setSub }), [setSub])
  const toggleRef = useRef<HTMLButtonElement>(null)
  const navRef = useRef<HTMLElement>(null)

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
  const [narrow, setNarrow] = useState(
    () => window.matchMedia?.('(max-width: 800px)').matches ?? false,
  )
  // Breiter als der Handy-Umbruch: Navigation steht fest, also zuklappen
  useEffect(() => {
    const wide = window.matchMedia?.('(min-width: 801px)')
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

  // Persönliches im Kontomenü (UX-Audit 10.7); die Auswahl oben zeigt nur Verwaltungsbereiche
  const personal: PersonalArea[] = portal.map((p) => ({
    key: `p:${p.id}`,
    title: portal.length > 1 ? p.club_display_name || p.club_name : undefined,
    links: portalSections(p).flatMap((s) => (s.account ? [{ to: s.to, label: s.account }] : [])),
  }))
  const portalInPicker = portal.filter((p) => activeKey === `p:${p.id}`)

  const ws = { dept: activeDept, portal: activePortal }
  const visible = modules.filter((m) => m.visible(active, ws))
  const modulePaths = (m: (typeof modules)[number]) => [m.path, ...(m.also ?? [])]
  const inModule = (m: (typeof modules)[number]) =>
    modulePaths(m).some((p) => pathname === p || pathname.startsWith(`${p}/`))
  const contextCount =
    orgs.length + departments.length + portalInPicker.length + remoteAccounts.length
  // Im Kopf steht immer der volle Name, der Kurzname nur in der Auswahl.
  // Ohne Einheit: Name und Logo der Instanz (White Label, Vorgabe „HUBIplan“)
  const instance = usePlatform()
  const brandName = active?.name ?? activeDept?.name ?? activePortal?.club_name ?? instance.name
  const brandLogo =
    active?.theme.logo_url ??
    activeDept?.theme.logo_url ??
    activePortal?.theme.logo_url ??
    instance.logo_url

  // Seitentitel im Browser-Tab: Bereich · Arbeitsbereich · HUBIplan (WCAG 2.4.2)
  // Pfad der Seite aus der Menüstruktur (Seitenkopf S-05, W-02): Modul › Unterpunkt ›
  // angemeldeter Unterpunkt der Seite. Seitentitel, h1 und Pfadzeile nutzen ihn.
  const matchesPath = (path: string) => pathname === path || pathname.startsWith(`${path}/`)
  const currentModule = visible
    .filter((m) => modulePaths(m).some(matchesPath))
    .sort((a, b) => b.path.length - a.path.length)[0]
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
      {undoBase && !previewOrg && <UndoControls base={undoBase} />}
      {contextCount > 1 && (
        <label className="org-switch">
          <span className="sr-only">{t('Organisation wechseln')}</span>
          <select
            value={activeKey ?? ''}
            onChange={(e) => void switchOrg(e.target.value)}
            aria-label={t('Organisation wechseln')}
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
                  ? t('Mein Bereich: {member} als Ansprechpartner (', {
                      member: p.member_name ?? '',
                    })
                  : t('Mein Bereich: {first_name} (', { first_name: p.first_name })}
                {p.club_display_name || p.club_name})
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
              <div className={`app-shell${navOpen ? ' nav-open' : ''}`}>
                <a href="#inhalt" className="skip-link">
                  {t('Zum Inhalt springen')}
                </a>
                <header className="topbar" inert={navOpen || undefined}>
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
                    <Logo name={brandName} logoUrl={brandLogo} />
                  </NavLink>
                  <div className="topbar-user">
                    {!narrow && headerTools}
                    {!narrow && <HelpButton />}
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

                <nav className="sidebar" id="hauptnavigation" aria-label={t('Module')} ref={navRef}>
                  <button type="button" className="sidebar-close" onClick={closeNav}>
                    <span aria-hidden="true">×</span> {t('Navigation schließen')}
                  </button>
                  {narrow && <div className="sidebar-tools">{headerTools}</div>}
                  <ul>
                    {visible.map((m, index) => (
                      <li
                        key={m.id}
                        className={
                          index > 0 && visible[index - 1].group !== m.group
                            ? 'sidebar-group-start'
                            : undefined
                        }
                      >
                        {(index === 0 || visible[index - 1].group !== m.group) && (
                          <span className="sidebar-group-label">{GROUP_LABELS[m.group]}</span>
                        )}
                        <NavLink
                          to={m.linkFor?.(active, ws) ?? m.path}
                          end={m.path === '/'}
                          className="sidebar-link"
                          onClick={choseInNav}
                        >
                          {m.icon}
                          <span>
                            {m.id === 'abteilung' && activeDept
                              ? activeDept.label
                              : (m.labelFor?.(active, ws) ?? m.label)}
                          </span>
                        </NavLink>
                        {inModule(m) && (
                          // Unterpunkte; tiefere Ebenen nur unter dem aktiven Punkt, Finanzen
                          // in aufklappbaren Arbeitsgruppen (Konzept S-01)
                          <SubNavList
                            nodes={buildNavTree(
                              m.path,
                              m.children?.(active, ws) ?? [],
                              Object.values(subNav),
                            )}
                            pathname={pathname}
                            onChoose={choseInNav}
                          />
                        )}
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
                </nav>
                <div className="sidebar-backdrop" aria-hidden="true" onClick={closeNav} />

                <main className="content" id="inhalt" tabIndex={-1} inert={navOpen || undefined}>
                  {previewOrg && <RolePreviewBanner org={previewOrg} onChanged={previewChanged} />}
                  {user?.mfa_required_by && (
                    <MfaNotice
                      by={user.mfa_required_by}
                      overdue={!!user.mfa_overdue}
                      short={pathname !== '/' && !pathname.startsWith('/mein-konto')}
                    />
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
                      {t('Lädt …')}
                    </p>
                  ) : (
                    <PageErrorBoundary resetKey={pathname}>
                      <Suspense
                        fallback={
                          <p className="muted" role="status">
                            {t('Lädt …')}
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

/** Pflicht-2FA für heikle Rechte (Gesamtaudit 31.10.b, Frage 1). */
function MfaNotice({ by, overdue, short }: { by: string; overdue: boolean; short: boolean }) {
  const date = new Date(by).toLocaleDateString(locale())
  // W-05: Außer auf der Startseite und in „Mein Konto“ nur eine kurze Zeile, solange die Frist läuft
  if (short && !overdue)
    return (
      <p className="mfa-hint small" role="status">
        {t('Zwei-Faktor-Anmeldung nötig ab {date}.', { date })}{' '}
        <NavLink to="/mein-konto/anmeldung">{t('Jetzt einrichten')}</NavLink>
      </p>
    )
  return (
    <div className={overdue ? 'alert alert-error' : 'alert alert-info'} role="status">
      {overdue
        ? t(
            'Mitgliederdaten, Protokoll, Rollenverwaltung, vollständige Exporte und das Buchen in der Kasse ruhen, bis du die Zwei-Faktor-Anmeldung einrichtest. ',
          )
        : t(
            'Für deine Rechte (Mitglieder, Protokoll, Rollen, Exporte oder Kasse) brauchst du ab dem {date} die Zwei-Faktor-Anmeldung. ',
            { date },
          )}
      <NavLink to="/mein-konto/anmeldung">{t('Jetzt einrichten')}</NavLink>
    </div>
  )
}
