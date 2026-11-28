import { useState } from 'react'
import { peeringApi } from '../../api/peering.ts'
import type { Coupling } from '../../api/peering.ts'
import { errorMessage, formatDate } from '../../components/forms.ts'
import { Alert } from '../../components/ui.tsx'
import { useActiveOrg } from '../../org/OrgContext.tsx'
import { t } from '../../i18n/index.ts'

export function RegisterCard({ coupling, onChange }: { coupling: Coupling; onChange: () => void }) {
  const org = useActiveOrg()
  const reg = coupling.register!
  const [err, setErr] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  async function resolve(member: number, person: number | null) {
    setErr(null)
    setBusy(true)
    try {
      await peeringApi.resolve(org.id, coupling.id, member, person)
      onChange()
    } catch (e) {
      setErr(errorMessage(e))
    } finally {
      setBusy(false)
    }
  }

  async function decide(member: number, apply: boolean) {
    setErr(null)
    setBusy(true)
    try {
      await peeringApi.decideCorrection(org.id, coupling.id, member, apply)
      onChange()
    } catch (e) {
      setErr(errorMessage(e))
    } finally {
      setBusy(false)
    }
  }

  const fieldLabel = {
    last_name: t('Nachname'),
    first_name: t('Vorname'),
    birth_date: t('Geburtsdatum'),
  }
  const shown = (field: string, value?: string) =>
    !value ? '–' : field === 'birth_date' ? formatDate(value) : value

  return (
    <div>
      <h4>{t('Namentliche Meldung')}</h4>
      <p className="muted small">
        {reg.counts.active} {t('gemeldet')}
        {reg.counts.withdrawn > 0 &&
          t(' · {withdrawn} nicht mehr gemeldet (nur Minimum)', {
            withdrawn: reg.counts.withdrawn,
          })}
        {reg.counts.unclear > 0 && t(' · {unclear} Klärfälle', { unclear: reg.counts.unclear })}
        {t('. Die Personen stehen in der Mitgliederliste des Dachverbands unter')}{' '}
        {coupling.remote.name}.
      </p>
      {reg.unclear.map((u) => (
        <div key={u.id} className="card">
          <p>
            <strong>{[u.first_name, u.last_name].filter(Boolean).join(' ')}</strong>
            {u.birth_date && t(', geboren {x}', { x: formatDate(u.birth_date) })}
            {t(': Ist das dieselbe Person?')}
          </p>
          <ul className="plain-list">
            {u.candidates.map((p) => (
              <li key={p.id}>
                {p.name}
                {p.birth_date && t(', geboren {x}', { x: formatDate(p.birth_date) })}
                {p.member_number &&
                  t(' · Verbandsnr. {member_number}', { member_number: p.member_number })}
                {p.units.length > 0 && t(' · {x}', { x: p.units.join(', ') })}{' '}
                <button
                  type="button"
                  className="link-button"
                  disabled={busy}
                  onClick={() => void resolve(u.id, p.id)}
                >
                  {t('dieselbe Person')}
                </button>
              </li>
            ))}
          </ul>
          <button
            type="button"
            className="button"
            disabled={busy}
            onClick={() => void resolve(u.id, null)}
          >
            {t('Andere Person, neu anlegen')}
          </button>
        </div>
      ))}
      {(reg.corrections ?? []).map((c) => (
        <div key={`b${c.id}`} className="card">
          <p>
            <strong>{c.name}</strong>{' '}
            {t('ist auch in einem anderen Verein Mitglied. Der Verein meldet eine Änderung:')}
          </p>
          <ul className="plain-list">
            {(Object.keys(c.proposed) as (keyof typeof fieldLabel)[]).map((f) => (
              <li key={f}>
                {fieldLabel[f]}: {shown(f, c.current[f])} → {shown(f, c.proposed[f])}
              </li>
            ))}
          </ul>
          <button
            type="button"
            className="button"
            disabled={busy}
            onClick={() => void decide(c.id, true)}
          >
            {t('Änderung übernehmen')}
          </button>{' '}
          <button
            type="button"
            className="link-button"
            disabled={busy}
            onClick={() => void decide(c.id, false)}
          >
            {t('Verwerfen')}
          </button>
        </div>
      ))}
      {reg.conflicts.length > 0 && (
        <Alert kind="info">
          {t('Doppelt aktiv gemeldet:')}{' '}
          {reg.conflicts
            .map((c) =>
              t('{name} (auch aktiv in {active_elsewhere})', {
                name: c.name,
                active_elsewhere: c.active_elsewhere,
              }),
            )
            .join(', ')}
          {t('. Bitte mit den Vereinen klären.')}
        </Alert>
      )}
      {err && <Alert kind="error">{err}</Alert>}
    </div>
  )
}
