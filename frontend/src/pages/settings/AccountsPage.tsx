// Einstellungen › Konten: wer sich anmelden kann, mit Filtern und Sammelversand
// (Rollen-Vorschlag R4, konzepte/rollen-zugaenge.md).
import { useState } from 'react'
import { Link } from 'react-router-dom'
import { accountsApi } from '../../api/accounts.ts'
import type { Account } from '../../api/accounts.ts'
import { orgApi, PERM } from '../../api/orgs.ts'
import { UsersCard } from './RolesPage.tsx'
import { errorMessage, formatDateTime, useLoad } from '../../components/forms.ts'
import { Alert, LoadError, SelectField } from '../../components/ui.tsx'
import { useActiveOrg, useOrg } from '../../org/OrgContext.tsx'
import { t, tn } from '../../i18n/index.ts'

type Filter = '' | 'rights' | 'never' | 'expired' | 'mfa'

const FILTERS: { value: Filter; label: () => string; test: (a: Account) => boolean }[] = [
  { value: '', label: () => t('alle Konten'), test: () => true },
  { value: 'rights', label: () => t('mit Rechten'), test: (a) => a.rights },
  { value: 'never', label: () => t('nie angemeldet'), test: (a) => a.last_login === null },
  { value: 'expired', label: () => t('Einladung abgelaufen'), test: (a) => a.invitation_expired },
  {
    value: 'mfa',
    label: () => t('ohne Zwei-Faktor trotz Pflicht'),
    test: (a) => a.mfa_missing,
  },
]

export function AccountsPage() {
  const org = useActiveOrg()
  const { can } = useOrg()
  const accounts = useLoad(() => accountsApi.list(org.id), [org.id])
  // Amtszeiten mit Einladung, Zwei-Faktor und Zeitraum je Konto (früher unter Rollen und Rechte)
  const canRoles = can(PERM.rolesView) || can(PERM.rolesManage)
  const roles = useLoad(() => (canRoles ? orgApi.roles(org.id) : Promise.resolve([])), [org.id])
  const assignments = useLoad(
    () => (canRoles ? orgApi.assignments(org.id) : Promise.resolve([])),
    [org.id],
  )
  const [filter, setFilter] = useState<Filter>('')
  const [chosen, setChosen] = useState<Set<number>>(new Set())
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState<{ kind: 'success' | 'error'; text: string } | null>(null)
  const canSend = can(PERM.loginsEdit) || can(PERM.rolesManage)
  const canOpen = can(PERM.membersView)

  if (accounts.error) return <LoadError message={accounts.error} onRetry={accounts.reload} />
  if (!accounts.data) return <p className="muted">{t('Lädt …')}</p>
  const test = FILTERS.find((f) => f.value === filter)!.test
  const rows = accounts.data.filter(test)
  const picked = rows.filter((a) => chosen.has(a.id))
  const allPicked = rows.length > 0 && picked.length === rows.length

  function toggle(id: number, on: boolean) {
    setChosen((old) => {
      const next = new Set(old)
      if (on) next.add(id)
      else next.delete(id)
      return next
    })
  }

  async function resend() {
    setBusy(true)
    setMessage(null)
    try {
      const r = await accountsApi.resend(
        org.id,
        picked.map((a) => a.id),
      )
      const parts = [tn('Gesendet an ein Konto.', 'Gesendet an {n} Konten.', r.sent.length)]
      if (r.skipped.length > 0)
        parts.push(
          t('Nicht gesendet (Passwort schon festgelegt oder kein Recht): {x}', {
            x: r.skipped.join(', '),
          }),
        )
      setMessage({ kind: 'success', text: parts.join(' ') })
      setChosen(new Set())
    } catch (err) {
      setMessage({ kind: 'error', text: errorMessage(err) })
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="stack">
      <div className="card card-wide">
        <h2>{t('Konten')}</h2>
        <p className="muted small">
          {t(
            'Ein Konto ist die Anmeldung einer Person. Hier stehen alle Konten mit Rollen in dieser Einheit und alle, die den Mitgliederbereich nutzen dürfen. Rollen besetzt ihr unter Mitglieder › Ämter, einzelne Konten bearbeitet ihr in der Mitgliederakte.',
          )}
        </p>
        <SelectField
          label={t('Zeigen')}
          value={filter}
          onChange={(e) => {
            setFilter(e.target.value as Filter)
            setChosen(new Set())
          }}
        >
          {FILTERS.map((f) => (
            <option key={f.value} value={f.value}>
              {f.label()}
            </option>
          ))}
        </SelectField>
        <p className="muted small">{tn('Ein Konto', '{n} Konten', rows.length)}</p>
        <div className="table-scroll">
          <table className="table" aria-label={t('Konten')}>
            <thead>
              <tr>
                {canSend && (
                  <th scope="col">
                    <input
                      type="checkbox"
                      aria-label={t('Alle auswählen')}
                      checked={allPicked}
                      onChange={(e) =>
                        setChosen(e.target.checked ? new Set(rows.map((a) => a.id)) : new Set())
                      }
                    />
                  </th>
                )}
                <th scope="col">{t('Name')}</th>
                <th scope="col">{t('E-Mail-Adresse')}</th>
                <th scope="col">{t('Rollen')}</th>
                <th scope="col">{t('Mitgliederbereich')}</th>
                <th scope="col">{t('Letzte Anmeldung')}</th>
                <th scope="col">{t('Zwei-Faktor')}</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((a) => (
                <tr key={a.id}>
                  {canSend && (
                    <td>
                      <input
                        type="checkbox"
                        aria-label={t('{name} auswählen', { name: a.name })}
                        checked={chosen.has(a.id)}
                        onChange={(e) => toggle(a.id, e.target.checked)}
                      />
                    </td>
                  )}
                  <td>
                    {canOpen && a.membership ? (
                      <Link to={`/mitglieder/${a.membership}`}>{a.name}</Link>
                    ) : (
                      a.name
                    )}
                  </td>
                  <td>{a.email}</td>
                  <td>
                    {a.roles.length > 0 ? a.roles.join(', ') : <span className="muted">–</span>}
                  </td>
                  <td>{a.member_area ? t('freigeschaltet') : <span className="muted">–</span>}</td>
                  <td>
                    {a.last_login ? (
                      formatDateTime(a.last_login)
                    ) : (
                      <span className="muted">
                        {a.invitation_expired
                          ? t('nie (Einladung abgelaufen)')
                          : a.awaiting_password
                            ? t('nie (Einladung offen)')
                            : t('nie')}
                      </span>
                    )}
                  </td>
                  <td>
                    {a.has_mfa ? (
                      t('eingerichtet')
                    ) : a.mfa_missing ? (
                      <strong>{t('fehlt (Pflicht)')}</strong>
                    ) : (
                      <span className="muted">–</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {rows.length === 0 && <p className="muted">{t('Keine Konten für diesen Filter.')}</p>}
        {canSend && (
          <div className="button-row">
            <button
              type="button"
              className="button button-primary"
              disabled={busy || picked.length === 0}
              onClick={() => void resend()}
            >
              {t('Anmeldelink erneut senden ({n})', { n: picked.length })}
            </button>
          </div>
        )}
        {canSend && (
          <p className="muted small">
            {t(
              'Konten mit Rolle bekommen eine neue Einladung, solange sie noch kein Passwort festgelegt haben. Konten für den Mitgliederbereich bekommen einen neuen Anmeldelink.',
            )}
          </p>
        )}
        {message && <Alert kind={message.kind}>{message.text}</Alert>}
      </div>
      {canRoles && roles.data && assignments.data && (
        <UsersCard
          orgId={org.id}
          isClub={org.type === 'club' && org.modules.includes('members')}
          roles={roles.data}
          assignments={assignments.data}
          onChange={async () => {
            await Promise.all([assignments.reload(), accounts.reload()])
          }}
          readOnly={!can(PERM.rolesManage)}
        />
      )}
    </div>
  )
}
