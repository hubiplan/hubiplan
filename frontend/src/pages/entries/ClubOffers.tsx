// Sammelanmeldungen beim Dachverband unter Meldungen (Anmeldung A8): kommende Termine des
// Dachverbands, zu denen der Verein Mitglieder gesammelt anmelden kann.
import { Link } from 'react-router-dom'
import { registrationApi } from '../../api/registrations.ts'
import { PERM } from '../../api/orgs.ts'
import { formatDate, useLoad } from '../../components/forms.ts'
import { useActiveOrg } from '../../org/OrgContext.tsx'
import { t } from '../../i18n/index.ts'

export function ClubOffersCard() {
  const org = useActiveOrg()
  const allowed =
    org.type === 'club' &&
    org.modules.includes('registrations') &&
    org.permissions.includes(PERM.registrationsEdit) &&
    org.permissions.includes(PERM.membersView)
  const { data } = useLoad(
    () =>
      allowed
        ? registrationApi.clubOffers(org.id)
        : Promise.resolve({ federation: '', offers: [] }),
    [org.id, allowed],
  )
  if (!data?.offers.length) return null
  return (
    <section className="card card-wide">
      <h2>{t('Sammelanmeldungen beim Dachverband')}</h2>
      <p className="muted">
        {t('Zu diesen Terminen von {name} meldet ihr eure Mitglieder gesammelt an.', {
          name: data.federation,
        })}
      </p>
      <ul className="plain-list">
        {data.offers.map((o) => (
          <li key={o.event_id}>
            <Link to={`/termine?termin=${o.event_id}&datum=${o.starts_at.slice(0, 10)}`}>
              {formatDate(o.starts_at.slice(0, 10))} · {o.title}
            </Link>{' '}
            <span className="muted small">
              {o.state_text}
              {' · '}
              {o.persons === 0 ? t('noch niemand gemeldet') : t('{n} gemeldet', { n: o.persons })}
            </span>
          </li>
        ))}
      </ul>
    </section>
  )
}
