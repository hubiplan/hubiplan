import { Suspense, useEffect, useMemo } from 'react'
import { OfflineBanner } from './OfflineBanner.tsx'
import { SubNavContext } from './subnav.ts'
import { SubNavList } from './SubNavList.tsx'
import { formatTitle, useTitleOverride } from './pageTitle.ts'
import { NavTrailContext, navTrail, trailTitle } from './navTrail.ts'
import type { TrailItem } from './navTrail.ts'
import { PageSlotProvider } from './PageHeader.tsx'
import { Link, NavLink, Outlet } from 'react-router-dom'
import { NewMenu } from './NewMenu.tsx'
import { TodoMenu } from './TodoMenu.tsx'
import { actionCatalog, deptCatalog } from './home/roleActions.ts'
import { QuickSearch } from './QuickSearch.tsx'
import { displayName } from '../api/orgs.ts'
import { AppFooter } from './ImprintFooter.tsx'
import { Logo } from './Logo.tsx'
import { UndoControls } from './UndoControls.tsx'
import { PageErrorBoundary } from './PageErrorBoundary.tsx'
import { LearningProvider } from '../learning/LearningContext.tsx'
import { HelpProvider } from '../help/HelpContext.tsx'
import { HelpButton, HelpPanel } from '../help/HelpPanel.tsx'
import { ACCOUNT_PATH, accountSectionLabel } from '../pages/settings/accountNav.ts'
import { AccountMenu } from './AccountMenu.tsx'
import { RolePreviewBanner, RolePreviewSelect } from './RolePreview.tsx'
import { UpdateNotice } from '../news/UpdateNotice.tsx'
import { NewReleaseNotice } from '../news/NewReleaseNotice.tsx'
import { PERM } from '../api/orgs.ts'
import { locale, t } from '../i18n/index.ts'
import { useLayout } from './useLayout.ts'

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
  const {
    user,
    pathname,
    navOpen,
    setNavOpen,
    menuClosed,
    toggleMenu,
    subNav,
    setSub,
    toggleRef,
    navRef,
    topbarRef,
    remoteAccounts,
    narrow,
    closeNav,
    choseInNav,
    undoBase,
    version,
    previewVersion,
    previewOrg,
    previewChanged,
    handleLogout,
    switchOrg,
    twoViews,
    showMemberView,
    showAdminView,
    personal,
    portalInPicker,
    ws,
    bottomNav,
    areas,
    inModule,
    contextCount,
    instance,
    brandName,
    brandLogo,
    brandLogoDark,
    quickPages,
    quickMemberOrg,
    quickEventBase,
    currentModule,
    overviewOf,
    currentArea,
    moduleLabel,
    moduleLink,
    moduleTree,
    flat,
    memberNav,
    memberCurrent,
    railItems,
    railCurrent,
    hasMenu,
    menuTitle,
    orgs,
    departments,
    active,
    activeKey,
    activeDept,
    activePortal,
    loading,
  } = useLayout()
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
