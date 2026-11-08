import type { MemberDetail } from '../../api/members.ts'
import { todayIso } from '../../api/members.ts'
import { PERM } from '../../api/orgs.ts'
import type { OrgSummary } from '../../api/orgs.ts'
import { cardApi } from '../../api/cards.ts'
import { PageHeader } from '../../components/PageHeader.tsx'
import type { PageAction } from '../../components/PageHeader.tsx'
import { t } from '../../i18n/index.ts'

/**
 * Kopf der Mitgliedsakte (S-03 A2) auf dem einheitlichen Seitenkopf: Name als h1, Foto,
 * Zusatzzeile mit Status, Nummer, Art, Einheiten und Ämtern, Anrufen/E-Mail. Keine
 * Hauptaktion in Primärfarbe, weil die Akte von selbst speichert.
 */
export function MemberHeader({
  org,
  member,
  canEdit,
  tabs,
}: {
  org: OrgSummary
  member: MemberDetail
  canEdit: boolean
  /** sichtbare Reiter der Akte */
  tabs: string[]
}) {
  const organization = member.kind === 'organization'
  const name = organization
    ? [member.last_name, member.organization?.name_suffix].filter(Boolean).join(' – ')
    : `${member.first_name} ${member.last_name}`
  const today = todayIso()
  const running = (from: string, until: string | null) =>
    from <= today && (!until || until >= today)
  const units = [
    ...new Set(
      member.departments
        .filter((d) => running(d.valid_from, d.valid_until))
        .map((d) => d.department_name),
    ),
  ]
  const offices = [
    ...new Set([
      ...member.board_roles
        .filter((r) => running(r.valid_from, r.valid_until))
        .map((r) => r.role_name),
      ...member.department_roles
        .filter((r) => running(r.valid_from, r.valid_until))
        .map((r) => `${r.role_name} (${r.department_name})`),
      ...currentTitles(member),
    ]),
  ]
  const phone = member.contact?.phone?.trim()
  const email = member.contact?.email?.trim()
  const actions: (PageAction | false)[] = [
    org.permissions.includes(PERM.photosManage) &&
      tabs.includes('foto') && {
        label: organization ? t('Logo hochladen') : t('Foto anfordern'),
        to: '?bereich=foto',
      },
    org.permissions.includes(PERM.cardsView) && {
      label: t('Ausweis drucken'),
      href: cardApi.orgPdfUrl(org.id, { mitglied: member.id }),
    },
    canEdit &&
      member.status === 'active' && {
        label: t('Austritt erfassen'),
        to: '?bereich=mitgliedschaft',
      },
    canEdit && {
      label: t('Auskunft und Löschen (Datenschutz)'),
      to: '?bereich=mitgliedschaft',
      danger: member.status === 'former',
    },
  ]

  return (
    <PageHeader
      title={name}
      extra={
        member.photo.approved ? (
          <img src={member.photo.approved.thumbnail_url} alt="" className="member-avatar" />
        ) : (
          <span className="member-avatar member-avatar-initials" aria-hidden="true">
            {initials(member, organization)}
          </span>
        )
      }
      actions={actions}
    >
      <p className="member-facts">
        {[
          organization ? t('Organisation') : null,
          member.status === 'active' ? t('Mitglied') : t('ehemaliges Mitglied'),
          member.club_number ? t('Nr. {x}', { x: member.club_number }) : null,
          member.current_type?.member_type_name ?? null,
          units.length > 0 ? units.join(', ') : null,
          offices.length > 0 ? offices.join(', ') : null,
        ]
          .filter(Boolean)
          .join(' · ')}
      </p>
      {(phone || email) && (
        <div className="button-row">
          {phone && (
            <a className="button button-ghost" href={`tel:${phone.replace(/[^\d+]/g, '')}`}>
              {t('Anrufen')}
            </a>
          )}
          {email && (
            <a className="button button-ghost" href={`mailto:${email}`}>
              {t('E-Mail')}
            </a>
          )}
        </div>
      )}
    </PageHeader>
  )
}

function initials(m: MemberDetail, organization: boolean): string {
  const parts = organization ? m.last_name.split(/\s+/).slice(0, 2) : [m.first_name, m.last_name]
  return parts
    .map((p) => p.trim()[0] ?? '')
    .join('')
    .toLocaleUpperCase()
}

/** Aktuelle Ehrungen (eigene und des Dachverbands) */
function currentTitles(m: MemberDetail): string[] {
  const today = todayIso()
  const all = [...(m.honorary_titles?.own ?? []), ...(m.honorary_titles?.federation ?? [])]
  return all
    .filter((a) => a.valid_from <= today && (!a.valid_until || a.valid_until >= today))
    .map((a) => a.title_name)
}
