import { useEffect, useState } from 'react'
import { Link, Route, Routes, useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { api } from '../../api/client.ts'
import { materialApi } from '../../api/materials.ts'
import type {
  Material,
  MaterialChoice,
  MaterialEvent,
  StockKind,
  StockRow,
} from '../../api/materials.ts'
import { errorMessage, useLoad, useQueryLoad, whenLabel } from '../../components/forms.ts'
import { useDraftGuard } from '../../components/leaveGuard.ts'
import { t, tn, locale } from '../../i18n/index.ts'
import { useOrg } from '../../org/OrgContext.tsx'
import { BookingRulesCard } from '../bookings/BookingsPage.tsx'
import './materials.css'

// Bestand: Material oder Infrastruktur (Schießstand, Schützenhaus, Vereinsheim)
interface Stock {
  kind: StockKind
  // Oberfläche, z. B. /material
  root: string
  // Schnittstelle, z. B. /api/orgs/1/materials/
  base: string
  // Schnittstelle der Einheit, z. B. /api/orgs/1/
  prefix: string
  infrastructure: boolean
  materialView: boolean
}

function stockRoot(kind: StockKind) {
  return kind === 'facility' ? '/infrastruktur' : '/material'
}

export function MaterialsPage({ kind = 'material' }: { kind?: StockKind }) {
  const { active, activeDept } = useOrg()
  const permissions = active?.permissions ?? activeDept?.permissions ?? []
  const has = (module: 'material' | 'infrastructure') =>
    active
      ? active.modules.includes(module)
      : module === 'material'
        ? !!activeDept?.material_enabled
        : !!activeDept?.infrastructure_enabled
  const area = kind === 'facility' ? 'infrastructure' : 'material'
  if (!has(area) || !permissions.includes(`${area}.view`))
    return <p>{t('Dafür fehlt dir die Berechtigung.')}</p>
  const prefix = active ? `/api/orgs/${active.id}/` : `/api/depts/${activeDept!.id}/`
  const stock: Stock = {
    kind,
    root: stockRoot(kind),
    base: `${prefix}${kind === 'facility' ? 'facilities' : 'materials'}/`,
    prefix,
    infrastructure: has('infrastructure'),
    materialView: has('material') && permissions.includes('material.view'),
  }
  const base = stock.base
  const editable = permissions.includes(`${area}.edit`)
  return (
    <div className="materials" key={base}>
      <Routes>
        <Route
          index
          element={
            <MaterialList
              stock={stock}
              base={base}
              editable={editable}
              canExport={permissions.some((p) => ['export.lists', 'export.full'].includes(p))}
            />
          }
        />
        <Route
          path="neu"
          element={
            editable ? (
              <ItemForm stock={stock} base={base} />
            ) : (
              <p>{t('Dafür fehlt dir die Berechtigung.')}</p>
            )
          }
        />
        <Route
          path=":id"
          element={<MaterialDetail stock={stock} base={base} editable={editable} />}
        />
      </Routes>
    </div>
  )
}

function conditionLabel(value: string, kind: StockKind = 'material') {
  if (kind === 'facility')
    return (
      {
        ready: t('Nutzbar'),
        limited: t('Eingeschränkt nutzbar'),
        defective: t('Gesperrt'),
        retired: t('Aufgegeben'),
      }[value] ?? value
    )
  return (
    {
      ready: t('Einsatzbereit'),
      limited: t('Eingeschränkt nutzbar'),
      defective: t('Defekt'),
      retired: t('Ausgesondert'),
    }[value] ?? value
  )
}

function facilityTypeLabel(value: string) {
  return (
    {
      building: t('Gebäude oder Vereinsheim'),
      room: t('Raum'),
      range: t('Schießstand'),
      ground: t('Platz oder Gelände'),
      storage: t('Lager'),
      other: t('Sonstiges'),
    }[value] ?? value
  )
}

function ownershipLabel(value: string) {
  return (
    {
      own: t('Eigentum'),
      lease: t('Pacht oder Miete'),
      third_party: t('Nutzungsrecht bei Dritten'),
    }[value] ?? value
  )
}

const LANES: [string, string][] = [
  ['lg10', 'lg10'],
  ['lp10', 'lp10'],
  ['kk50', 'kk50'],
  ['kk100', 'kk100'],
  ['p25', 'p25'],
  ['p50', 'p50'],
  ['vogel', 'vogel'],
]

function laneLabel(key: string) {
  return (
    {
      lg10: `${t('Luftgewehr')} · 10 m`,
      lp10: `${t('Luftpistole')} · 10 m`,
      kk50: `${t('Kleinkaliber')} · 50 m`,
      kk100: `${t('Kleinkaliber')} · 100 m`,
      p25: `${t('Pistole')} · 25 m`,
      p50: `${t('Pistole')} · 50 m`,
      vogel: t('Vogelschießen · Hochstand'),
    }[key] ?? key
  )
}

function location(item: Material) {
  if (item.location_review) return t('Standort prüfen')
  if (item.location_kind === 'facility')
    return item.kind === 'facility'
      ? t('Bereich von {name}', { name: item.facility_title ?? '' })
      : t('In {name}', { name: item.facility_title ?? '' })
  if (item.location_kind === 'member')
    return item.member_name ? t('Bei {name}', { name: item.member_name }) : t('Bei einem Mitglied')
  return [
    item.address.name,
    item.address.street,
    item.address.postal_code,
    item.address.city,
    item.address.country,
  ]
    .filter(Boolean)
    .join(', ')
}

function MaterialList({
  stock,
  base,
  editable,
  canExport,
}: {
  stock: Stock
  base: string
  editable: boolean
  canExport: boolean
}) {
  const [params, setParams] = useSearchParams()
  const query = params.toString()
  const { data, error, loading } = useLoad(() => materialApi.list(base, query), [base, query])
  const filter = (key: string, value: string) => {
    const next = new URLSearchParams(params)
    if (value) next.set(key, value)
    else next.delete(key)
    if (key !== 'page') next.delete('page')
    setParams(next, { replace: true })
  }
  return (
    <>
      <div className="page-heading">
        <h1>{stock.kind === 'facility' ? t('Infrastruktur') : t('Material')}</h1>
        {editable && (
          <Link className="button" to="neu">
            {stock.kind === 'facility' ? t('Infrastruktur anlegen') : t('Material anlegen')}
          </Link>
        )}
      </div>
      <div className="card material-filters">
        <label>
          {t('Suchen')}
          <input
            type="search"
            value={params.get('q') ?? ''}
            onChange={(e) => filter('q', e.target.value)}
          />
        </label>
        <label>
          {t('Zustand')}
          <select
            value={params.get('condition') ?? ''}
            onChange={(e) => filter('condition', e.target.value)}
          >
            <option value="">{t('Alle')}</option>
            {['ready', 'limited', 'defective', 'retired'].map((v) => (
              <option key={v} value={v}>
                {conditionLabel(v, stock.kind)}
              </option>
            ))}
          </select>
        </label>
        <label>
          <input
            type="checkbox"
            checked={params.get('archived') === '1'}
            onChange={(e) => filter('archived', e.target.checked ? '1' : '')}
          />{' '}
          {stock.kind === 'facility' ? t('Aufgegebene anzeigen') : t('Ausgesonderte anzeigen')}
        </label>
        <label>
          <input
            type="checkbox"
            checked={params.get('trash') === '1'}
            onChange={(e) => filter('trash', e.target.checked ? '1' : '')}
          />{' '}
          {t('Papierkorb')}
        </label>
        <label>
          <input
            type="checkbox"
            checked={params.get('review') === '1'}
            onChange={(e) => filter('review', e.target.checked ? '1' : '')}
          />{' '}
          {t('Nur Prüfhinweise')}
        </label>
        {canExport && (
          <a className="button button-ghost" href={`${base}?${query}&export=1`}>
            {t('Als CSV exportieren')}
          </a>
        )}
        {!!query && (
          <button className="button button-ghost" type="button" onClick={() => setParams({})}>
            {t('Filter zurücksetzen')}
          </button>
        )}
      </div>
      {error && <p role="alert">{error}</p>}
      {loading && <p role="status">{t('Wird geladen…')}</p>}
      {!loading && data?.count === 0 && (
        <p>
          {stock.kind === 'facility'
            ? t('Keine Infrastruktur gefunden.')
            : t('Kein Material gefunden.')}
        </p>
      )}
      <div className="material-grid">
        {data?.items.map((item) => (
          <article className="card" key={item.id}>
            {item.photo_url && !item.deleted_at && (
              <img
                className="material-thumbnail"
                src={item.photo_url}
                alt={item.title}
                loading="lazy"
              />
            )}
            <p className="muted">{item.inventory_number}</p>
            <h2>
              <Link to={`${item.id}${item.deleted_at ? '?trash=1' : ''}`}>{item.title}</Link>
            </h2>
            <p>{item.description}</p>
            {item.facility_type && <p>{facilityTypeLabel(item.facility_type)}</p>}
            <p>{location(item)}</p>
            <p>{conditionLabel(item.condition, stock.kind)}</p>
            {item.next_use && (
              <p>
                {item.next_use.title} · {whenLabel(item.next_use.starts_at, item.next_use.all_day)}
              </p>
            )}
          </article>
        ))}
      </div>
      {data && data.count > 50 && (
        <div className="button-row">
          <button
            className="button button-ghost"
            disabled={data.page <= 1}
            onClick={() => filter('page', String(data.page - 1))}
          >
            {t('Zurück')}
          </button>
          <span>
            {data.page} / {Math.ceil(data.count / 50)}
          </span>
          <button
            className="button button-ghost"
            disabled={data.page * 50 >= data.count}
            onClick={() => filter('page', String(data.page + 1))}
          >
            {t('Weiter')}
          </button>
        </div>
      )}
    </>
  )
}

export function MaterialPicker({
  base,
  kind,
  onSelect,
}: {
  base: string
  kind: string
  onSelect: (choice: MaterialChoice) => void
}) {
  const [search, setSearch] = useState('')
  const [open, setOpen] = useState(false)
  const [debounced, setDebounced] = useState('')
  const query = search.trim()
  useEffect(() => {
    const timer = setTimeout(() => setDebounced(query), 250)
    return () => clearTimeout(timer)
  }, [query])
  const { data, error, loading } = useQueryLoad(
    () =>
      api.get<{ items: MaterialChoice[]; more: boolean }>(
        `${base}choices/?kind=${kind}&q=${encodeURIComponent(query)}`,
      ),
    [base, kind, query],
    open && query.length >= 2 && debounced === query,
  )
  return (
    <div
      className="material-picker member-picker"
      onFocus={() => setOpen(true)}
      onBlur={(e) => {
        if (!e.currentTarget.contains(e.relatedTarget)) setOpen(false)
      }}
      onKeyDown={(e) => {
        if (e.key === 'Escape') {
          e.stopPropagation()
          setOpen(false)
        }
      }}
    >
      <label>
        {t('Auswahl suchen')}
        <input
          type="search"
          value={search}
          onChange={(e) => {
            setSearch(e.target.value)
            setOpen(true)
          }}
        />
      </label>
      {open && query && (
        <small className="muted" role="status">
          {query.length < 2
            ? t('Mindestens 2 Zeichen eingeben.')
            : loading || debounced !== query
              ? t('Suche läuft …')
              : data?.items.length === 0
                ? t('Keine passenden Einträge gefunden.')
                : data
                  ? t('{n} Treffer', { n: data.items.length })
                  : ''}
        </small>
      )}
      {!!data?.items.length && (
        <ul className="picker-results material-picker-results" aria-label={t('Suchergebnisse')}>
          {data.items.map((choice) => (
            <li key={choice.id}>
              <button
                className="button button-ghost"
                type="button"
                onClick={() => {
                  onSelect(choice)
                  setSearch('')
                  setOpen(false)
                }}
              >
                {choice.title}
                {choice.starts_at && (
                  <span className="muted">
                    {new Date(choice.starts_at).toLocaleDateString(locale(), {
                      timeZone: 'Europe/Berlin',
                    })}
                  </span>
                )}
              </button>
            </li>
          ))}
        </ul>
      )}
      {data?.more && <p>{t('Bitte die Suche eingrenzen.')}</p>}
      {error && <p role="alert">{error}</p>}
    </div>
  )
}

function ItemForm({
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
  useDraftGuard(!saved && (JSON.stringify(values) !== JSON.stringify(initial) || !!event), () => {
    setValues(initial)
    setEvent(null)
  })
  const lanes = values.lanes
  return (
    <>
      <h1>
        {facility
          ? item
            ? t('Infrastruktur bearbeiten')
            : t('Infrastruktur anlegen')
          : item
            ? t('Material bearbeiten')
            : t('Material anlegen')}
      </h1>
      <form
        className="card material-form"
        onSubmit={async (e) => {
          e.preventDefault()
          setBusy(true)
          setError(null)
          try {
            const payload: Record<string, unknown> = {
              ...values,
              member: values.location_kind === 'member' ? values.member : null,
              facility: values.location_kind === 'facility' ? values.facility : null,
              events: event ? [{ event: event.id, kind: event.series ? 'series' : 'event' }] : [],
            }
            if (facility) delete payload.belongs_to
            else
              for (const key of ['facility_type', 'ownership', 'capacity', 'lanes', 'access_note'])
                delete payload[key]
            if (facility && values.facility_type !== 'range') payload.lanes = []
            // Unveränderte Mitgliedsreferenzen nicht ohne Mitgliederdatenrecht neu validieren.
            const changes: Record<string, unknown> = item
              ? Object.fromEntries(
                  Object.entries(payload).filter(
                    ([key, value]) =>
                      key !== 'events' &&
                      JSON.stringify(value) !==
                        JSON.stringify(initial[key as keyof typeof initial]),
                  ),
                )
              : payload
            if (item && item.location_kind !== values.location_kind)
              changes.location_kind = values.location_kind
            const result = item
              ? await materialApi.update(base, item.id, { ...changes, version: item.version })
              : await materialApi.create(base, payload)
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
                    {['building', 'room', 'range', 'ground', 'storage', 'other'].map((v) => (
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
                  {t('Zum Beispiel ein Schlüssel, der zum Schützenhaus gehört.')}
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
        </div>
      </form>
    </>
  )
}

function MaterialDetail({
  stock,
  base,
  editable,
}: {
  stock: Stock
  base: string
  editable: boolean
}) {
  const { id } = useParams()
  const [params] = useSearchParams()
  const trash = params.get('trash') === '1'
  const { data, error, reload } = useLoad(
    () => materialApi.get(base, Number(id), trash),
    [base, id, trash],
  )
  const navigate = useNavigate()
  const [editing, setEditing] = useState(false)
  const [failure, setFailure] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const act = async (fn: () => Promise<unknown>) => {
    setBusy(true)
    setFailure(null)
    try {
      await fn()
      await reload()
    } catch (err) {
      setFailure(errorMessage(err))
    } finally {
      setBusy(false)
    }
  }
  if (error) return <p role="alert">{error}</p>
  if (!data) return <p role="status">{t('Wird geladen…')}</p>
  if (editing)
    return (
      <ItemForm
        key={data.version}
        stock={stock}
        base={base}
        item={data}
        onSaved={() => {
          setEditing(false)
          reload()
        }}
      />
    )
  return (
    <>
      <Link to={stock.root}>
        {stock.kind === 'facility' ? t('Zur Infrastrukturübersicht') : t('Zur Materialübersicht')}
      </Link>
      <div className="page-heading">
        <h1>{data.title}</h1>
        {data.music_equipment && (
          <p>
            <Link to="/musik?ausstattung=1">{t('Musikausstattung öffnen')}</Link>
            {data.music_equipment.loaned ? ` · ${t('Über den Musikbereich ausgegeben')}` : ''}
          </p>
        )}
        {editable && !trash && (
          <button className="button" onClick={() => setEditing(true)}>
            {t('Bearbeiten')}
          </button>
        )}
      </div>
      {failure && <p role="alert">{failure}</p>}
      <section className="card">
        <p className="muted">{data.inventory_number}</p>
        <p>{data.description}</p>
        {data.facility_type && (
          <p>
            {facilityTypeLabel(data.facility_type)}
            {data.ownership ? ` · ${ownershipLabel(data.ownership)}` : ''}
            {data.capacity ? ` · ${t('Kapazität {n}', { n: data.capacity })}` : ''}
          </p>
        )}
        {!!data.lanes?.length && (
          <ul>
            {data.lanes.map((lane) => (
              <li key={lane.facility}>
                {laneLabel(lane.facility)}: {tn('{n} Bahn', '{n} Bahnen', lane.count)}
              </li>
            ))}
          </ul>
        )}
        <h2>{t('Standort')}</h2>
        <p>
          {data.location_kind === 'facility' && data.facility && !data.location_review ? (
            <Link to={`/infrastruktur/${data.facility}`}>{location(data)}</Link>
          ) : (
            location(data)
          )}
        </p>
        {data.parent && <p>{Object.values(data.parent.address).filter(Boolean).join(', ')}</p>}
        <p>{data.location_note}</p>
        {data.access_note && (
          <p>
            {t('Zugangshinweis')}: {data.access_note}
          </p>
        )}
        {data.belongs_to && (
          <p>
            {t('Gehört zu')}:{' '}
            <Link to={`/infrastruktur/${data.belongs_to}`}>{data.belongs_to_title}</Link>
          </p>
        )}
        <p>
          {conditionLabel(data.condition, stock.kind)} · {data.condition_note}
        </p>
      </section>
      {stock.kind === 'facility' && !trash && (
        <FacilityParts stock={stock} item={data} editable={editable} />
      )}
      {!trash && (
        <BookingRulesCard itemBase={base} item={data} editable={editable} onSaved={reload} />
      )}
      {!trash && (
        <section className="card">
          <h2>{stock.kind === 'facility' ? t('Foto') : t('Materialfoto')}</h2>
          {data.photo_url ? (
            <img className="material-photo" src={data.photo_url} alt={data.title} />
          ) : (
            <p>{t('Noch kein Bild vorhanden.')}</p>
          )}
          {editable && (
            <>
              <label>
                {t('Bild hinzufügen oder ersetzen')}
                <input
                  disabled={busy}
                  type="file"
                  accept="image/jpeg,image/png,image/webp"
                  onChange={(e) => {
                    const file = e.target.files?.[0]
                    if (!file) return
                    const form = new FormData()
                    form.append('file', file)
                    form.append('version', String(data.version))
                    void act(() => api.post(`${base}${data.id}/photo/`, form))
                    e.target.value = ''
                  }}
                />
              </label>
              <p className="muted">
                {t('JPEG, PNG oder WebP, höchstens 10 MB. Bildmetadaten werden entfernt.')}
              </p>
              {data.photo_url && (
                <button
                  className="button button-ghost"
                  disabled={busy}
                  onClick={() =>
                    void act(() =>
                      api.delWith(`${base}${data.id}/photo/`, { version: data.version }),
                    )
                  }
                >
                  {t('Bild entfernen')}
                </button>
              )}
            </>
          )}
        </section>
      )}
      <section className="card">
        <h2>{t('Verwendung')}</h2>
        <p>{data.purpose}</p>
        {data.usage_review && <p role="status">{t('Verwendung prüfen')}</p>}
        {data.events?.map((link) => (
          <div className="material-link" key={link.id}>
            <div>
              <strong>{link.title}</strong>
              <p>
                {eventLabel(link.kind)}
                {link.original_start ? ` · ${whenLabel(link.original_start, link.all_day)}` : ''}
                {link.valid_from ? ` · ${t('Ab')} ${link.valid_from}` : ''}
                {link.valid_until ? ` · ${t('Bis')} ${link.valid_until}` : ''}
              </p>
              <p>{link.note}</p>
              {link.needs_review && <p>{t('Terminbezug prüfen')}</p>}
              {link.cancelled && <p>{t('Abgesagt')}</p>}
              {data.booking_rules?.enabled &&
                !trash &&
                !link.cancelled &&
                link.kind !== 'exclude' &&
                (link.kind !== 'occurrence' || link.original_start) && (
                  <Link
                    to={`/belegung?${new URLSearchParams({
                      buchen: '1',
                      objekt: String(data.id),
                      termin: String(link.event),
                      titel: link.title,
                      ...(link.kind === 'occurrence' && link.original_start
                        ? { vorkommen: link.original_start }
                        : {}),
                    }).toString()}`}
                  >
                    {t('Verbindlich buchen')}
                  </Link>
                )}
            </div>
            {editable && !trash && (
              <button
                className="button button-ghost"
                disabled={busy}
                onClick={() =>
                  void act(() =>
                    materialApi.link(base, data, { type: 'event', id: link.id, remove: true }),
                  )
                }
              >
                {t('Zuordnung entfernen')}
              </button>
            )}
          </div>
        ))}
        {!trash && (
          <>
            <h3>{t('Kommende Verwendungen')}</h3>
            {data.uses?.length ? (
              <ul>
                {data.uses.map((u) => (
                  <li key={`${u.event}-${u.original_start}`}>
                    {u.title} · {whenLabel(u.starts_at, u.all_day)}
                  </li>
                ))}
              </ul>
            ) : (
              <p>{t('Keine kommenden Verwendungen im nächsten Jahr.')}</p>
            )}
            <p className="muted">
              {t('Eine Zuordnung erfasst den Bedarf und ist keine verbindliche Reservierung.')}
            </p>
          </>
        )}
        {editable && !trash && data.condition !== 'retired' && (
          <EventEditor
            base={base}
            busy={busy}
            save={(row) => act(() => materialApi.link(base, data, { type: 'event', ...row }))}
          />
        )}
      </section>
      {(['todo', 'document'] as const).map((kind) => (
        <section className="card" key={kind}>
          <h2>{kind === 'todo' ? t('Aufgaben') : t('Dokumente')}</h2>
          {(kind === 'todo' ? data.todos : data.documents)?.map((row) => (
            <div className="material-link" key={row.id}>
              <a
                href={
                  kind === 'todo'
                    ? `/aufgaben?aufgabe=${row.id}`
                    : `${base}${data.id}/documents/${row.id}/`
                }
              >
                {row.title}
                {'status' in row && row.status === 'done' ? ` · ${t('Erledigt')}` : ''}
              </a>
              {editable && !trash && (
                <button
                  className="button button-ghost"
                  disabled={busy}
                  onClick={() =>
                    void act(() =>
                      materialApi.link(base, data, { type: kind, id: row.id, remove: true }),
                    )
                  }
                >
                  {t('Zuordnung entfernen')}
                </button>
              )}
            </div>
          ))}
          {editable && !trash && data.condition !== 'retired' && (
            <fieldset disabled={busy}>
              <MaterialPicker
                base={base}
                kind={kind}
                onSelect={(row) =>
                  void act(() => materialApi.link(base, data, { type: kind, id: row.id }))
                }
              />
              {kind === 'todo' && (
                <Link
                  to={`/aufgaben?neu=1&material=${data.id}${stock.kind === 'facility' ? '&art=facility' : ''}`}
                >
                  {stock.kind === 'facility'
                    ? t('Aufgabe für diese Infrastruktur anlegen')
                    : t('Aufgabe für dieses Material anlegen')}
                </Link>
              )}
            </fieldset>
          )}
        </section>
      ))}
      <History
        key={data.version}
        root={stock.root}
        base={base}
        item={data}
        editable={editable}
        act={act}
        busy={busy}
      />
      {editable && (
        <div className="button-row">
          {trash ? (
            <button
              className="button button-ghost"
              disabled={busy}
              onClick={() =>
                void act(async () => {
                  await materialApi.restore(base, data)
                  navigate(`${stock.root}/${data.id}`)
                })
              }
            >
              {t('Wiederherstellen')}
            </button>
          ) : (
            <button
              className="button button-ghost"
              disabled={busy}
              onClick={() =>
                void act(async () => {
                  await materialApi.remove(base, data)
                  navigate(`${stock.root}?trash=1&archived=1`)
                })
              }
            >
              {t('In den Papierkorb')}
            </button>
          )}
        </div>
      )}
    </>
  )
}

function eventLabel(kind: MaterialEvent['kind']) {
  return {
    event: t('Einzeltermin'),
    series: t('Ganze Reihe'),
    occurrence: t('Nur dieser Termin'),
    exclude: t('Diesen Termin ausschließen'),
  }[kind]
}

function EventEditor({
  base,
  busy,
  save,
}: {
  base: string
  busy: boolean
  save: (row: object) => Promise<void>
}) {
  const [choice, setChoice] = useState<MaterialChoice | null>(null)
  const [kind, setKind] = useState<MaterialEvent['kind']>('event')
  const [original, setOriginal] = useState('')
  const [from, setFrom] = useState('')
  const [until, setUntil] = useState('')
  const [note, setNote] = useState('')
  return (
    <details>
      <summary>{t('Termin oder Terminreihe zuordnen')}</summary>
      <fieldset disabled={busy}>
        <MaterialPicker
          base={base}
          kind="event"
          onSelect={(row) => {
            setChoice(row)
            setKind(row.series ? 'series' : 'event')
            setOriginal('')
          }}
        />
        {choice && (
          <>
            <p>{choice.title}</p>
            {choice.series && (
              <label>
                {t('Geltung')}
                <select
                  value={kind}
                  onChange={(e) => setKind(e.target.value as MaterialEvent['kind'])}
                >
                  {(['series', 'occurrence', 'exclude'] as const).map((k) => (
                    <option value={k} key={k}>
                      {eventLabel(k)}
                    </option>
                  ))}
                </select>
              </label>
            )}
            {(kind === 'occurrence' || kind === 'exclude') && (
              <label>
                {t('Ursprünglicher Beginn des Vorkommens')}
                <input
                  type="datetime-local"
                  required
                  value={original}
                  onChange={(e) => setOriginal(e.target.value)}
                />
              </label>
            )}
            {kind === 'series' && (
              <div className="material-filters">
                <label>
                  {t('Gültig ab (leer: heute)')}
                  <input type="date" value={from} onChange={(e) => setFrom(e.target.value)} />
                </label>
                <label>
                  {t('Gültig bis')}
                  <input type="date" value={until} onChange={(e) => setUntil(e.target.value)} />
                </label>
              </div>
            )}
            <label>
              {t('Verwendungshinweis')}
              <input maxLength={300} value={note} onChange={(e) => setNote(e.target.value)} />
            </label>
            <button
              className="button button-ghost"
              type="button"
              disabled={busy || (['occurrence', 'exclude'].includes(kind) && !original)}
              onClick={() =>
                void save({
                  event: choice.id,
                  kind,
                  ...(original ? { original_start: original + ':00' } : {}),
                  ...(from ? { valid_from: from } : {}),
                  valid_until: until || null,
                  note,
                })
              }
            >
              {t('Zuordnen')}
            </button>
          </>
        )}
      </fieldset>
    </details>
  )
}

function History({
  root,
  base,
  item,
  editable,
  act,
  busy,
}: {
  root: string
  base: string
  item: Material
  editable: boolean
  act: (fn: () => Promise<unknown>) => Promise<void>
  busy: boolean
}) {
  const navigate = useNavigate()
  const endpoint = `${base}${item.id}/history/${item.deleted_at ? '?trash=1' : ''}`
  const { data, error } = useLoad(
    () =>
      api.get<{ id: number; at: string; action: string; actor: string; can_undo: boolean }[]>(
        endpoint,
      ),
    [endpoint],
  )
  return (
    <details className="card">
      <summary>{t('Verlauf')}</summary>
      {error && <p role="alert">{error}</p>}
      {data?.map((row, index) => (
        <div className="material-link" key={row.id}>
          <span>
            {new Date(row.at).toLocaleString(locale(), { timeZone: 'Europe/Berlin' })} · {row.actor}{' '}
            ·{' '}
            {
              {
                create: t('Angelegt'),
                update: t('Bearbeitet'),
                links: t('Zuordnungen geändert'),
                photo: t('Bild geändert'),
                delete: t('In den Papierkorb'),
                restore: t('Wiederhergestellt'),
                undo: t('Rückgängig'),
              }[row.action]
            }
          </span>
          {index === 0 && row.can_undo && editable && (
            <button
              className="button button-ghost"
              disabled={busy}
              onClick={() =>
                void act(async () => {
                  const restored = await api.post<Material>(endpoint, {
                    version: item.version,
                    revision: row.id,
                  })
                  if (!!restored.deleted_at !== !!item.deleted_at)
                    navigate(`${root}/${item.id}${restored.deleted_at ? '?trash=1' : ''}`)
                })
              }
            >
              {t('Rückgängig')}
            </button>
          )}
        </div>
      ))}
    </details>
  )
}

function FacilityParts({
  stock,
  item,
  editable,
}: {
  stock: Stock
  item: Material
  editable: boolean
}) {
  const row = (r: StockRow) => (
    <li key={r.id}>
      <Link to={`${stockRoot(r.kind)}/${r.id}`}>
        {r.inventory_number} · {r.title}
      </Link>
      {r.member_name ? ` · ${t('Bei {name}', { name: r.member_name })}` : ''}
      {r.location_note ? ` · ${r.location_note}` : ''}
      {r.condition !== 'ready' ? ` · ${conditionLabel(r.condition, r.kind)}` : ''}
    </li>
  )
  return (
    <>
      {item.location_kind !== 'facility' && (
        <section className="card">
          <h2>{t('Bereiche')}</h2>
          {item.areas?.length ? (
            <ul>{item.areas.map(row)}</ul>
          ) : (
            <p>
              {t('Keine Bereiche. Bereiche sind zum Beispiel Saal, Küche oder einzelne Stände.')}
            </p>
          )}
          {editable && item.condition !== 'retired' && (
            <Link
              to={`${stock.root}/neu?bereich=${item.id}&name=${encodeURIComponent(item.title)}`}
            >
              {t('Bereich anlegen')}
            </Link>
          )}
        </section>
      )}
      {item.contents && (
        <section className="card">
          <h2>{t('Hier gelagertes Material')}</h2>
          {item.contents.length ? (
            <ul>{item.contents.map(row)}</ul>
          ) : (
            <p>{t('Kein Material hier gelagert.')}</p>
          )}
          <h2>{t('Zugehöriges Material')}</h2>
          {item.accessories?.length ? (
            <ul>{item.accessories.map(row)}</ul>
          ) : (
            <p>{t('Kein zugehöriges Material, zum Beispiel Schlüssel.')}</p>
          )}
        </section>
      )}
    </>
  )
}
