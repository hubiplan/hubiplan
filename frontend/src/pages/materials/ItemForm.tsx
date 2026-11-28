import { useRef, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { materialApi } from '../../api/materials.ts'
import type { Material, MaterialChoice } from '../../api/materials.ts'
import { errorMessage, useAutoSave } from '../../components/forms.ts'
import { useDraftGuard } from '../../components/leaveGuard.ts'
import { t } from '../../i18n/index.ts'
import { Why } from '../../learning/Aids.tsx'
import { useOrg } from '../../org/OrgContext.tsx'
import { SaveStatus } from '../../components/ui.tsx'
import './materials.css'
import {
  conditionLabel,
  facilityTypeLabel,
  laneLabel,
  ownershipLabel,
  type Stock,
} from './materialsHelpers.ts'
import { MaterialPicker } from './MaterialPicker.tsx'

const LANES: [string, string][] = [
  ['lg10', 'lg10'],
  ['lp10', 'lp10'],
  ['kk50', 'kk50'],
  ['kk100', 'kk100'],
  ['p25', 'p25'],
  ['p50', 'p50'],
  ['vogel', 'vogel'],
]

export function ItemForm({
  stock,
  base,
  item,
  onSaved,
}: {
  stock: Stock
  base: string
  item?: Material
  onSaved?: () => void
}) {
  const navigate = useNavigate()
  const [params] = useSearchParams()
  const facility = stock.kind === 'facility'
  // Schießstand als Art nur mit Modul Schießsport (UX-Audit VW-13)
  const { active: club } = useOrg()
  const shooting = !club || club.modules.includes('shooting')
  // „Bereich anlegen“ auf der Detailseite: ?bereich=<id>&name=<Bezeichnung>
  const parentId = Number(params.get('bereich')) || null
  const initial = {
    title: item?.title ?? '',
    description: item?.description ?? '',
    purpose: item?.purpose ?? '',
    location_kind: (item
      ? item.location_kind === 'unknown'
        ? 'address'
        : item.location_kind
      : facility
        ? parentId
          ? 'facility'
          : 'address'
        : 'member') as 'address' | 'member' | 'facility',
    member: item?.member ?? null,
    facility: item?.facility ?? parentId,
    belongs_to: item?.belongs_to ?? null,
    address: item?.address ?? {
      name: '',
      street: '',
      postal_code: '',
      city: '',
      country: 'Deutschland',
    },
    location_note: item?.location_note ?? '',
    condition: item?.condition ?? 'ready',
    condition_note: item?.condition_note ?? '',
    facility_type: item?.facility_type ?? (parentId ? 'room' : 'building'),
    ownership: item?.ownership ?? '',
    capacity: item?.capacity ?? null,
    lanes: item?.lanes ?? [],
    access_note: item?.access_note ?? '',
  }
  const [values, setValues] = useState(initial)
  const [memberName, setMemberName] = useState(item?.member_name ?? '')
  const [facilityName, setFacilityName] = useState(item?.facility_title ?? params.get('name') ?? '')
  const [belongsName, setBelongsName] = useState(item?.belongs_to_title ?? '')
  const [event, setEvent] = useState<MaterialChoice | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [saved, setSaved] = useState(false)
  const payloadOf = (v: typeof initial) => {
    const payload: Record<string, unknown> = {
      ...v,
      member: v.location_kind === 'member' ? v.member : null,
      facility: v.location_kind === 'facility' ? v.facility : null,
    }
    if (facility) delete payload.belongs_to
    else
      for (const key of ['facility_type', 'ownership', 'capacity', 'lanes', 'access_note'])
        delete payload[key]
    if (facility && v.facility_type !== 'range') payload.lanes = []
    return payload
  }
  // Vorhandenes speichert automatisch: nur, was sich seit dem letzten Speichern geändert hat
  // (unveränderte Mitgliedsreferenzen nicht ohne Mitgliederdatenrecht neu validieren)
  const sent = useRef(payloadOf(initial))
  const version = useRef(item?.version)
  const [, setErrors] = useState<Record<string, string>>({})
  const auto = useAutoSave(
    { values, setErrors, setValues },
    async (_changes, all) => {
      const payload = payloadOf(all)
      const changes = Object.fromEntries(
        Object.entries(payload).filter(
          ([key, value]) => JSON.stringify(value) !== JSON.stringify(sent.current[key]),
        ),
      )
      if (Object.keys(changes).length === 0) return
      const result = await materialApi.update(base, item!.id, {
        ...changes,
        version: version.current,
      })
      sent.current = payload
      version.current = result.version
    },
    { enabled: !!item },
  )
  useDraftGuard(
    !item && !saved && (JSON.stringify(values) !== JSON.stringify(initial) || !!event),
    () => {
      setValues(initial)
      setEvent(null)
    },
  )
  const lanes = values.lanes
  return (
    <>
      <h1>
        {facility
          ? item
            ? t('Raum oder Anlage bearbeiten')
            : t('Raum oder Anlage anlegen')
          : item
            ? t('Material bearbeiten')
            : t('Material anlegen')}
      </h1>
      <form
        className="card material-form"
        onSubmit={async (e) => {
          e.preventDefault()
          if (item) return
          setBusy(true)
          setError(null)
          try {
            const payload = {
              ...payloadOf(values),
              events: event ? [{ event: event.id, kind: event.series ? 'series' : 'event' }] : [],
            }
            const result = await materialApi.create(base, payload)
            setSaved(true)
            if (onSaved) onSaved()
            else navigate(`${stock.root}/${result.id}`)
          } catch (err) {
            setError(errorMessage(err))
          } finally {
            setBusy(false)
          }
        }}
      >
        {item && <SaveStatus auto={auto} />}
        <fieldset disabled={busy}>
          <fieldset className="material-form-section">
            <legend>{t('Grunddaten')}</legend>
            <div className="material-basic-grid">
              <label>
                {t('Bezeichnung')}
                <input
                  required
                  maxLength={200}
                  value={values.title}
                  onChange={(e) => setValues({ ...values, title: e.target.value })}
                />
              </label>
              {facility && (
                <label>
                  {t('Art')}
                  <select
                    value={values.facility_type}
                    onChange={(e) => setValues({ ...values, facility_type: e.target.value })}
                  >
                    {['building', 'room', 'range', 'ground', 'storage', 'other']
                      .filter((v) => v !== 'range' || shooting || values.facility_type === 'range')
                      .map((v) => (
                        <option key={v} value={v}>
                          {facilityTypeLabel(v)}
                        </option>
                      ))}
                  </select>
                </label>
              )}
              <label>
                {t('Kurzbeschreibung')}
                <textarea
                  required
                  maxLength={2000}
                  value={values.description}
                  onChange={(e) => setValues({ ...values, description: e.target.value })}
                />
              </label>
              <label>
                {facility ? t('Nutzung (optional)') : t('Verwendungszweck')}
                <textarea
                  required={!facility && !item?.events?.length && !event}
                  maxLength={2000}
                  value={values.purpose}
                  onChange={(e) => setValues({ ...values, purpose: e.target.value })}
                />
              </label>
            </div>
            {!item && !facility && (
              <details>
                <summary>{t('Termin statt freiem Verwendungszweck')}</summary>
                {event && (
                  <p className="material-selection">
                    <span>{event.title}</span>
                    <button
                      className="button button-ghost"
                      type="button"
                      onClick={() => setEvent(null)}
                    >
                      {t('Entfernen')}
                    </button>
                  </p>
                )}
                <MaterialPicker base={base} kind="event" onSelect={setEvent} />
              </details>
            )}
          </fieldset>
          {facility && (
            <fieldset className="material-form-section">
              <legend>{t('Nutzung und Ausstattung')}</legend>
              <div className="material-basic-grid">
                <label>
                  {t('Kapazität (Personen oder Plätze)')}
                  <input
                    type="number"
                    min={1}
                    max={100000}
                    value={values.capacity ?? ''}
                    onChange={(e) =>
                      setValues({
                        ...values,
                        capacity: e.target.value ? Number(e.target.value) : null,
                      })
                    }
                  />
                </label>
                <label>
                  {t('Eigentum und Nutzung')}
                  <select
                    value={values.ownership}
                    onChange={(e) => setValues({ ...values, ownership: e.target.value })}
                  >
                    <option value="">{t('Keine Angabe')}</option>
                    {['own', 'lease', 'third_party'].map((v) => (
                      <option key={v} value={v}>
                        {ownershipLabel(v)}
                      </option>
                    ))}
                  </select>
                </label>
                <label>
                  {t('Zugangshinweis')}
                  <input
                    maxLength={500}
                    value={values.access_note}
                    onChange={(e) => setValues({ ...values, access_note: e.target.value })}
                  />
                  <small className="muted">
                    {t('Nur für Personen mit Leserecht auf die Infrastruktur sichtbar.')}
                  </small>
                </label>
              </div>
              {values.facility_type === 'range' && (
                <fieldset className="material-lanes">
                  <legend>{t('Schießbahnen')}</legend>
                  {lanes.map((lane, index) => (
                    <div className="material-lane" key={index}>
                      <label>
                        {t('Disziplin')}
                        <select
                          value={lane.facility}
                          onChange={(e) =>
                            setValues({
                              ...values,
                              lanes: lanes.map((l, i) =>
                                i === index ? { ...l, facility: e.target.value } : l,
                              ),
                            })
                          }
                        >
                          {LANES.map(([key]) => (
                            <option key={key} value={key}>
                              {laneLabel(key)}
                            </option>
                          ))}
                        </select>
                      </label>
                      <label>
                        {t('Anzahl')}
                        <input
                          type="number"
                          min={1}
                          max={500}
                          required
                          value={lane.count}
                          onChange={(e) =>
                            setValues({
                              ...values,
                              lanes: lanes.map((l, i) =>
                                i === index ? { ...l, count: Number(e.target.value) } : l,
                              ),
                            })
                          }
                        />
                      </label>
                      <button
                        className="button button-ghost"
                        type="button"
                        onClick={() =>
                          setValues({ ...values, lanes: lanes.filter((_, i) => i !== index) })
                        }
                      >
                        {t('Entfernen')}
                      </button>
                    </div>
                  ))}
                  <button
                    className="button button-ghost"
                    type="button"
                    onClick={() =>
                      setValues({
                        ...values,
                        lanes: [
                          ...lanes,
                          {
                            facility:
                              LANES.map(([k]) => k).find(
                                (k) => !lanes.some((l) => l.facility === k),
                              ) ?? 'lg10',
                            count: 1,
                          },
                        ],
                      })
                    }
                  >
                    {t('Bahnen hinzufügen')}
                  </button>
                </fieldset>
              )}
            </fieldset>
          )}
          <fieldset className="material-form-section">
            <legend>{t('Standort')}</legend>
            <label>
              {t('Standort')}
              <select
                value={values.location_kind}
                onChange={(e) =>
                  setValues({
                    ...values,
                    location_kind: e.target.value as 'address' | 'member' | 'facility',
                  })
                }
              >
                <option value="address">{t('An einer Adresse')}</option>
                {!facility && <option value="member">{t('Bei einem Mitglied')}</option>}
                {stock.infrastructure && (
                  <option value="facility">
                    {facility ? t('Bereich einer Infrastruktur') : t('In einer Infrastruktur')}
                  </option>
                )}
              </select>
            </label>
            {values.location_kind === 'member' ? (
              <>
                <Why k="material_with_member" />
                <p>{memberName || t('Bitte ein Mitglied wählen.')}</p>
                <MaterialPicker
                  base={base}
                  kind="member"
                  onSelect={(m) => {
                    setMemberName(m.title)
                    setValues({ ...values, member: m.id })
                  }}
                />
              </>
            ) : values.location_kind === 'facility' ? (
              <>
                <p>{facilityName || t('Bitte eine Infrastruktur wählen.')}</p>
                <MaterialPicker
                  base={base}
                  kind="facility"
                  onSelect={(m) => {
                    setFacilityName(m.title)
                    setValues({ ...values, facility: m.id })
                  }}
                />
              </>
            ) : (
              <>
                <p className="muted">
                  {facility
                    ? t(
                        'Diese Adresse ist für Personen mit Leserecht auf die Infrastruktur sichtbar.',
                      )
                    : t('Diese Adresse ist für Personen mit Materialleserecht sichtbar.')}
                </p>
                <div className="material-address-grid">
                  {(['name', 'street', 'postal_code', 'city', 'country'] as const).map(
                    (key, index) => (
                      <label
                        key={key}
                        className={['postal_code', 'city'].includes(key) ? '' : 'material-wide'}
                      >
                        {
                          [
                            facility ? t('Name des Ortes') : t('Lagerortbezeichnung'),
                            t('Straße und Hausnummer'),
                            t('Postleitzahl'),
                            t('Ort'),
                            t('Land'),
                          ][index]
                        }
                        <input
                          required={key !== 'name'}
                          maxLength={300}
                          value={values.address[key] ?? ''}
                          onChange={(e) =>
                            setValues({
                              ...values,
                              address: { ...values.address, [key]: e.target.value },
                            })
                          }
                        />
                      </label>
                    ),
                  )}
                </div>
              </>
            )}
            <label>
              {t('Standortzusatz')}
              <input
                maxLength={300}
                value={values.location_note}
                onChange={(e) => setValues({ ...values, location_note: e.target.value })}
              />
            </label>
            {!facility && stock.infrastructure && (
              <div>
                <p>
                  {t('Gehört zu')}:{' '}
                  {values.belongs_to ? belongsName : t('Keiner Infrastruktur zugeordnet')}
                  {!!values.belongs_to && (
                    <>
                      {' '}
                      <button
                        className="button button-ghost"
                        type="button"
                        onClick={() => {
                          setBelongsName('')
                          setValues({ ...values, belongs_to: null })
                        }}
                      >
                        {t('Entfernen')}
                      </button>
                    </>
                  )}
                </p>
                <p className="muted">
                  {t('Zum Beispiel ein Schlüssel, der zum Vereinsheim gehört.')}
                </p>
                <MaterialPicker
                  base={base}
                  kind="facility"
                  onSelect={(m) => {
                    setBelongsName(m.title)
                    setValues({ ...values, belongs_to: m.id })
                  }}
                />
              </div>
            )}
          </fieldset>
          <fieldset className="material-form-section">
            <legend>{t('Zustand')}</legend>
            <label>
              {t('Zustand')}
              <select
                value={values.condition}
                onChange={(e) =>
                  setValues({ ...values, condition: e.target.value as Material['condition'] })
                }
              >
                {['ready', 'limited', 'defective', 'retired'].map((v) => (
                  <option key={v} value={v}>
                    {conditionLabel(v, stock.kind)}
                  </option>
                ))}
              </select>
            </label>
            <label>
              {t('Zustandshinweis')}
              <input
                maxLength={500}
                value={values.condition_note}
                onChange={(e) => setValues({ ...values, condition_note: e.target.value })}
              />
            </label>
          </fieldset>
        </fieldset>
        {values.condition === 'retired' && (
          <p>
            {facility
              ? t('Bitte Bereiche, gelagertes Material und offene Aufgaben vorher klären.')
              : t('Bitte offene Aufgaben und kommende Verwendungen vor dem Aussondern klären.')}
          </p>
        )}
        {error && <p role="alert">{error}</p>}
        <div className="button-row">
          {item ? (
            <button
              className="button"
              type="button"
              onClick={async () => {
                // Schließt erst, wenn alles gespeichert ist
                if (!(await auto.flush())) return
                if (onSaved) onSaved()
                else navigate(stock.root)
              }}
            >
              {t('Schließen')}
            </button>
          ) : (
            <>
              <button className="button button-primary" disabled={busy}>
                {t('Speichern')}
              </button>
              <button
                className="button button-ghost"
                type="button"
                disabled={busy}
                onClick={() => {
                  setSaved(true)
                  if (onSaved) onSaved()
                  else navigate(stock.root)
                }}
              >
                {t('Abbrechen')}
              </button>
            </>
          )}
        </div>
      </form>
    </>
  )
}
