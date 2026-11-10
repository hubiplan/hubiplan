// Einstellungen › Orte: Orte, die man in Terminen, Wettbewerben, Helferdiensten und
// Versammlungen immer wieder eingibt, einmal speichern und dort auswählen.
import { useState } from 'react'
import { placeApi } from '../../api/places.ts'
import type { Place, PlaceInput, PlaceSuggestion } from '../../api/places.ts'
import { confirmDialog } from '../../components/dialog.ts'
import { errorMessage, useLoad } from '../../components/forms.ts'
import { forgetPlaces } from '../../components/places.ts'
import { Alert, Checkbox, Field, LoadError, Loading } from '../../components/ui.tsx'
import { useActiveOrg } from '../../org/OrgContext.tsx'
import { t } from '../../i18n/index.ts'
import { TextArea } from './TextArea.tsx'

interface Draft {
  name: string
  address: string
  directions: string
  latitude: string
  longitude: string
  is_active: boolean
}

const EMPTY: Draft = {
  name: '',
  address: '',
  directions: '',
  latitude: '',
  longitude: '',
  is_active: true,
}

function draftOf(p: Place): Draft {
  return {
    name: p.name,
    address: p.address,
    directions: p.directions,
    latitude: p.latitude == null ? '' : String(p.latitude),
    longitude: p.longitude == null ? '' : String(p.longitude),
    is_active: p.is_active,
  }
}

function number(value: string): number | null {
  const v = value.trim().replace(',', '.')
  return v ? Number(v) : null
}

function inputOf(d: Draft): PlaceInput {
  return {
    name: d.name.trim(),
    address: d.address.trim(),
    directions: d.directions.trim(),
    latitude: number(d.latitude),
    longitude: number(d.longitude),
    is_active: d.is_active,
  }
}

function PlaceForm({
  initial,
  submitLabel,
  onSubmit,
  onCancel,
}: {
  initial: Draft
  submitLabel: string
  onSubmit: (input: PlaceInput) => Promise<void>
  onCancel?: () => void
}) {
  const [d, setD] = useState(initial)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const set = <K extends keyof Draft>(key: K, value: Draft[K]) => setD({ ...d, [key]: value })
  return (
    <form
      className="stack"
      onSubmit={async (e) => {
        e.preventDefault()
        setBusy(true)
        setError(null)
        try {
          await onSubmit(inputOf(d))
          if (!onCancel) setD(EMPTY)
        } catch (err) {
          setError(errorMessage(err))
        } finally {
          setBusy(false)
        }
      }}
    >
      <div className="grid-2">
        <Field
          label={t('Name')}
          required
          maxLength={200}
          placeholder={t('z. B. Schützenhaus')}
          value={d.name}
          onChange={(e) => set('name', e.target.value)}
        />
        <Field
          label={t('Anschrift')}
          maxLength={300}
          placeholder={t('Straße Nr., PLZ Ort')}
          value={d.address}
          onChange={(e) => set('address', e.target.value)}
        />
      </div>
      <TextArea
        label={t('Anfahrt und Hinweise')}
        hint={t('z. B. Parkplatz, Eingang, Bushaltestelle')}
        value={d.directions}
        onChange={(value) => set('directions', value)}
      />
      <details open={!!(d.latitude || d.longitude)}>
        <summary>{t('Genauer Kartenpunkt (optional)')}</summary>
        <p className="muted small">
          {t(
            'Für Orte ohne passende Anschrift, etwa ein Festzelt oder einen Schießstand im Wald. Die Zahlen stehen z. B. in OpenStreetMap im Link zum Ort.',
          )}
        </p>
        <div className="grid-2">
          <Field
            label={t('Breite')}
            inputMode="decimal"
            placeholder="51.17000"
            value={d.latitude}
            onChange={(e) => set('latitude', e.target.value)}
          />
          <Field
            label={t('Länge')}
            inputMode="decimal"
            placeholder="6.73000"
            value={d.longitude}
            onChange={(e) => set('longitude', e.target.value)}
          />
        </div>
      </details>
      {onCancel && (
        <Checkbox
          label={t('Aktiv (in der Auswahl der Formulare)')}
          checked={d.is_active}
          onChange={(value) => set('is_active', value)}
        />
      )}
      {error && <Alert kind="error">{error}</Alert>}
      <div className="button-row">
        <button type="submit" className="button button-primary" disabled={busy}>
          {submitLabel}
        </button>
        {onCancel && (
          <button type="button" className="button" onClick={onCancel}>
            {t('Abbrechen')}
          </button>
        )}
      </div>
    </form>
  )
}

function Suggestions({ base, onTaken }: { base: string; onTaken: (place: Place) => void }) {
  const { data, setData } = useLoad(() => placeApi.suggestions(base), [base])
  const [error, setError] = useState<string | null>(null)
  if (!data?.length) return null
  const take = async (s: PlaceSuggestion) => {
    setError(null)
    try {
      const place = await placeApi.create(base, { name: s.name, address: s.address })
      setData(data.filter((x) => x !== s))
      onTaken(place)
    } catch (err) {
      setError(errorMessage(err))
    }
  }
  return (
    <section className="card">
      <h3>{t('Vorschläge aus bisherigen Einträgen')}</h3>
      <p className="muted small">
        {t('Diese Orte wurden in den letzten zwei Jahren mehrfach eingetippt.')}
      </p>
      <ul className="item-list">
        {data.map((s) => (
          <li key={s.name} className="item-row">
            <div className="item-row-info">
              <strong>{s.name}</strong>
              {s.address && <div className="muted small">{s.address}</div>}
              <div className="muted small">{t('{n}-mal verwendet', { n: s.count })}</div>
            </div>
            <div className="button-row">
              <button type="button" className="button" onClick={() => void take(s)}>
                {t('Übernehmen')}
              </button>
            </div>
          </li>
        ))}
      </ul>
      {error && <Alert kind="error">{error}</Alert>}
    </section>
  )
}

export function PlacesPage() {
  const org = useActiveOrg()
  const base = `/api/orgs/${org.id}/places/`
  const { data, error, reload, setData } = useLoad(() => placeApi.list(base, true), [base])
  const [editing, setEditing] = useState<number | null>(null)
  const [actionError, setActionError] = useState<string | null>(null)
  if (error) return <LoadError message={error} onRetry={reload} />
  if (!data) return <Loading />
  const own = data.places.filter((p) => p.own)
  const inherited = data.places.filter((p) => !p.own && p.is_active)
  const replace = (place: Place) => {
    forgetPlaces()
    setData({ ...data, places: data.places.map((p) => (p.id === place.id ? place : p)) })
  }
  const add = (place: Place) => {
    forgetPlaces()
    setData({ ...data, places: [...data.places, place] })
  }
  const remove = async (place: Place) => {
    const yes = await confirmDialog({
      message: t(
        'Ort „{name}“ löschen? Termine und Wettbewerbe mit diesem Ort behalten ihre Angaben.',
        { name: place.name },
      ),
      confirmLabel: t('Löschen'),
    })
    if (!yes) return
    setActionError(null)
    try {
      await placeApi.remove(base, place.id)
      forgetPlaces()
      setData({ ...data, places: data.places.filter((p) => p.id !== place.id) })
    } catch (err) {
      setActionError(errorMessage(err))
    }
  }
  return (
    <div className="stack">
      <section className="card card-wide">
        <h2>{t('Orte')}</h2>
        <p className="muted small">
          {t(
            'Gespeicherte Orte stehen in Terminen, Wettbewerben, Helferdiensten und Versammlungen zur Auswahl. Beim Auswählen werden Name und Anschrift übernommen; spätere Änderungen hier ändern frühere Einträge nicht.',
          )}
        </p>
        {own.length === 0 ? (
          <p>{t('Noch keine Orte gespeichert.')}</p>
        ) : (
          <ul className="item-list">
            {own.map((p) =>
              editing === p.id ? (
                <li key={p.id}>
                  <PlaceForm
                    initial={draftOf(p)}
                    submitLabel={t('Speichern')}
                    onCancel={() => setEditing(null)}
                    onSubmit={async (input) => {
                      replace(await placeApi.update(base, p.id, input))
                      setEditing(null)
                    }}
                  />
                </li>
              ) : (
                <li key={p.id} className="item-row">
                  <div className="item-row-info">
                    <strong>{p.name}</strong>
                    {!p.is_active && <span className="muted small"> · {t('archiviert')}</span>}
                    {p.address && <div className="muted small">{p.address}</div>}
                    {p.directions && <div className="small">{p.directions}</div>}
                  </div>
                  {data.can_manage && (
                    <div className="button-row">
                      <button type="button" className="button" onClick={() => setEditing(p.id)}>
                        {t('Bearbeiten')}
                      </button>
                      <button
                        type="button"
                        className="button button-danger"
                        onClick={() => void remove(p)}
                      >
                        {t('Löschen')}
                      </button>
                    </div>
                  )}
                </li>
              ),
            )}
          </ul>
        )}
        {actionError && <Alert kind="error">{actionError}</Alert>}
      </section>
      {data.can_edit && (
        <section className="card card-wide">
          <h3>{t('Neuer Ort')}</h3>
          <PlaceForm
            initial={EMPTY}
            submitLabel={t('Ort speichern')}
            onSubmit={async (input) => add(await placeApi.create(base, input))}
          />
        </section>
      )}
      {data.can_manage && <Suggestions base={base} onTaken={add} />}
      {inherited.length > 0 && (
        <section className="card card-wide">
          <h3>{t('Orte von {name}', { name: inherited[0].owner ?? '' })}</h3>
          <ul className="item-list">
            {inherited.map((p) => (
              <li key={p.id} className="item-row">
                <div className="item-row-info">
                  <strong>{p.name}</strong>
                  {p.address && <div className="muted small">{p.address}</div>}
                </div>
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  )
}
