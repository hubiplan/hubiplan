// Sammelanmeldung (Anmeldung A8, Konzept 3.5): Der Verein meldet Mitglieder zu einem Termin
// seines Dachverbands. Die Anmeldung liegt beim Dachverband, die Rechnung geht an den Verein.
import { useState } from 'react'
import type { CalendarBase, EventDetail } from '../../api/events.ts'
import { registrationApi } from '../../api/registrations.ts'
import type { ClubRegistrations, Price } from '../../api/registrations.ts'
import { euro } from '../../api/finance.ts'
import type { PickedMember } from '../../api/members.ts'
import { errorMessage, useLoad } from '../forms.ts'
import { Alert, Checkbox, Loading, SelectField } from '../ui.tsx'
import { MemberPicker } from '../MemberPicker.tsx'
import { confirmDialog } from '../dialog.ts'
import { PaidBadge } from './PaidBadge.tsx'
import { lang, t } from '../../i18n/index.ts'

interface Row {
  member: PickedMember
  price_id: number
}

function priceLabel(p: Price): string {
  const name = lang() === 'en' && p.name_en ? p.name_en : p.name
  return `${name} – ${p.current ? euro(p.current.amount) : t('nicht mehr buchbar')}`
}

export function ClubRegistrationCard({ base, event }: { base: CalendarBase; event: EventDetail }) {
  const { data, error, setData } = useLoad(
    () => registrationApi.club(base, event.id),
    [base, event.id],
  )
  const [rows, setRows] = useState<Row[]>([])
  const [picker, setPicker] = useState<PickedMember | null>(null)
  const [note, setNote] = useState('')
  const [terms, setTerms] = useState(false)
  const [busy, setBusy] = useState(false)
  const [failed, setFailed] = useState<string | null>(null)
  if (error) return <Alert kind="error">{error}</Alert>
  if (!data) return <Loading small />
  const orgId = Number(/\/api\/orgs\/(\d+)\//.exec(base)?.[1] ?? 0)
  const offer = data.offer
  const prices = offer.prices.filter((p) => p.is_active && p.applies !== 'guests' && p.current)
  const open = offer.state === 'open'
  const taken = new Set([...data.registered_members, ...rows.map((r) => r.member.id)])

  function add(m: PickedMember | null) {
    setPicker(null)
    if (!m || taken.has(m.id) || !prices.length) return
    setRows([...rows, { member: m, price_id: prices[0].id }])
  }

  async function run(action: () => Promise<ClubRegistrations>, reset = false) {
    setBusy(true)
    setFailed(null)
    try {
      setData(await action())
      if (reset) {
        setRows([])
        setNote('')
        setTerms(false)
      }
    } catch (e) {
      setFailed(errorMessage(e))
    } finally {
      setBusy(false)
    }
  }

  return (
    <section className="card event-card">
      <h3 className="event-card-title">{t('Sammelanmeldung des Vereins')}</h3>
      <div className="stack-sm">
        <p>
          {offer.state_text}{' '}
          {t('Veranstalter: {name}. Die Rechnung geht an euren Verein.', { name: data.federation })}
        </p>
        {failed && <Alert kind="error">{failed}</Alert>}
        {data.registrations.map((reg) => (
          <div key={reg.id} className="stack-sm">
            <h4>
              {t('Anmeldung {number}', { number: reg.number })}{' '}
              {reg.status === 'cancelled' ? (
                <span className="muted small">{t('abgemeldet')}</span>
              ) : (
                <PaidBadge state={reg.paid_state} />
              )}
            </h4>
            {reg.invoice && (
              <p className="muted small">
                {t('Rechnung {number} über {total}', {
                  number: reg.invoice.number,
                  total: euro(reg.invoice.total),
                })}
              </p>
            )}
            <ul className="plain-list">
              {reg.participants.map((p) => (
                <li key={p.id}>
                  {p.status === 'cancelled' ? <s>{p.name}</s> : p.name}{' '}
                  <span className="muted small">
                    {p.price_name} · {euro(p.amount)}
                  </span>{' '}
                  {p.status === 'active' && reg.can_cancel && (
                    <button
                      type="button"
                      className="button button-ghost"
                      disabled={busy}
                      onClick={async () => {
                        if (
                          await confirmDialog({
                            final: false,
                            title: t('{name} abmelden?', { name: p.name }),
                            confirmLabel: t('Abmelden'),
                          })
                        )
                          void run(() => registrationApi.clubCancel(base, event.id, reg.id, [p.id]))
                      }}
                    >
                      {t('Abmelden')}
                    </button>
                  )}
                </li>
              ))}
            </ul>
          </div>
        ))}
        {open && prices.length > 0 && (
          <div className="stack-sm">
            <h4>{t('Mitglieder anmelden')}</h4>
            <MemberPicker
              orgId={orgId}
              value={picker}
              label={t('Mitglied hinzufügen')}
              onChange={add}
            />
            {rows.map((r, i) => (
              <div key={r.member.id} className="button-row">
                <strong>
                  {r.member.first_name} {r.member.last_name}
                </strong>
                <SelectField
                  label={t('Tarif')}
                  value={r.price_id}
                  onChange={(e) =>
                    setRows(
                      rows.map((x, j) =>
                        j === i ? { ...x, price_id: Number(e.target.value) } : x,
                      ),
                    )
                  }
                >
                  {prices.map((p) => (
                    <option key={p.id} value={p.id}>
                      {priceLabel(p)}
                    </option>
                  ))}
                </SelectField>
                <button
                  type="button"
                  className="button button-ghost"
                  onClick={() => setRows(rows.filter((_, j) => j !== i))}
                >
                  {t('Entfernen')}
                </button>
              </div>
            ))}
            {rows.length > 0 && (
              <>
                <label className="field">
                  <span>{t('Bemerkung (optional)')}</span>
                  <textarea
                    rows={2}
                    maxLength={500}
                    value={note}
                    onChange={(e) => setNote(e.target.value)}
                  />
                </label>
                {offer.terms && (
                  <Checkbox
                    label={t('Die Teilnahmebedingungen habe ich gelesen und akzeptiere sie.')}
                    hint={offer.terms}
                    checked={terms}
                    onChange={setTerms}
                  />
                )}
                <div className="button-row">
                  <button
                    type="button"
                    className="button"
                    disabled={busy || rows.length > data.max_persons || (!!offer.terms && !terms)}
                    onClick={() =>
                      run(
                        () =>
                          registrationApi.clubRegister(base, event.id, {
                            persons: rows.map((r) => ({
                              membership_id: r.member.id,
                              price_id: r.price_id,
                            })),
                            note,
                            terms_accepted: terms,
                          }),
                        true,
                      )
                    }
                  >
                    {t('{n} Personen verbindlich anmelden', { n: rows.length })}
                  </button>
                </div>
              </>
            )}
          </div>
        )}
      </div>
    </section>
  )
}
