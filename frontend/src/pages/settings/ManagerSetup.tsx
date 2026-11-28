import { useState } from 'react'
import type { FormEvent } from 'react'
import { orgApi, PERM } from '../../api/orgs.ts'
import type { Department } from '../../api/orgs.ts'
import { Alert } from '../../components/ui.tsx'
import { errorMessage } from '../../components/forms.ts'
import { useOrg } from '../../org/OrgContext.tsx'
import { MemberPicker } from '../../components/MemberPicker.tsx'
import type { MemberRow } from '../../api/members.ts'
import { t } from '../../i18n/index.ts'

/** Erste Leitung einer Einheit in einem Schritt einrichten. */
export function ManagerSetup({
  orgId,
  dep,
  inThis,
  onChange,
}: {
  orgId: number
  dep: Department
  inThis: string
  onChange: () => void
}) {
  const { can } = useOrg()
  const [member, setMember] = useState<MemberRow | null>(null)
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState<{ kind: 'success' | 'error'; text: string } | null>(null)
  if (!can(PERM.membersView)) return null

  async function submit(e: FormEvent) {
    e.preventDefault()
    if (!member) return
    setBusy(true)
    setMessage(null)
    try {
      const r = await orgApi.setupUnitManager(orgId, dep.id, member.id)
      const mail =
        r.mail === 'invitation'
          ? t('Eine Einladung zum Festlegen des Passworts ging an {email}.', { email: r.email })
          : r.mail === 'none'
            ? t(
                'Die E-Mail an {email} konnte nicht gesendet werden; bitte später über „Zugang“ in der Mitgliederakte erneut senden.',
                { email: r.email },
              )
            : t('Ein Hinweis zur Anmeldung ging an {email}.', { email: r.email })
      const extra = r.workspace_role
        ? t(' und im Arbeitsbereich die Rolle „{workspace_role}“', {
            workspace_role: r.workspace_role,
          })
        : ''
      setMessage({
        kind: 'success',
        text: t(
          '{first_name} {last_name} hat jetzt die Rolle „{role}“ mit allen Rechten{extra}. {mail}',
          { first_name: member.first_name, last_name: member.last_name, role: r.role, extra, mail },
        ),
      })
      setMember(null)
      onChange()
    } catch (err) {
      setMessage({ kind: 'error', text: errorMessage(err) })
    } finally {
      setBusy(false)
    }
  }

  return (
    <form onSubmit={submit} className="stack" data-testid="unit-manager">
      <h3>{t('Leitung besetzen')}</h3>
      <p className="muted small">
        {t('Gibt einem Mitglied die Rolle „Leitung“ mit allen Rechten in')} {inThis}
        {dep.own_workspace ? t(' (auch für Kasse und Rechnungen)') : ''}{' '}
        {t(
          'und richtet ihm ein Konto ein. Die Person braucht eine E-Mail-Adresse und kann danach selbst weitere Rollen besetzen. Nur nötig, wenn jemand selbst in HUBIplan arbeiten soll; Ämter ohne Konto besetzt du unter „Wer hat welche Rolle?“ mit „Besetzen“.',
        )}
      </p>
      <MemberPicker orgId={orgId} value={member} onChange={setMember} label={t('Mitglied')} />
      <div className="button-row">
        <button type="submit" className="button button-primary" disabled={!member || busy}>
          {t('Leitung besetzen')}
        </button>
      </div>
      {message && <Alert kind={message.kind}>{message.text}</Alert>}
    </form>
  )
}
