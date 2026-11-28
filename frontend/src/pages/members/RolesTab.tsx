import { useState } from 'react'
import { memberApi, todayIso } from '../../api/members.ts'
import type { MemberDetail } from '../../api/members.ts'
import { orgApi, PERM } from '../../api/orgs.ts'
import type { OrgSummary } from '../../api/orgs.ts'
import { errorMessage, formatDate, useLoad } from '../../components/forms.ts'
import { Alert } from '../../components/ui.tsx'
import { AssignRoleDialog } from '../../components/AssignRoleDialog.tsx'
import { MemberAccessSection } from '../../components/AccessPanel.tsx'
import { t } from '../../i18n/index.ts'
import { useDepartmentChoices } from '../../components/masterData.ts'
import { MemberFileSection } from './MemberFileSection.tsx'
import { AddWithDate } from './AddWithDate.tsx'

export function RolesTab({
  org,
  member,
  canEdit,
  reload,
}: {
  org: OrgSummary
  member: MemberDetail
  canEdit: boolean
  reload: () => Promise<void>
}) {
  const canEditRoles = org.permissions.includes(PERM.rolesManage)
  const departments = useDepartmentChoices(org.id)
  // Vorstandsrollen besetzen im selben Dialog wie unter Ämter (Rollen-Vorschlag R2)
  const [assigning, setAssigning] = useState(false)
  const roles = useLoad(
    () => (assigning ? orgApi.roles(org.id) : Promise.resolve(null)),
    [org.id, assigning],
  )
  const assignments = useLoad(
    () => (assigning ? orgApi.assignments(org.id) : Promise.resolve(null)),
    [org.id, assigning],
  )
  const [error, setError] = useState<string | null>(null)
  const roleOptions =
    departments.data?.flatMap((d) =>
      d.roles.map((r) => ({
        id: r.id,
        name: t('{name} ({name2})', { name: r.name, name2: d.name }),
      })),
    ) ?? []

  async function run(action: () => Promise<unknown>) {
    setError(null)
    try {
      await action()
      await reload()
    } catch (err) {
      setError(errorMessage(err))
    }
  }

  return (
    <div className="stack">
      {member.status === 'active' &&
        org.permissions.includes(PERM.loginsView) &&
        member.kind === 'organization' && (
          <OrganizationAccess
            orgId={org.id}
            member={member}
            canManage={canEdit && org.permissions.includes(PERM.loginsEdit)}
          />
        )}
      {member.status === 'active' &&
        org.permissions.includes(PERM.loginsView) &&
        member.kind !== 'organization' && (
          <MemberAccessSection
            key={`zugang-${member.id}`}
            orgId={org.id}
            memberId={member.id}
            hasEmail={!!member.contact?.email}
            contactEmail={member.contact?.email}
            canManage={canEdit && org.permissions.includes(PERM.loginsEdit)}
          />
        )}
      <MemberFileSection title={t('Vorstandsrollen')}>
        {member.board_roles.length === 0 ? (
          <p className="muted">{t('Keine.')}</p>
        ) : (
          <ul className="plain-list">
            {member.board_roles.map((r) => (
              <li key={r.id}>
                <strong>{r.role_name}</strong> · {formatDate(r.valid_from)} –{' '}
                {r.valid_until ? formatDate(r.valid_until) : t('heute')}
              </li>
            ))}
          </ul>
        )}
        {canEditRoles && member.status === 'active' && (
          <button type="button" className="button button-ghost" onClick={() => setAssigning(true)}>
            {t('Rolle besetzen')}
          </button>
        )}
      </MemberFileSection>
      {assigning && roles.data && assignments.data && (
        <AssignRoleDialog
          orgId={org.id}
          roles={roles.data}
          assignments={assignments.data}
          member={{
            id: member.id,
            first_name: member.first_name,
            last_name: member.last_name,
            email: member.contact?.email ?? '',
          }}
          onClose={() => setAssigning(false)}
          onDone={reload}
        />
      )}
      <MemberFileSection
        title={t('Rollen in {x}', {
          x: org.department_terms?.pl_dat ?? org.department_label_plural,
        })}
      >
        {member.department_roles.length === 0 ? (
          <p className="muted">{t('Keine.')}</p>
        ) : (
          <ul className="plain-list">
            {member.department_roles.map((r) => (
              <li key={r.id}>
                <strong>{r.role_name}</strong> ({r.department_name}) · {formatDate(r.valid_from)} –{' '}
                {r.valid_until ? formatDate(r.valid_until) : t('heute')}
                {canEditRoles && !r.valid_until && (
                  <button
                    type="button"
                    className="link-button spaced"
                    onClick={() =>
                      void run(() =>
                        memberApi.endDepartmentRole(org.id, member.id, r.id, todayIso()),
                      )
                    }
                  >
                    {t('beenden')}
                  </button>
                )}
              </li>
            ))}
          </ul>
        )}
        {canEditRoles && roleOptions.length > 0 && (
          <AddWithDate
            label={t('Rolle besetzen')}
            options={roleOptions}
            onAdd={(id, date) =>
              run(() =>
                memberApi.addDepartmentRole(org.id, member.id, { role: id, valid_from: date }),
              )
            }
          />
        )}
        {error && <Alert kind="error">{error}</Alert>}
      </MemberFileSection>
    </div>
  )
}

/** Organisationen: ein Zugang je Ansprechpartner statt eines Zugangs für das Mitglied. */
function OrganizationAccess({
  orgId,
  member,
  canManage,
}: {
  orgId: number
  member: MemberDetail
  canManage: boolean
}) {
  const contacts = member.contact_persons ?? []
  if (contacts.length === 0)
    return (
      <div className="card card-wide">
        <h2>{t('Konto und Mitgliederbereich')}</h2>
        <p className="muted">
          {t(
            'Organisationen kommen über ihre Ansprechpartner in den Mitgliederbereich. Bitte zuerst unter „Stammdaten“ einen Ansprechpartner eintragen.',
          )}
        </p>
      </div>
    )
  return (
    <>
      {contacts.map((c) => (
        <MemberAccessSection
          key={`zugang-${member.id}-${c.id}`}
          orgId={orgId}
          memberId={member.id}
          contactId={c.id}
          title={t('Mitgliederbereich für {name}', { name: c.display_name })}
          hasEmail={!!c.contact_email}
          contactEmail={c.contact_email}
          canManage={canManage}
        />
      ))}
    </>
  )
}
