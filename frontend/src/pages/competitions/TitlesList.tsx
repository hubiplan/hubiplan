import { Link } from 'react-router-dom'
import { historyApi, type Grant } from '../../api/competitionHistory.ts'
import { t } from '../../i18n/index.ts'
import { grantLine } from './historyHelpers.ts'
import { ManualGrant } from './ManualGrant.tsx'

export function TitlesList({
  org,
  grants,
  canManage,
  defaults = {},
  onChanged,
  heading,
}: {
  org: number
  grants: Grant[]
  canManage: boolean
  defaults?: Partial<Grant>
  onChanged: () => void
  heading?: string
}) {
  async function remove(g: Grant) {
    await historyApi.grants.remove(org, g.id)
    onChanged()
  }
  return (
    <>
      {heading && <h2>{heading}</h2>}
      {grants.length === 0 ? (
        <p className="muted">{t('Noch keine Titel.')}</p>
      ) : (
        <ul className="plain-list">
          {grants.map((g) => (
            <li key={g.id}>
              {g.year}: <strong>{g.name}</strong> · {grantLine(g)}
              {g.competition && (
                <>
                  {' · '}
                  <Link to={`/wettbewerbe/${g.competition}/auswertung`}>{g.competition_title}</Link>
                </>
              )}
              {g.manual && <span className="muted"> · {t('nachgetragen')}</span>}
              {g.manual && canManage && (
                <button
                  type="button"
                  className="button button-ghost button-small"
                  onClick={() => void remove(g)}
                >
                  {t('Entfernen')}
                </button>
              )}
            </li>
          ))}
        </ul>
      )}
      {canManage && <ManualGrant org={org} defaults={defaults} onSaved={onChanged} />}
    </>
  )
}
