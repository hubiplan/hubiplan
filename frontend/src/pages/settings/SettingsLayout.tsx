import { Link, Navigate, Outlet, useLocation } from 'react-router-dom'
import { modules } from '../../modules.tsx'
import { PERM } from '../../api/orgs.ts'
import { Tabs, SectionTitle } from '../../components/ui.tsx'
import { useOrg } from '../../org/OrgContext.tsx'
import { federationAccess } from '../members/access.ts'
import { t } from '../../i18n/index.ts'

export function SettingsLayout() {
  const { active, can } = useOrg()
  const location = useLocation()

  // Persönliche Einstellungen stehen unter „Mein Konto“ (/mein-konto),
  // hier nur die Einstellungen der gewählten Organisation.
  if (!active) return <Navigate to="/" replace />

  // Arbeitsbereich einer Untereinheit: Stammdaten pflegt die Einheit darüber
  const unit = active.type === 'unit'
  // Zwischenüberschriften in der Seitenleiste (Menüprüfung M-11)
  const general = t('Allgemein')
  const legal = t('Recht')
  const access = t('Zugänge')
  const records = t('Daten')
  const items = [
    ...(unit
      ? []
      : [{ to: '/einstellungen/organisation', label: t('Organisation'), section: general }]),
    ...(unit || active.type === 'platform'
      ? []
      : [
          { to: '/einstellungen/bezeichnungen', label: t('Bezeichnungen'), section: general },
          { to: '/einstellungen/vereinsdokumente', label: t('Vereinsdokumente'), section: general },
        ]),
    ...(unit
      ? []
      : [
          { to: '/einstellungen/erscheinungsbild', label: t('Erscheinungsbild'), section: general },
        ]),
    ...(unit || active.type === 'platform'
      ? []
      : [{ to: '/einstellungen/briefbogen', label: t('Briefbogen'), section: general }]),
    // Dachverband ohne Mitgliederzugriff: kein Menüpunkt Mitglieder, die
    // Einrichtung (Zusatzfelder, Jubiläen) bleibt aber erreichbar.
    ...(active.type === 'federation' && !federationAccess(active) && can(PERM.membersView)
      ? [{ to: '/mitglieder/einrichtung', label: t('Mitglieder-Einrichtung'), section: general }]
      : []),
    ...(unit || active.type === 'platform'
      ? []
      : [
          { to: '/einstellungen/impressum', label: t('Impressum'), section: legal },
          { to: '/einstellungen/datenschutz', label: t('Datenschutz'), section: legal },
        ]),
    // Untereinheit mit eigener Webseite: nur deren Datenschutzhinweise
    ...(unit && active.modules.includes('website') && can(PERM.websiteManage)
      ? [{ to: '/einstellungen/datenschutz', label: t('Datenschutz'), section: legal }]
      : []),
    // Untereinheiten stehen als eigener Punkt im Hauptmenü (modules.tsx)
    ...(can(PERM.rolesView) || can(PERM.rolesManage)
      ? [{ to: '/einstellungen/rollen', label: t('Rollen & Benutzer'), section: access }]
      : []),
    ...((active.type === 'federation' || active.type === 'club') && can(PERM.peeringManage)
      ? [{ to: '/einstellungen/verbund', label: t('Verbund'), section: access }]
      : []),
    ...((active.type === 'federation' || active.type === 'club') && can(PERM.rolesManage)
      ? [{ to: '/einstellungen/nextcloud', label: t('Nextcloud'), section: access }]
      : []),
    ...(active.type !== 'platform' &&
    (can(PERM.dataExport) || (active.type === 'club' && can(PERM.orgEdit)))
      ? [{ to: '/einstellungen/datenuebernahme', label: t('Datenübernahme'), section: records }]
      : []),
    ...(can(PERM.auditView)
      ? [
          { to: '/einstellungen/protokoll', label: t('Protokoll'), section: records },
          { to: '/einstellungen/postausgang', label: t('Postausgang'), section: records },
        ]
      : []),
  ]

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
  const { active } = useOrg()
  const links = modules
    .filter((m) => m.visible(active, { dept: null, portal: null }))
    .flatMap((m) =>
      (m.children?.(active) ?? [])
        .filter((c) => c.label === t('Einrichtung'))
        .map((c) => ({ to: c.to, label: `${m.labelFor?.(active) ?? m.label} › ${c.label}` })),
    )
  if (links.length === 0) return null
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
