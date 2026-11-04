import { useState } from 'react'
import { api, newRequestKey } from '../../api/client.ts'
import { errorMessage, formatDateTime, useLoad } from '../../components/forms.ts'
import { confirmLeave, useDraftGuard } from '../../components/leaveGuard.ts'
import { confirmDialog } from '../../components/dialog.ts'
import { Alert } from '../../components/ui.tsx'
import { useActiveOrg } from '../../org/OrgContext.tsx'
import { t } from '../../i18n/index.ts'
import { MusicHeader, MusicEmptyState } from './MusicLayout.tsx'

type Absence = { id: number; musician: number; starts_at: string; ends_at: string }
type Musician = { id: number; display_name: string; active: boolean }
type Values = { musician?: number; starts_at: string; ends_at: string }

export function AvailabilityHint({ reasons = [] }: { reasons?: string[] }) {
  return (
    <span className={`music-availability${reasons.length ? ' music-availability-conflict' : ''}`}>
      {reasons.includes('absence')
        ? t('Abwesend')
        : reasons.includes('declined')
          ? t('Für diesen Termin abgesagt')
          : reasons.includes('busy')
            ? t('Terminüberschneidung')
            : t('Kein Konflikt bekannt')}
    </span>
  )
}

export function AvailabilityPage() {
  const org = useActiveOrg(),
    base = `/api/orgs/${org.id}/music/`
  const load = useLoad(async () => {
    const [items, musicians] = await Promise.all([
      api.get<Absence[]>(base + 'absences/'),
      api.get<Musician[]>(base + 'musicians/'),
    ])
    return { items, musicians }
  }, [org.id])
  const [selected, setSelected] = useState<Absence | 'new' | null>(null),
    [error, setError] = useState('')
  if (load.error) return <Alert kind="error">{load.error}</Alert>
  if (!load.data) return <p>{t('Lädt …')}</p>
  const { items, musicians } = load.data,
    canEdit = org.permissions.includes('music.edit')
  return (
    <section className="stack music-page">
      <MusicHeader
        title={t('Verfügbarkeiten')}
        description={t(
          'Abwesenheiten ohne Begründung erfassen. Die Besetzungsplanung prüft zusätzlich bekannte Auftritte, Proben und Kalenderzusagen im selben Verein.',
        )}
      />
      {error && <Alert kind="error">{error}</Alert>}
      {canEdit && (
        <button
          className="button button-primary"
          onClick={async () => {
            if (await confirmLeave()) setSelected('new')
          }}
        >
          {t('Abwesenheit eintragen')}
        </button>
      )}
      {canEdit && selected && (
        <AbsenceForm
          key={selected === 'new' ? 'new' : selected.id}
          initial={selected === 'new' ? undefined : selected}
          musicians={musicians}
          onClose={() => setSelected(null)}
          onSave={async (values, key) => {
            if (selected === 'new') await api.post(base + 'absences/', values, key)
            else await api.patch(`${base}absences/${selected.id}/`, values)
            await load.reload()
            setSelected(null)
          }}
        />
      )}
      {!items.length && <MusicEmptyState>{t('Keine Abwesenheiten eingetragen.')}</MusicEmptyState>}
      {items.map((row) => (
        <article className="card stack music-record" key={row.id}>
          <strong>{musicians.find((m) => m.id === row.musician)?.display_name}</strong>
          <AbsenceDates row={row} />
          {canEdit && (
            <div className="actions">
              <button
                className="button button-ghost"
                onClick={async () => {
                  if (await confirmLeave()) setSelected(row)
                }}
              >
                {t('Bearbeiten')}
              </button>
              <button
                className="button button-ghost"
                onClick={async () => {
                  if (
                    !(await confirmLeave()) ||
                    !(await confirmDialog(t('Abwesenheit entfernen?')))
                  )
                    return
                  try {
                    await api.del(`${base}absences/${row.id}/`)
                    setSelected(null)
                    await load.reload()
                  } catch (e) {
                    setError(errorMessage(e))
                  }
                }}
              >
                {t('Entfernen')}
              </button>
            </div>
          )}
        </article>
      ))}
    </section>
  )
}

function AbsenceDates({ row }: { row: Absence }) {
  return (
    <p>
      {formatDateTime(row.starts_at)} – {formatDateTime(row.ends_at)}
    </p>
  )
}

export function OwnAvailability({ accessId }: { accessId: number }) {
  const url = `/api/portal/${accessId}/music/absences/`
  const load = useLoad(() => api.get<{ enabled: boolean; items: Absence[] }>(url), [accessId])
  const [selected, setSelected] = useState<Absence | 'new' | null>(null),
    [error, setError] = useState(''),
    [deleteKeys] = useState(() => new Map<number, string>())
  if (!load.data?.enabled) return null
  return (
    <section className="card stack music-personal">
      <h2>{t('Meine Abwesenheiten')}</h2>
      <p>
        {t(
          'Zeiträume eintragen, in denen Sie nicht mitspielen können. Eine Begründung wird nicht erfasst. Bestehende Einteilungen bleiben erhalten; bitte dort zusätzlich absagen.',
        )}
      </p>
      {error && <Alert kind="error">{error}</Alert>}
      <button
        className="button button-ghost"
        onClick={async () => {
          if (await confirmLeave()) setSelected('new')
        }}
      >
        {t('Abwesenheit eintragen')}
      </button>
      {selected && (
        <AbsenceForm
          key={selected === 'new' ? 'new' : selected.id}
          initial={selected === 'new' ? undefined : selected}
          onClose={() => setSelected(null)}
          onSave={async (values, key) => {
            await api.post(
              url,
              { action: 'save', ...(selected === 'new' ? {} : { id: selected.id }), ...values },
              key,
            )
            await load.reload()
            setSelected(null)
          }}
        />
      )}
      {!load.data.items.length && (
        <MusicEmptyState>{t('Keine Abwesenheiten eingetragen.')}</MusicEmptyState>
      )}
      {load.data.items.map((row) => (
        <article className="stack" key={row.id}>
          <AbsenceDates row={row} />
          <div className="actions">
            <button
              className="button button-ghost"
              onClick={async () => {
                if (await confirmLeave()) setSelected(row)
              }}
            >
              {t('Bearbeiten')}
            </button>
            <button
              className="button button-ghost"
              onClick={async () => {
                if (!(await confirmLeave()) || !(await confirmDialog(t('Abwesenheit entfernen?'))))
                  return
                if (!deleteKeys.has(row.id)) deleteKeys.set(row.id, newRequestKey())
                try {
                  await api.post(url, { action: 'delete', id: row.id }, deleteKeys.get(row.id))
                  setSelected(null)
                  await load.reload()
                } catch (e) {
                  setError(errorMessage(e))
                }
              }}
            >
              {t('Entfernen')}
            </button>
          </div>
        </article>
      ))}
    </section>
  )
}

function local(value?: string) {
  if (!value) return ''
  const date = new Date(value)
  return new Date(date.getTime() - date.getTimezoneOffset() * 60000).toISOString().slice(0, 16)
}

function AbsenceForm({
  initial,
  musicians,
  onSave,
  onClose,
}: {
  initial?: Absence
  musicians?: Musician[]
  onSave: (values: Values, key: string) => Promise<void>
  onClose: () => void
}) {
  const [musician, setMusician] = useState(
      String(initial?.musician ?? musicians?.find((m) => m.active)?.id ?? ''),
    ),
    [start, setStart] = useState(local(initial?.starts_at)),
    [end, setEnd] = useState(local(initial?.ends_at)),
    [key, setKey] = useState(newRequestKey),
    [busy, setBusy] = useState(false),
    [error, setError] = useState('')
  const [clean] = useState(JSON.stringify([musician, start, end]))
  useDraftGuard(JSON.stringify([musician, start, end]) !== clean)
  return (
    <form
      className="stack music-absence-form"
      onSubmit={async (e) => {
        e.preventDefault()
        setBusy(true)
        setError('')
        try {
          await onSave(
            {
              ...(musicians ? { musician: Number(musician) } : {}),
              starts_at: new Date(start).toISOString(),
              ends_at: new Date(end).toISOString(),
            },
            key,
          )
        } catch (e) {
          setError(errorMessage(e))
        } finally {
          setBusy(false)
        }
      }}
    >
      {error && <Alert kind="error">{error}</Alert>}
      <fieldset disabled={busy} className="music-form-fields">
        {musicians && (
          <label>
            {t('Musiker')}
            <select
              required
              disabled={!!initial}
              value={musician}
              onChange={(e) => {
                setMusician(e.target.value)
                setKey(newRequestKey())
              }}
            >
              {musicians
                .filter((m) => m.active || m.id === initial?.musician)
                .map((m) => (
                  <option value={m.id} key={m.id}>
                    {m.display_name}
                  </option>
                ))}
            </select>
          </label>
        )}
        <label>
          {t('Abwesend von')}
          <input
            type="datetime-local"
            required
            value={start}
            onChange={(e) => {
              setStart(e.target.value)
              setKey(newRequestKey())
            }}
          />
        </label>
        <label>
          {t('Abwesend bis')}
          <input
            type="datetime-local"
            required
            value={end}
            min={start || undefined}
            onChange={(e) => {
              setEnd(e.target.value)
              setKey(newRequestKey())
            }}
          />
        </label>
        <div className="actions">
          <button className="button button-primary">{t('Speichern')}</button>
          <button
            type="button"
            className="button button-ghost"
            onClick={async () => {
              if (await confirmLeave()) onClose()
            }}
          >
            {t('Abbrechen')}
          </button>
        </div>
      </fieldset>
    </form>
  )
}
