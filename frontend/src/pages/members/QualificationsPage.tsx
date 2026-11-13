// Mitglieder › Qualifikationen: maßgebliche Nachweise aller aktuellen Mitglieder, wahlweise nur
// abgelaufene und bald ablaufende, je Art filterbar. Der Link aus „Zu erledigen“ setzt die Filter.
import { Link, useSearchParams } from 'react-router-dom'
import { PERM } from '../../api/orgs.ts'
import { qualificationApi } from '../../api/qualifications.ts'
import { formatDate, useLoad } from '../../components/forms.ts'
import { Alert, Loading } from '../../components/ui.tsx'
import { useActiveOrg } from '../../org/OrgContext.tsx'
import { t } from '../../i18n/index.ts'
import { StatusBadge } from './QualificationsCard.tsx'
import { untilText } from './qualificationText.ts'

export function QualificationsPage() {
  const org = useActiveOrg()
  const [params, setParams] = useSearchParams()
  const stand = params.get('stand') ?? ''
  const art = params.get('art') ?? ''
  const types = useLoad(() => qualificationApi.types(org.id), [org.id])
  const rows = useLoad(
    () => qualificationApi.overview(org.id, { stand, art }),
    [org.id, stand, art],
  )
  const canSetup = org.permissions.includes(PERM.orgEdit)

  function setFilter(key: string, value: string) {
    const next = new URLSearchParams(params)
    if (value) next.set(key, value)
    else next.delete(key)
    setParams(next, { replace: true })
  }

  return (
    <div className="stack">
      <div className="filters">
        <label className="field">
          <span>{t('Stand')}</span>
          <select value={stand} onChange={(e) => setFilter('stand', e.target.value)}>
            <option value="">{t('alle')}</option>
            <option value="bald">{t('abgelaufen oder läuft bald ab')}</option>
          </select>
        </label>
        <label className="field">
          <span>{t('Qualifikation')}</span>
          <select value={art} onChange={(e) => setFilter('art', e.target.value)}>
            <option value="">{t('alle')}</option>
            {(types.data ?? []).map((k) => (
              <option key={k.id} value={k.id}>
                {k.name}
              </option>
            ))}
          </select>
        </label>
      </div>
      {rows.error ? (
        <Alert kind="error">{rows.error}</Alert>
      ) : !rows.data ? (
        <Loading />
      ) : rows.data.length === 0 ? (
        <div className="card">
          <p className="muted">
            {types.data?.length === 0
              ? t('Noch keine Qualifikationen angelegt.')
              : stand
                ? t('Nichts läuft in nächster Zeit ab.')
                : t('Noch bei keinem Mitglied eingetragen. Eingetragen wird in der Mitgliedsakte.')}
          </p>
          {types.data?.length === 0 && canSetup && (
            <p>
              <Link to="/mitglieder/einrichtung/qualifikationen">
                {t('Qualifikationen einrichten')}
              </Link>
            </p>
          )}
        </div>
      ) : (
        <div className="card table-scroll">
          <table className="table">
            <thead>
              <tr>
                <th>{t('Mitglied')}</th>
                <th>{t('Qualifikation')}</th>
                <th>{t('seit')}</th>
                <th>{t('gültig')}</th>
              </tr>
            </thead>
            <tbody>
              {rows.data.map((r) => (
                <tr key={r.id}>
                  <td>
                    <Link to={`/mitglieder/${r.member}`}>
                      {r.last_name}, {r.first_name}
                    </Link>
                  </td>
                  <td>{r.kind_name}</td>
                  <td>{formatDate(r.acquired_on)}</td>
                  <td>
                    {untilText(r.valid_until)} <StatusBadge status={r.status} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
