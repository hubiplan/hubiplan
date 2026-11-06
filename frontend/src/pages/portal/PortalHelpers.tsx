// Helferdienste im Mitgliederbereich: freie Schichten, selbst eintragen, absagen, meine Dienste.
import { useState } from 'react'
import { saveBlob } from '../../api/client.ts'
import { portalHelperApi } from '../../api/helpers.ts'
import type { PortalShift } from '../../api/helpers.ts'
import { confirmDialog } from '../../components/dialog.ts'
import { errorMessage, useLoad } from '../../components/forms.ts'
import { LoadError } from '../../components/ui.tsx'
import { locale, t } from '../../i18n/index.ts'

const ZONE = 'Europe/Berlin'

function when(row: { starts_at: string; ends_at: string }) {
  const day = new Date(row.starts_at).toLocaleDateString(locale(), {
    timeZone: ZONE,
    weekday: 'short',
    day: '2-digit',
    month: '2-digit',
  })
  const time = (v: string) =>
    new Date(v).toLocaleTimeString(locale(), { timeZone: ZONE, hour: '2-digit', minute: '2-digit' })
  return `${day} ${time(row.starts_at)}–${time(row.ends_at)}`
}

export function PortalHelpers({ accessId }: { accessId: number }) {
  const { data, error, reload } = useLoad(() => portalHelperApi.list(accessId), [accessId])
  const [busy, setBusy] = useState(false)
  const [failure, setFailure] = useState<string | null>(null)
  if (error) return <LoadError message={error} onRetry={reload} />
  if (!data) return <p role="status">{t('Wird geladen…')}</p>
  const run = async (action: () => Promise<unknown>) => {
    setBusy(true)
    setFailure(null)
    try {
      await action()
      await reload()
    } catch (err) {
      setFailure(errorMessage(err))
    } finally {
      setBusy(false)
    }
  }
  const cancel = async (assignment: number, label: string) => {
    const yes = await confirmDialog({
      title: t('Dienst absagen?'),
      message: label,
      confirmLabel: t('Dienst absagen'),
    })
    if (yes) await run(() => portalHelperApi.cancel(accessId, assignment))
  }
  const action = (shift: PortalShift, label: string, selfSignup: boolean) => {
    if (shift.mine)
      return shift.can_cancel ? (
        <button
          type="button"
          className="button button-ghost"
          disabled={busy}
          aria-label={t('Absagen: {shift}', { shift: label })}
          onClick={() => cancel(shift.mine!, label)}
        >
          {t('Dienst absagen')}
        </button>
      ) : (
        <span className="muted small">{t('Absage nur über die Verwaltung')}</span>
      )
    if (!selfSignup || shift.past || shift.taken >= shift.needed) return null
    return (
      <button
        type="button"
        className="button"
        disabled={busy}
        aria-label={t('Eintragen: {shift}', { shift: label })}
        onClick={() => run(() => portalHelperApi.signup(accessId, shift.id))}
      >
        {t('Mich eintragen')}
      </button>
    )
  }
  return (
    <>
      {failure && <p role="alert">{failure}</p>}
      <section className="card stack">
        <h2>{t('Meine Dienste')}</h2>
        {data.mine.length === 0 ? (
          <p className="muted">{t('Du bist zurzeit für keinen Dienst eingetragen.')}</p>
        ) : (
          <>
            <ul>
              {data.mine.map((m) => (
                <li key={m.id}>
                  <strong>{m.duty}</strong> · {when(m)}
                  {m.location && ` · ${m.location}`} · {m.plan}
                </li>
              ))}
            </ul>
            <div className="button-row">
              <button
                type="button"
                className="button button-ghost"
                disabled={busy}
                onClick={() =>
                  run(async () =>
                    saveBlob(await portalHelperApi.calendar(accessId), 'meine-dienste.ics'),
                  )
                }
              >
                {t('In den Kalender übernehmen')}
              </button>
            </div>
          </>
        )}
      </section>
      {data.plans.length === 0 && (
        <p className="muted">{t('Zurzeit gibt es keinen veröffentlichten Dienstplan.')}</p>
      )}
      {data.plans.map((plan) => (
        <section key={plan.id} className="card stack">
          <h2>
            {plan.title}
            {plan.unit && <span className="badge">{plan.unit}</span>}
          </h2>
          {plan.note && <p style={{ whiteSpace: 'pre-wrap' }}>{plan.note}</p>}
          <p className="muted small">
            {plan.signup === 'self'
              ? t('Trag dich in freie Schichten ein. Absagen kannst du bis {days} Tage vorher.', {
                  days: plan.cancel_days,
                })
              : t('In diesen Plan trägt nur die Verwaltung ein.')}
            {plan.max_shifts
              ? ' ' + t('Höchstens {n} Schichten je Person.', { n: plan.max_shifts })
              : ''}
          </p>
          {plan.duties.map((duty) => (
            <div key={duty.id} className="stack">
              <h3>
                {duty.name}
                {duty.location && <span className="muted"> · {duty.location}</span>}
                {duty.min_age && (
                  <span className="muted"> · {t('ab {age} Jahren', { age: duty.min_age })}</span>
                )}
              </h3>
              <table className="table">
                <thead>
                  <tr>
                    <th>{t('Schicht')}</th>
                    <th>{t('Frei')}</th>
                    <th>{t('Eingetragen')}</th>
                    <th>
                      <span className="sr-only">{t('Aktion')}</span>
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {duty.shifts.map((s) => {
                    const label = `${duty.name} ${when(s)}`
                    return (
                      <tr key={s.id}>
                        <td>
                          {when(s)}
                          {s.note && <div className="muted small">{s.note}</div>}
                        </td>
                        <td>{Math.max(s.needed - s.taken, 0)}</td>
                        <td>{s.names.join(', ')}</td>
                        <td>{action(s, label, plan.signup === 'self')}</td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          ))}
        </section>
      ))}
    </>
  )
}
