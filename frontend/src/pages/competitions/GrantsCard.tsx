import { useState } from 'react'
import { historyApi, type Grant } from '../../api/competitionHistory.ts'
import type { CompetitionDetail } from '../../api/competitions.ts'
import { PERM } from '../../api/orgs.ts'
import { errorMessage } from '../../components/forms.ts'
import { Alert } from '../../components/ui.tsx'
import { t } from '../../i18n/index.ts'
import { useActiveOrg } from '../../org/OrgContext.tsx'
import { grantLine } from './historyHelpers.ts'

/** Auswertung: vergebene Auszeichnungen und Würdenvorschläge des Wettbewerbs. */
export function GrantsCard({
  org,
  comp,
  onChanged,
}: {
  org: number
  comp: CompetitionDetail
  onChanged: () => void
}) {
  const active = useActiveOrg()
  const [message, setMessage] = useState<{ kind: 'error' | 'success'; text: string } | null>(null)
  const grants = comp.grants ?? []
  if (comp.status !== 'endgueltig' && grants.length === 0) return null
  const canConfirm = active.permissions.includes(PERM.membersEdit)

  async function decide(g: Grant, decision: 'bestaetigen' | 'ablehnen') {
    setMessage(null)
    try {
      await historyApi.grants.decide(org, g.id, decision)
      setMessage({
        kind: 'success',
        text:
          decision === 'bestaetigen'
            ? t('{name} ist als {dignity} {year} eingetragen.', {
                name: g.name,
                dignity: g.dignity_name,
                year: g.year,
              })
            : t('Vorschlag abgelehnt.'),
      })
      onChanged()
    } catch (err) {
      setMessage({ kind: 'error', text: errorMessage(err) })
    }
  }

  async function again() {
    try {
      await historyApi.awards.grantAgain(org, comp.id)
      onChanged()
    } catch (err) {
      setMessage({ kind: 'error', text: errorMessage(err) })
    }
  }

  return (
    <div className="card card-wide">
      <div className="card-head">
        <h2>{t('Vergebene Auszeichnungen')}</h2>
        {comp.can_manage && comp.status === 'endgueltig' && (
          <button
            type="button"
            className="button button-ghost push-right"
            onClick={() => void again()}
          >
            {t('Neu vergeben')}
          </button>
        )}
      </div>
      {grants.length === 0 ? (
        <p className="muted">
          {t('Keine. Auszeichnungen richtet ihr unter „Einrichten“ ein, dann „Neu vergeben“.')}
        </p>
      ) : (
        <ul className="plain-list">
          {grants.map((g) => (
            <li key={g.id}>
              <strong>{g.name}</strong>: {grantLine(g)}
              {g.dignity_state === 'vorschlag' && (
                <>
                  {' · '}
                  {t('Vorschlag: {dignity} {year}', { dignity: g.dignity_name, year: g.year })}{' '}
                  {canConfirm && comp.can_manage && (
                    <button
                      type="button"
                      className="button button-small"
                      onClick={() => void decide(g, 'bestaetigen')}
                    >
                      {t('Würde eintragen')}
                    </button>
                  )}{' '}
                  {comp.can_manage && (
                    <button
                      type="button"
                      className="button button-ghost button-small"
                      onClick={() => void decide(g, 'ablehnen')}
                    >
                      {t('Ablehnen')}
                    </button>
                  )}
                </>
              )}
              {g.dignity_state === 'bestaetigt' && (
                <span className="muted">
                  {' '}
                  · {t('{dignity} eingetragen', { dignity: g.dignity_name })}
                </span>
              )}
              {g.dignity_state === 'abgelehnt' && (
                <span className="muted"> · {t('Würde abgelehnt')}</span>
              )}
            </li>
          ))}
        </ul>
      )}
      {grants.some((g) => g.dignity_state === 'vorschlag') && !canConfirm && (
        <p className="muted small">
          {t('Würden eintragen darf, wer zusätzlich „Mitglieder bearbeiten“ hat.')}
        </p>
      )}
      {message && <Alert kind={message.kind}>{message.text}</Alert>}
    </div>
  )
}
