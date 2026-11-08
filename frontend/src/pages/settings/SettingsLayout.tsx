import { Link, Navigate, Outlet, useLocation } from 'react-router-dom'
import { modules } from '../../modules.tsx'
import { PERM } from '../../api/orgs.ts'
import { Tabs, SectionTitle } from '../../components/ui.tsx'
import { useOrg } from '../../org/OrgContext.tsx'
import { settingsItems } from './items.ts'
import { t } from '../../i18n/index.ts'

export function SettingsLayout() {
  const { active } = useOrg()
  const location = useLocation()

  // Persönliche Einstellungen stehen unter „Mein Konto“ (/mein-konto),
  // hier nur die Einstellungen der gewählten Organisation.
  if (!active) return <Navigate to="/" replace />

  const items = settingsItems(active)

  if (location.pathname.replace(/\/$/, '') === '/einstellungen') {
    if (items.length === 0) return <Navigate to="/" replace />
    return <Navigate to={items[0].to} replace />
  }

  return (
    <section>
      <SectionTitle title={t('Einstellungen')} items={items} subtitle={active.name} always />
      <Tabs items={items} />
      <Outlet />
    </section>
  )
}

/**
 * Links zu den Einrichtungen der Module (Menüprüfung M-11, UX-Audit S-02): „Einstellungen“
 * gilt für die ganze Einheit, die Einstellungen eines Bereichs stehen dort unter „Einrichtung“.
 */
export function ModuleSetupLinks() {
  const { active, can } = useOrg()
  // Wo es die Seite „Module“ gibt, stehen die Einrichtungen dort je Modul; hier nur der Weg
  // dorthin, damit es keine zweite Liste gibt (Menüprüfung 2, N-06)
  const modulesPage =
    !!active && (active.type === 'federation' || active.type === 'club') && can(PERM.settingsView)
  const links = modules
    .filter((m) => m.visible(active, { dept: null, portal: null }))
    .flatMap((m) =>
      (m.children?.(active) ?? [])
        .filter((c) => c.label === t('Einrichtung'))
        .map((c) => ({ to: c.to, label: `${m.labelFor?.(active) ?? m.label} › ${c.label}` })),
    )
  if (links.length === 0) return null
  if (modulesPage)
    return (
      <div className="card card-wide">
        <h2>{t('Einrichtung der Bereiche')}</h2>
        <p className="muted small">
          {t('Was nur einen Bereich betrifft, stellst du dort unter „Einrichtung“ ein.')}{' '}
          <Link to="/einstellungen/module">
            {t('Alle Bereiche mit ihrer Einrichtung unter Module')}
          </Link>
        </p>
      </div>
    )
  return (
    <div className="card card-wide">
      <h2>{t('Einrichtung der Bereiche')}</h2>
      <p className="muted small">
        {t('Was nur einen Bereich betrifft, stellst du dort unter „Einrichtung“ ein.')}
      </p>
      <ul className="plain-list">
        {links.map((l) => (
          <li key={l.to}>
            <Link to={l.to}>{l.label}</Link>
          </li>
        ))}
      </ul>
    </div>
  )
}
