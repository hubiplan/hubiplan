import type { Coupling, ReceivedCompetition } from '../../api/peering.ts'
import { formatDate } from '../../components/forms.ts'
import { t } from '../../i18n/index.ts'

export function ReceivedInfo({ coupling }: { coupling: Coupling }) {
  const r = coupling.received
  if (!r) return null
  const roles = r.board?.roles ?? []
  return (
    <div className="muted small">
      {r.members && (
        <p>
          {t('Gemeldete Mitglieder am {x}: {total} (', {
            x: formatDate(r.members.on),
            total: r.members.total,
          })}
          {r.members.counts.filter((c) => c.kind === 'active').reduce((a, c) => a + c.n, 0)}{' '}
          {t('aktiv,')}{' '}
          {r.members.counts.filter((c) => c.kind === 'passive').reduce((a, c) => a + c.n, 0)}{' '}
          {t('passiv). Die Beitragsrechnung an diese Einheit nutzt diese Zahlen.')}
        </p>
      )}
      {typeof r.events === 'number' && r.events > 0 && (
        <p>
          {r.events} {t('übermittelte Termine stehen im Kalender.')}
        </p>
      )}
      {r.statute && (
        <p>
          {t('Satzung vom')} {formatDate(r.statute.valid_from)}
          {r.statute.download_url && (
            <>
              {' · '}
              <a href={r.statute.download_url} target="_blank" rel="noreferrer">
                {t('öffnen')}
              </a>
            </>
          )}
        </p>
      )}
      {roles.length > 0 && (
        <ul className="plain-list">
          {roles.map((role) => (
            <li key={role.role}>
              {role.role}: {role.holders.map((h) => h.name).join(', ') || '–'}
              {role.email && t(' · {email}', { email: role.email })}
            </li>
          ))}
        </ul>
      )}
      {r.results && <ReceivedResults competitions={r.results.competitions} />}
    </div>
  )
}

function ReceivedResults({ competitions }: { competitions: ReceivedCompetition[] }) {
  if (competitions.length === 0) {
    return <p>{t('Noch keine endgültigen Wettbewerbsergebnisse übermittelt.')}</p>
  }
  return (
    <details>
      <summary>{t('Wettbewerbsergebnisse von oben: {n}', { n: competitions.length })}</summary>
      {competitions.map((c) => (
        <div key={c.uid}>
          <p>
            <strong>{c.title}</strong> · {formatDate(c.date)}
            {c.location && ` · ${c.location}`}
          </p>
          <ul className="plain-list">
            {c.scorings.map((s) => (
              <li key={s.name}>
                {s.name}:{' '}
                {s.rows.map((row, i) => (
                  <span key={i}>
                    {i > 0 && ', '}
                    {row.own ? <strong>{resultRow(row)}</strong> : resultRow(row)}
                  </span>
                ))}
                {s.field ? ` ${t('(von {n})', { n: s.field })}` : ''}
              </li>
            ))}
          </ul>
        </div>
      ))}
    </details>
  )
}

function resultRow(row: { place: number | null; name: string; value: string }): string {
  const place = row.place ? `${row.place}. ` : ''
  return `${place}${row.name}${row.value ? ` (${row.value})` : ''}`
}
