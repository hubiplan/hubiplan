import { useState } from 'react'
import { EditAt } from '../../components/EditInPlace.tsx'
import { displayName, platformApi } from '../../api/orgs.ts'
import { flatModules, moduleApi } from '../../api/modules.ts'
import type { PlatformOrg } from '../../api/orgs.ts'
import { Alert, Loading } from '../../components/ui.tsx'
import { useLoad } from '../../components/forms.ts'
import { t, tn } from '../../i18n/index.ts'
import { PlatformOrgForm } from './PlatformOrgForm.tsx'
import { ACCESS_LABELS } from './platformHelpers.ts'

/** Freigeschaltete Module als Kennzeichen mit Zählung, aufklappbar (UX-Audit 08.11., W-20 e). */
function ModuleChips({ ids, labels }: { ids: string[]; labels: { id: string; label: string }[] }) {
  if (ids.length === 0) return <div className="muted">{t('keine Module')}</div>
  return (
    <details className="module-chips">
      <summary>{tn('{n} Modul', '{n} Module', ids.length)}</summary>
      <ul className="chips">
        {ids.map((m) => (
          <li key={m} className="chip">
            {labels.find((x) => x.id === m)?.label ?? m}
          </li>
        ))}
      </ul>
    </details>
  )
}

export function PlatformOrgsPage() {
  const { data, error, reload } = useLoad(() => platformApi.orgs(), [])
  const directory = useLoad(() => moduleApi.directory(), [])
  const moduleList = flatModules(directory.data)
  const [editing, setEditing] = useState<PlatformOrg | 'new' | null>(null)

  if (error) return <Alert kind="error">{error}</Alert>
  if (!data) return <Loading />

  const federations = data.filter((o) => o.type === 'federation')
  const clubsOf = (fed: number | null) =>
    data.filter((o) => o.type === 'club' && o.federation === fed)

  if (editing !== null) {
    return (
      <EditAt at={null}>
        <PlatformOrgForm
          org={editing === 'new' ? null : editing}
          parents={federations}
          onDone={async () => {
            setEditing(null)
            await reload()
          }}
          onCancel={() => setEditing(null)}
        />
      </EditAt>
    )
  }

  const row = (o: PlatformOrg, indent = false) => (
    <tr key={o.id} className={o.is_active ? '' : 'inactive'}>
      <td className={indent ? 'indent' : ''}>
        <strong>{displayName(o)}</strong>
        <div className="small muted">
          {o.short_name && t('{name} · ', { name: o.name })}
          {o.type_label} · {o.postal_code} {o.city}
          {!o.is_active && t(' · deaktiviert')}
          {o.erase_requested_at && t(' · zum Löschen vorgemerkt')}
        </div>
      </td>
      <td className="small">
        <div>{o.keeps_members ? t('führt eigene Mitglieder') : t('ohne eigene Mitglieder')}</div>
        {o.type === 'federation' && (
          <div>
            {t('Mitgliedsdaten darunter:')} {ACCESS_LABELS[o.federation_member_access]}
          </div>
        )}
        <ModuleChips ids={o.released_modules ?? o.enabled_modules} labels={moduleList} />
      </td>
      <td className="actions">
        <button type="button" className="link-button" onClick={() => setEditing(o)}>
          {t('Bearbeiten')}
        </button>
      </td>
    </tr>
  )

  return (
    <div className="card card-wide">
      <div className="button-row">
        <button type="button" className="button button-primary" onClick={() => setEditing('new')}>
          {t('Einheit anlegen')}
        </button>
      </div>
      <table className="table">
        <thead>
          <tr>
            <th>{t('Einheit')}</th>
            <th>{t('Freigaben')}</th>
            <th />
          </tr>
        </thead>
        <tbody>
          {federations.flatMap((f) => [row(f), ...clubsOf(f.id).map((c) => row(c, true))])}
          {clubsOf(null).map((c) => row(c))}
        </tbody>
      </table>
    </div>
  )
}
