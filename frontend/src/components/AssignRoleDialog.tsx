// Rolle besetzen: ein Dialog für Mitglieder › Ämter und die Mitgliederakte (Rollen-Vorschlag R2).
// Er nennt vorher, was passiert, und beendet auf Wunsch die Amtszeit des Vorgängers.
import { useState } from 'react'
import type { FormEvent } from 'react'
import { Link } from 'react-router-dom'
import { todayIso } from '../api/members.ts'
import type { PickedMember } from '../api/members.ts'
import { orgApi } from '../api/orgs.ts'
import type { Assignment, Role } from '../api/orgs.ts'
import { errorMessage, formatDate } from './forms.ts'
import { MemberPicker } from './MemberPicker.tsx'
import { Modal } from './Modal.tsx'
import { Alert, Checkbox, Field, SelectField } from './ui.tsx'
import { t } from '../i18n/index.ts'

function holderName(a: Assignment) {
  return a.person_name || a.user_name || a.user_email
}

/** Vortag eines Datums (JJJJ-MM-TT), wie im Backend beim Beenden des Vorgängers */
function dayBefore(iso: string) {
  const d = new Date(`${iso}T12:00:00`)
  d.setDate(d.getDate() - 1)
  return d.toISOString().slice(0, 10)
}

export function AssignRoleDialog({
  orgId,
  roles,
  assignments,
  role: initialRole,
  suggestedRole,
  from: initialFrom,
  member: fixedMember,
  onClose,
  onDone,
}: {
  orgId: number
  roles: Role[]
  /** heutige Amtszeiten, um Vorgänger zu nennen */
  assignments: Assignment[]
  role?: number
  /** vorgeschlagene Rolle; anders als `role` bleibt sie in der Auswahl änderbar */
  suggestedRole?: number
  /** Beginn der Amtszeit (sonst heute), etwa das Datum der Wahl */
  from?: string
  /** feste Person (Mitgliederakte); sonst Auswahl aus der Mitgliederliste */
  member?: PickedMember
  onClose: () => void
  onDone: () => Promise<void> | void
}) {
  const [roleId, setRoleId] = useState(initialRole ?? suggestedRole ?? roles[0]?.id ?? 0)
  const [member, setMember] = useState<PickedMember | null>(fixedMember ?? null)
  const [email, setEmail] = useState(fixedMember?.email ?? '')
  const [from, setFrom] = useState(initialFrom ?? todayIso)
  const [endPrevious, setEndPrevious] = useState(true)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [result, setResult] = useState<Assignment | null>(null)

  const role = roles.find((r) => r.id === roleId)
  const previous = assignments.filter(
    (a) => a.role === roleId && a.is_active && a.user_email !== email.trim().toLowerCase(),
  )
  const hasRights = (role?.permissions.length ?? 0) > 0
  const name = member ? `${member.first_name} ${member.last_name}` : email || t('die Person')

  async function submit(e: FormEvent) {
    e.preventDefault()
    setBusy(true)
    setError(null)
    try {
      const created = await orgApi.createAssignment(orgId, {
        email: email.trim(),
        role: roleId,
        valid_from: from,
        member: member?.id ?? null,
        end_previous: previous.length > 0 && endPrevious,
      })
      setResult(created)
      await onDone()
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setBusy(false)
    }
  }

  if (result) {
    return (
      <Modal title={t('Rolle besetzt')} onClose={onClose}>
        <p>
          {t('{name} hat jetzt die Rolle {role}.', {
            name,
            role: result.role_name,
          })}
        </p>
        {(result.ended ?? []).length > 0 && (
          <p>
            {t('Amtszeit beendet: {names}', {
              names: (result.ended ?? []).join(', '),
            })}
          </p>
        )}
        {result.new_account && (
          <Alert kind={result.invited ? 'info' : 'error'}>
            {result.invited
              ? t('Neues Konto angelegt, die Einladung ist an {email} unterwegs.', {
                  email: result.user_email,
                })
              : t(
                  'Neues Konto angelegt, aber die Einladung an {email} ging nicht hinaus. Die Person kann „Passwort vergessen“ nutzen.',
                  { email: result.user_email },
                )}
          </Alert>
        )}
        {(role?.represents || role?.on_letterhead) && (
          <div className="subcard">
            <p>{t('Bitte prüfen:')}</p>
            <ul className="plain-list">
              {role.represents && (
                <li>
                  <Link to="/einstellungen/impressum">{t('Impressum')}</Link>
                </li>
              )}
              {role.on_letterhead && (
                <li>
                  <Link to="/einstellungen/briefbogen">{t('Briefbogen')}</Link>
                </li>
              )}
            </ul>
          </div>
        )}
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
      <form className="stack" onSubmit={submit}>
        {initialRole === undefined ? (
          <SelectField
            label={t('Rolle')}
            value={roleId}
            onChange={(e) => setRoleId(Number(e.target.value))}
          >
            {roles.map((r) => (
              <option key={r.id} value={r.id}>
                {r.name}
              </option>
            ))}
          </SelectField>
        ) : (
          <p>
            <strong>{role?.name}</strong>
          </p>
        )}
        {fixedMember ? (
          <p>{name}</p>
        ) : (
          <MemberPicker
            orgId={orgId}
            value={member}
            label={t('Person aus der Mitgliederliste')}
            onChange={(m) => {
              setMember(m)
              if (m?.email) setEmail(m.email)
            }}
          />
        )}
        <Field
          label={t('E-Mail-Adresse')}
          type="email"
          required
          value={email}
          hint={t('Für die Anmeldung. Gibt es noch kein Konto, wird eines angelegt.')}
          onChange={(e) => setEmail(e.target.value)}
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
              names: previous.map(holderName).join(', '),
              date: formatDate(dayBefore(from)),
            })}
            checked={endPrevious}
            onChange={setEndPrevious}
          />
        )}
        <div className="subcard" role="note" aria-label={t('Was passiert')}>
          <p className="small">
            {hasRights
              ? t(
                  'Die Rolle hat Rechte in HUBIplan. {name} meldet sich mit dem Konto für {email} an; gibt es noch keins, geht eine Einladung dorthin.',
                  { name, email: email || '…' },
                )
              : t(
                  'Die Rolle hat keine Rechte in HUBIplan. {name} bekommt nur das Amt; ein neues Konto wird nur für die Anmeldung angelegt.',
                  { name },
                )}
          </p>
        </div>
        {error && <Alert kind="error">{error}</Alert>}
        <div className="actions">
          <button type="submit" className="button button-primary" disabled={busy || !roleId}>
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
