// Haushalt und Firma in der Mitgliedsakte (Konzept Familien, Haushalte und Firmen, H1).
import { Link } from 'react-router-dom'
import type { HouseholdRole, MemberHousehold } from '../../api/households.ts'
import { formatDate } from '../../components/forms.ts'
import { t } from '../../i18n/index.ts'

const ROLE: Record<HouseholdRole, string> = {
  adult: t('Erwachsener'),
  child: t('Kind'),
  '': '',
}

export function MemberHouseholds({ households }: { households: MemberHousehold[] }) {
  return (
    <section className="card card-wide" aria-labelledby="haushalt-titel">
      <h2 id="haushalt-titel">{t('Haushalt und Firma')}</h2>
      <ul className="plain-list stack">
        {households.map((h) => (
          <li key={h.id}>
            <strong>
              <Link to="/mitglieder/haushalte">{h.name}</Link>
            </strong>
            <span className="muted small">
              {' · '}
              {h.kind === 'family' ? t('Familie/Haushalt') : t('Firma')}
              {h.role && ` · ${ROLE[h.role]}`}
              {' · '}
              {t('seit {date}', { date: formatDate(h.since) })}
            </span>
            {h.others.length > 0 && (
              <>
                <br />
                <span>
                  {t('Außerdem:')}{' '}
                  {h.others.map((o, i) => (
                    <span key={o.member_id}>
                      {i > 0 && ', '}
                      <Link to={`/mitglieder/${o.member_id}`}>{o.name}</Link>
                    </span>
                  ))}
                </span>
              </>
            )}
          </li>
        ))}
      </ul>
    </section>
  )
}
