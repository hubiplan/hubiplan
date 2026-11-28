import { EditAt, editKey } from '../../components/EditInPlace.tsx'
import { useState } from 'react'
import { Link } from 'react-router-dom'
import { orgApi, PERM } from '../../api/orgs.ts'
import type { CatalogModule, Department, DepartmentChoice, DepartmentRole } from '../../api/orgs.ts'
import { Alert } from '../../components/ui.tsx'
import { errorMessage } from '../../components/forms.ts'
import { useActiveOrg, useOrg } from '../../org/OrgContext.tsx'
import { confirmRoleRemoval } from '../../components/dialog.ts'
import { RoleForm, RoleTable } from '../../components/RoleEditor.tsx'
import { UNIT_ROLE_FIELDS } from '../../components/roles.ts'
import { memberApi, todayIso } from '../../api/members.ts'
import { confirmEndHolder, UnitRoleDialog, UnitRolesTable } from '../../components/UnitRoles.tsx'
import type { UnitHolder, UnitRole } from '../../components/UnitRoles.tsx'
import { t } from '../../i18n/index.ts'

export function DepartmentRolesPanel({
  orgId,
  dep,
  inThis,
  editable,
  catalog,
  onChange,
}: {
  orgId: number
  dep: DepartmentChoice
  inThis: string
  editable: boolean
  catalog: CatalogModule[]
  onChange: () => void
}) {
  const [roleEdit, setRoleEdit] = useState<DepartmentRole | 'new' | null>(null)
  const hasWebsite = useActiveOrg().modules.includes('website')
  return (
    <>
      <div className="card-head">
        <h3>
          {t('Rollen in')} {inThis}
        </h3>
        {editable && roleEdit === null && (
          <button
            type="button"
            className="button button-ghost push-right"
            onClick={() => setRoleEdit('new')}
          >
            {t('Neue Rolle')}
          </button>
        )}
      </div>
      {roleEdit !== null && (
        <EditAt at={roleEdit === 'new' ? null : editKey('unit-role', roleEdit.id)}>
          <RoleForm
            key={roleEdit === 'new' ? 'new' : roleEdit.id}
            role={
              roleEdit === 'new'
                ? null
                : { ...roleEdit, holders: roleEdit.holders.map((h) => h.name) }
            }
            catalog={catalog}
            fields={UNIT_ROLE_FIELDS}
            hasWebsite={hasWebsite}
            readOnly={!editable}
            permissionsOptional
            showPermissions={!!dep.self_managed}
            onSave={(data) =>
              roleEdit === 'new'
                ? orgApi.createDepartmentRole(orgId, dep.id, data)
                : orgApi.updateDepartmentRole(orgId, roleEdit.id, data)
            }
            onDelete={
              roleEdit === 'new' ? undefined : () => orgApi.deleteDepartmentRole(orgId, roleEdit.id)
            }
            confirmDelete={
              roleEdit === 'new'
                ? undefined
                : () =>
                    confirmRoleRemoval(
                      roleEdit.name,
                      roleEdit.holders.map((h) => h.name),
                    )
            }
            onDone={() => {
              setRoleEdit(null)
              onChange()
            }}
            onCancel={() => setRoleEdit(null)}
          />
        </EditAt>
      )}
      <RoleTable
        roles={dep.roles.map((r) => ({ ...r, holders: r.holders.map((h) => h.name) }))}
        catalog={catalog}
        holderLabel={t('Inhaber')}
        noPermissions={t('keine (nur Amt)')}
        showPermissions={!!dep.self_managed}
        editLabel={editable ? t('Bearbeiten') : t('Ansehen')}
        onEdit={(r) => setRoleEdit(dep.roles.find((x) => x.id === r.id) ?? null)}
        slot="unit-role"
        onReorder={
          editable
            ? (ids) => orgApi.reorderDepartmentRoles(orgId, dep.id, ids).then(() => onChange())
            : undefined
        }
        website={hasWebsite}
      />
      <UnitHolders orgId={orgId} dep={dep} onChange={onChange} />
    </>
  )
}

function UnitHolders({
  orgId,
  dep,
  onChange,
}: {
  orgId: number
  dep: Pick<Department, 'id' | 'roles'>
  onChange: () => void
}) {
  const { can } = useOrg()
  const org = useActiveOrg()
  const [assigning, setAssigning] = useState<UnitRole | null>(null)
  const [message, setMessage] = useState<{ kind: 'success' | 'error'; text: string } | null>(null)
  if (dep.roles.length === 0 || !can(PERM.membersView)) return null
  const canEdit = can(PERM.rolesManage)
  const roles: UnitRole[] = dep.roles.map((r) => ({ id: r.id, name: r.name, holders: r.holders }))

  async function end(role: UnitRole, h: UnitHolder) {
    if (!(await confirmEndHolder(role, h))) return
    setMessage(null)
    try {
      await memberApi.endDepartmentRole(orgId, h.membership, h.id, todayIso())
      setMessage({
        kind: 'success',
        text: t('Die Rolle „{name}“ von {name2} ist beendet.', { name: role.name, name2: h.name }),
      })
      onChange()
    } catch (err) {
      setMessage({ kind: 'error', text: errorMessage(err) })
    }
  }

  return (
    <div className="subcard" data-testid="unit-holders">
      <h3>{t('Wer hat welche Rolle?')}</h3>
      <UnitRolesTable
        label={t('Heutige Inhaber')}
        roles={roles}
        canEdit={canEdit}
        onAssign={setAssigning}
        onEnd={(r, h) => void end(r, h)}
      />
      {org.modules.includes('members') && (
        <p className="muted small">
          <Link to={`/mitglieder/aemter?einheit=${dep.id}`}>
            {t('Frühere Amtszeiten unter Mitglieder › Ämter')}
          </Link>
        </p>
      )}
      {message && <Alert kind={message.kind}>{message.text}</Alert>}
      {assigning && (
        <UnitRoleDialog
          orgId={orgId}
          role={assigning}
          submit={(d) =>
            memberApi.addDepartmentRole(orgId, d.member, {
              role: d.role,
              valid_from: d.valid_from,
              end_previous: d.end_previous,
            })
          }
          onClose={() => setAssigning(null)}
          onDone={onChange}
        />
      )}
    </div>
  )
}
