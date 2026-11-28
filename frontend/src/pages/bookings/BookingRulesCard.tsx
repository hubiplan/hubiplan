import { useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../../api/client.ts'
import { errorMessage } from '../../components/forms.ts'
import { HowTo } from '../../learning/Aids.tsx'
import { t } from '../../i18n/index.ts'
import { useOrg } from '../../org/OrgContext.tsx'
import './bookings.css'

/** Einstellungen des Buchungskalenders auf der Detailseite eines Objekts. */
export function BookingRulesCard({
  itemBase,
  item,
  editable,
  onSaved,
}: {
  itemBase: string
  item: {
    id: number
    version: number
    booking_rules?: Partial<import('../../api/bookings.ts').BookingRules>
  }
  editable: boolean
  onSaved: () => void
}) {
  const initial = {
    enabled: false,
    approval: false,
    buffer_before: 0,
    buffer_after: 0,
    horizon_days: 365,
    website: 'off' as 'off' | 'busy' | 'titles',
    portal: false,
    price: '',
    price_unit: 'booking' as 'booking' | 'day' | 'hour',
    ...(item.booking_rules ?? {}),
  }
  const [rules, setRules] = useState(initial)
  const { active } = useOrg()
  const billing = active?.modules.includes('billing') ?? false
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  if (!editable && !initial.enabled) return null
  return (
    <section className="card">
      <h2>{t('Buchungskalender')}</h2>
      <HowTo k="how_booking_requests" />
      {initial.enabled && (
        <p>
          <Link to={`/belegung?objekt=${item.id}`}>{t('Belegung ansehen und buchen')}</Link>
        </p>
      )}
      {editable && (
        <form
          onSubmit={async (e) => {
            e.preventDefault()
            setBusy(true)
            setError(null)
            try {
              await api.patch(`${itemBase}${item.id}/`, {
                booking_rules: { ...rules, price: rules.price === '' ? null : rules.price },
                version: item.version,
              })
              onSaved()
            } catch (err) {
              setError(errorMessage(err))
            } finally {
              setBusy(false)
            }
          }}
        >
          <fieldset disabled={busy}>
            <label>
              <input
                type="checkbox"
                checked={rules.enabled}
                onChange={(e) => setRules({ ...rules, enabled: e.target.checked })}
              />{' '}
              {t('Buchungskalender einschalten')}
            </label>
            {rules.enabled && (
              <>
                <label>
                  <input
                    type="checkbox"
                    checked={rules.approval}
                    onChange={(e) => setRules({ ...rules, approval: e.target.checked })}
                  />{' '}
                  {t('Buchungen ohne Freigaberecht sind Anfragen')}
                </label>
                <label>
                  <input
                    type="checkbox"
                    checked={rules.portal}
                    onChange={(e) => setRules({ ...rules, portal: e.target.checked })}
                  />{' '}
                  {t('Mitglieder dürfen im Mitgliederbereich anfragen')}
                </label>
                <div className="booking-times">
                  <label className="field">
                    <span>{t('Rüstzeit vorher (Minuten)')}</span>
                    <input
                      type="number"
                      min={0}
                      max={1440}
                      step={5}
                      value={rules.buffer_before}
                      onChange={(e) =>
                        setRules({ ...rules, buffer_before: Number(e.target.value) })
                      }
                    />
                  </label>
                  <label className="field">
                    <span>{t('Rüstzeit nachher (Minuten)')}</span>
                    <input
                      type="number"
                      min={0}
                      max={1440}
                      step={5}
                      value={rules.buffer_after}
                      onChange={(e) => setRules({ ...rules, buffer_after: Number(e.target.value) })}
                    />
                  </label>
                  <label className="field">
                    <span>{t('Buchbar bis (Tage im Voraus)')}</span>
                    <input
                      type="number"
                      min={1}
                      max={1095}
                      value={rules.horizon_days}
                      onChange={(e) => setRules({ ...rules, horizon_days: Number(e.target.value) })}
                    />
                  </label>
                  <label className="field">
                    <span>{t('Auf der Webseite')}</span>
                    <select
                      value={rules.website}
                      onChange={(e) =>
                        setRules({ ...rules, website: e.target.value as typeof rules.website })
                      }
                    >
                      <option value="off">{t('nicht zeigen')}</option>
                      <option value="busy">{t('nur belegt oder frei')}</option>
                      <option value="titles">{t('mit Zweck öffentlicher Buchungen')}</option>
                    </select>
                  </label>
                  {billing && (
                    <>
                      <label className="field">
                        <span>{t('Mietpreis in Euro (Vorschlag für Rechnungen)')}</span>
                        <input
                          type="number"
                          min={0}
                          step="0.01"
                          value={rules.price}
                          onChange={(e) => setRules({ ...rules, price: e.target.value })}
                        />
                      </label>
                      <label className="field">
                        <span>{t('Mietpreis gilt')}</span>
                        <select
                          value={rules.price_unit}
                          onChange={(e) =>
                            setRules({
                              ...rules,
                              price_unit: e.target.value as typeof rules.price_unit,
                            })
                          }
                        >
                          <option value="booking">{t('je Buchung')}</option>
                          <option value="day">{t('je angefangenen Tag')}</option>
                          <option value="hour">{t('je Stunde')}</option>
                        </select>
                      </label>
                    </>
                  )}
                </div>
              </>
            )}
            <button className="button" disabled={busy}>
              {t('Speichern')}
            </button>
          </fieldset>
          {error && <p role="alert">{error}</p>}
        </form>
      )}
    </section>
  )
}
