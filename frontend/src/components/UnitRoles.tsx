// Rollen einer Untereinheit besetzen (Rollen-Vorschlag R3): dieselbe Ansicht unter
// Mitglieder › Ämter (Filter Einheit), auf der Seite der Untereinheit und im Arbeitsbereich.
import { useState } from 'react'
import type { FormEvent } from 'react'
import { todayIso } from '../api/members.ts'
import type { PickedMember } from '../api/members.ts'
import { confirmDialog } from './dialog.ts'
import { errorMessage, formatDate } from './forms.ts'
import { MemberPicker } from './MemberPicker.tsx'
import { Modal } from './Modal.tsx'
import { Alert, Checkbox, Field } from './ui.tsx'
import { t } from '../i18n/index.ts'

export interface UnitHolder {
  id: number
  membership: number
  name: string
  valid_from: string
}

export interface UnitRole {
  id: number
  name: string
  /** heutige Inhaber */
  holders: UnitHolder[]
}

/** Vortag eines Datums (JJJJ-MM-TT), wie im Backend beim Beenden des Vorgängers */
function dayBefore(iso: string) {
  const d = new Date(`${iso}T12:00:00`)
  d.setDate(d.getDate() - 1)
  return d.toISOString().slice(0, 10)
}

/** Je Rolle die heutigen Inhaber, „Beenden“ und „Besetzen“. */
export function UnitRolesTable({
  label,
  roles,
  canEdit,
  onAssign,
  onEnd,
}: {
  label: string
  roles: UnitRole[]
  canEdit: boolean
  onAssign: (role: UnitRole) => void
  onEnd: (role: UnitRole, holder: UnitHolder) => void
}) {
  if (roles.length === 0) return <p className="muted small">{t('Noch keine Rollen angelegt.')}</p>
  return (
    <div className="table-scroll">
      <table className="table" aria-label={label}>
        <thead>
          <tr>
            <th scope="col">{t('Rolle')}</th>
            <th scope="col">{t('Inhaber')}</th>
            {canEdit && (
              <th scope="col">
                <span className="sr-only">{t('Aktionen')}</span>
              </th>
            )}
          </tr>
        </thead>
        <tbody>
          {roles.map((r) => (
            <tr key={r.id}>
              <td>{r.name}</td>
              <td>
                {r.holders.length === 0 ? (
                  <span className="muted">{t('unbesetzt')}</span>
                ) : (
                  <ul className="plain-list">
                    {r.holders.map((h) => (
                      <li key={h.id}>
                        {h.name}{' '}
                        <span className="muted small">
                          {t('seit {date}', { date: formatDate(h.valid_from) })}
                        </span>
                        {canEdit && (
                          <>
                            {' '}
                            <button
                              type="button"
                              className="link-button"
                              aria-label={t('{role} von {name} beenden', {
                                role: r.name,
                                name: h.name,
                              })}
                              onClick={() => onEnd(r, h)}
                            >
                              {t('Beenden')}
                            </button>
                          </>
                        )}
                      </li>
                    ))}
                  </ul>
                )}
              </td>
              {canEdit && (
                <td className="actions">
                  <button
                    type="button"
                    className="button"
                    aria-label={t('{x} besetzen', { x: r.name })}
                    onClick={() => onAssign(r)}
                  >
                    {t('Besetzen')}
                  </button>
                </td>
              )}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

/** Rückfrage vor dem Beenden einer Amtszeit (endet heute). */
export function confirmEndHolder(role: UnitRole, holder: UnitHolder) {
  return confirmDialog({
    title: t('Rolle „{name}“ von {name2} beenden?', { name: role.name, name2: holder.name }),
    message: t('Die Amtszeit endet heute und bleibt in der Mitgliederakte erhalten.'),
    confirmLabel: t('Beenden'),
  })
}

/** Dialog „Besetzen“ für eine Rolle einer Untereinheit: ohne Konto und ohne E-Mail. */
export function UnitRoleDialog({
  orgId,
  role,
  search,
  submit,
  onClose,
  onDone,
}: {
  orgId: number
  role: UnitRole
  /** eigene Mitgliedersuche (Arbeitsbereich der Untereinheit) */
  search?: (term: string) => Promise<PickedMember[]>
  submit: (data: {
    member: number
    role: number
    valid_from: string
    end_previous: boolean
  }) => Promise<{ ended?: string[] }>
  onClose: () => void
  onDone: () => Promise<void> | void
}) {
  const [member, setMember] = useState<PickedMember | null>(null)
  const [from, setFrom] = useState(todayIso)
  const [endPrevious, setEndPrevious] = useState(true)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [ended, setEnded] = useState<string[] | null>(null)

  const previous = role.holders.filter((h) => h.membership !== member?.id)
  const name = member ? `${member.first_name} ${member.last_name}` : ''

  async function save(e: FormEvent) {
    e.preventDefault()
    if (!member) return
    setBusy(true)
    setError(null)
    try {
      const result = await submit({
        member: member.id,
        role: role.id,
        valid_from: from,
        end_previous: previous.length > 0 && endPrevious,
      })
      setEnded(result.ended ?? [])
      await onDone()
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setBusy(false)
    }
  }

  if (ended !== null) {
    return (
      <Modal title={t('Rolle besetzt')} onClose={onClose}>
        <p>{t('{name} hat jetzt die Rolle {role}.', { name, role: role.name })}</p>
        {ended.length > 0 && <p>{t('Amtszeit beendet: {names}', { names: ended.join(', ') })}</p>}
        <div className="actions">
          <button type="button" className="button button-primary" onClick={onClose}>
            {t('Fertig')}
          </button>
        </div>
      </Modal>
    )
  }

  return (
    <Modal title={t('Rolle besetzen')} onClose={onClose}>
      <form className="stack" onSubmit={save}>
        <p>
          <strong>{role.name}</strong>
        </p>
        <MemberPicker
          orgId={orgId}
          value={member}
          label={t('Person aus der Mitgliederliste')}
          search={search}
          onChange={setMember}
        />
        <Field
          label={t('ab')}
          type="date"
          required
          value={from}
          onChange={(e) => setFrom(e.target.value)}
        />
        {previous.length > 0 && (
          <Checkbox
            label={t('Amtszeit von {names} zum {date} beenden', {
              names: previous.map((h) => h.name).join(', '),
              date: formatDate(dayBefore(from)),
            })}
            checked={endPrevious}
            onChange={setEndPrevious}
          />
        )}
        <p className="muted small">
          {t('Es wird kein Konto angelegt und keine E-Mail verschickt.')}
        </p>
        {error && <Alert kind="error">{error}</Alert>}
        <div className="actions">
          <button type="submit" className="button button-primary" disabled={busy || !member}>
            {t('Besetzen')}
          </button>
          <button type="button" className="button button-ghost" onClick={onClose}>
            {t('Abbrechen')}
          </button>
        </div>
      </form>
    </Modal>
  )
}
