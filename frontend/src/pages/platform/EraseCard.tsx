import { useState } from 'react'
import type { FormEvent } from 'react'
import { platformApi } from '../../api/orgs.ts'
import type { PlatformOrg } from '../../api/orgs.ts'
import { Alert, Field, LoadError } from '../../components/ui.tsx'
import { errorMessage, formatDate, useLoad } from '../../components/forms.ts'
import { t } from '../../i18n/index.ts'

/** Einheit in zwei Stufen löschen (Gesamtaudit 10.11., F02): erst stilllegen und die
 * Löschung vormerken, endgültig löschen erst nach Wartezeit und Aufbewahrungsfristen. */
export function EraseCard({
  org,
  onDone,
}: {
  org: PlatformOrg
  /** Nach jeder Stufe zurück zur Liste (sie zeigt den neuen Stand) */
  onDone: () => Promise<unknown> | void
}) {
  const state = useLoad(() => platformApi.eraseState(org.id), [org.id])
  const [open, setOpen] = useState(false)
  const [confirmation, setConfirmation] = useState('')
  const [confirmedBy, setConfirmedBy] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  function reset() {
    setOpen(false)
    setConfirmation('')
    setConfirmedBy('')
    setError(null)
  }

  async function run(action: () => Promise<unknown>, done: () => Promise<unknown> | void) {
    setBusy(true)
    setError(null)
    try {
      await action()
      reset()
      await done()
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setBusy(false)
    }
  }

  const s = state.data
  const requested = !!s?.requested_at

  function submit(ev: FormEvent) {
    ev.preventDefault()
    if (busy || confirmation !== org.name) return
    if (!requested) {
      void run(() => platformApi.eraseRequest(org.id, confirmation), onDone)
    } else {
      void run(
        () =>
          platformApi.erase(org.id, {
            confirmation,
            confirmed_by: confirmedBy,
          }),
        onDone,
      )
    }
  }

  return (
    <form className="card card-wide" onSubmit={submit}>
      <h2>{t('Einheit löschen')}</h2>
      {state.error && <LoadError message={state.error} onRetry={() => void state.reload()} />}
      {s && !requested && (
        <p>
          {t(
            'Gelöscht wird in zwei Stufen. Zuerst wird die Einheit mit allen Untereinheiten stillgelegt: Niemand kommt mehr hinein, die Daten bleiben erhalten. Endgültig löschen lässt sie sich frühestens {n} Tage später und erst, wenn die Aufbewahrungsfristen für Bücher und Belege abgelaufen sind.',
            { n: s.wait_days },
          )}
        </p>
      )}
      {s && requested && (
        <>
          <p>
            {t('Stillgelegt und zum Löschen vorgemerkt seit {date}.', {
              date: formatDate(s.requested_at),
            })}
            {s.requested_by ? ` ${t('Vorgemerkt von {name}.', { name: s.requested_by })}` : ''}
          </p>
          <ul>
            {s.retention_until ? (
              <li>
                {t('Aufbewahrungsfristen laufen bis {date}.', {
                  date: formatDate(s.retention_until),
                })}
              </li>
            ) : (
              <li>{t('Keine Finanzdaten, keine Aufbewahrungsfrist.')}</li>
            )}
            {s.holds.map((hold) => (
              <li key={`${hold.unit}-${hold.year}`}>
                {t('Löschsperre: {unit}, Geschäftsjahr {year}', hold)}
              </li>
            ))}
            {s.possible_from && (
              <li>
                {t('Endgültig löschen frühestens ab {date}.', {
                  date: formatDate(s.possible_from),
                })}
              </li>
            )}
          </ul>
          {!s.can_erase && s.blockers.length > 0 && (
            <Alert kind="info">{s.blockers.join(' ')}</Alert>
          )}
        </>
      )}
      {s && open && (
        <>
          <p>
            {requested
              ? t(
                  'Die Einheit, alle Untereinheiten und ihre Daten einschließlich Mitgliedern, Rollen, Finanzdaten und Dateien werden unwiderruflich gelöscht. Benutzerkonten bleiben erhalten. Auch ein später eingespieltes älteres Backup bringt sie nicht zurück.',
                )
              : t('Die Einheit wird sofort stillgelegt. Die Vormerkung lässt sich zurücknehmen.')}
          </p>
          <p>
            {t('Zur Bestätigung den vollständigen Namen eingeben:')} <strong>{org.name}</strong>
          </p>
          <Field
            label={t('Name zur Löschbestätigung')}
            value={confirmation}
            onChange={(ev) => setConfirmation(ev.target.value)}
          />
          {requested && (
            <>
              {s.has_finance && (
                <Field
                  label={t('Fristen bestätigt von')}
                  hint={t('Zum Beispiel Kassenprüfer oder Steuerberater, mit Datum.')}
                  value={confirmedBy}
                  onChange={(ev) => setConfirmedBy(ev.target.value)}
                />
              )}
            </>
          )}
        </>
      )}
      {error && <Alert kind="error">{error}</Alert>}
      {s && (
        <div className="button-row">
          {open ? (
            <>
              <button
                type="submit"
                className="button button-danger"
                disabled={
                  busy ||
                  confirmation !== org.name ||
                  (requested && s.has_finance && !confirmedBy.trim())
                }
              >
                {requested ? t('Unwiderruflich löschen') : t('Stilllegen und vormerken')}
              </button>
              <button type="button" className="button" disabled={busy} onClick={reset}>
                {t('Abbrechen')}
              </button>
            </>
          ) : (
            <>
              {(!requested || s.can_erase) && (
                <button
                  type="button"
                  className="button button-danger"
                  onClick={() => setOpen(true)}
                >
                  {requested ? t('Endgültig löschen') : t('Stilllegen und Löschung vormerken')}
                </button>
              )}
              {requested && (
                <button
                  type="button"
                  className="button"
                  disabled={busy}
                  onClick={() => void run(() => platformApi.eraseWithdraw(org.id), onDone)}
                >
                  {t('Vormerkung zurücknehmen')}
                </button>
              )}
            </>
          )}
        </div>
      )}
    </form>
  )
}
