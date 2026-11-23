import { useState } from 'react'
import { api } from '../../api/client.ts'
import { errorMessage, useLoad } from '../../components/forms.ts'
import { confirmDialog } from '../../components/dialog.ts'
import { Alert, Loading } from '../../components/ui.tsx'
import { PageHeader } from '../../components/PageHeader.tsx'
import { useActiveOrg } from '../../org/OrgContext.tsx'
import { t, tn } from '../../i18n/index.ts'
import { MusicHeader } from './MusicLayout.tsx'
import { instrumentGroups } from './InstrumentSelect.tsx'
import type { Instrument } from './InstrumentSelect.tsx'

/**
 * Instrumentenliste der Einheit (konzepte/instrumente.md), /musik/instrumente.
 * Vorbelegt mit einer Auswahl für Blaskapellen und Spielleute; Umbenennen zieht alle
 * Verwendungen mit, Entfernen geht nur bei unbenutzten Instrumenten.
 */
export function InstrumentsPage() {
  const org = useActiveOrg()
  const base = `/api/orgs/${org.id}/music/instruments/`
  const load = useLoad(() => api.get<Instrument[]>(base), [org.id])
  const [error, setError] = useState('')
  const [editing, setEditing] = useState<Instrument | 'new' | null>(null)
  if (load.error)
    return (
      <>
        <PageHeader />
        <Alert kind="error">{load.error}</Alert>
      </>
    )
  if (!load.data)
    return (
      <>
        <PageHeader />
        <Loading />
      </>
    )
  const instruments = load.data
  const canEdit = org.permissions.includes('music.edit')
  const act = async (fn: () => Promise<unknown>) => {
    setError('')
    try {
      await fn()
      await load.reload()
      return true
    } catch (err) {
      setError(errorMessage(err))
      return false
    }
  }
  // Innerhalb der Gruppe nach oben oder unten: Platz mit dem Nachbarn tauschen
  const move = (item: Instrument, step: -1 | 1) => {
    const ids = instruments.map((i) => i.id)
    const sameGroup = instruments.filter((i) => i.group === item.group)
    const neighbour = sameGroup[sameGroup.indexOf(item) + step]
    if (!neighbour) return
    const a = ids.indexOf(item.id)
    const b = ids.indexOf(neighbour.id)
    ;[ids[a], ids[b]] = [ids[b], ids[a]]
    void act(() => api.post(`${base}order/`, { ids }))
  }
  const remove = async (item: Instrument) => {
    if (
      await confirmDialog({
        final: true,
        message: t('„{name}“ aus der Liste entfernen?', { name: item.name }),
        confirmLabel: t('Entfernen'),
      })
    )
      await act(() => api.del(`${base}${item.id}/`))
  }
  const form = (item?: Instrument) => (
    <InstrumentForm
      key={item?.id ?? 'new'}
      initial={item}
      onCancel={() => setEditing(null)}
      onSave={async (values) => {
        if (
          await act(() => (item ? api.patch(`${base}${item.id}/`, values) : api.post(base, values)))
        )
          setEditing(null)
      }}
    />
  )
  return (
    <section className="stack music-page">
      <MusicHeader
        title={t('Instrumente')}
        description={t(
          'Feste Auswahl für Musiker, Sollbesetzung, Vorlagen und Noten. Umbenennen ändert das Instrument überall mit.',
        )}
      />
      {error && <Alert kind="error">{error}</Alert>}
      {canEdit && editing !== 'new' && (
        <button className="button button-primary" onClick={() => setEditing('new')}>
          {t('Instrument anlegen')}
        </button>
      )}
      {canEdit && editing === 'new' && form()}
      {instrumentGroups.map(([group, label]) => {
        const items = instruments.filter((i) => i.group === group)
        if (!items.length) return null
        return (
          <section className="stack" key={group} aria-label={label}>
            <h2>{label}</h2>
            <ul className="music-instrument-list">
              {items.map((item, index) => (
                <li key={item.id} className={item.active ? undefined : 'muted'}>
                  {editing !== 'new' && editing?.id === item.id ? (
                    form(item)
                  ) : (
                    <>
                      <span className="music-instrument-name">
                        <strong>{item.name}</strong>
                        {!item.active && ` · ${t('Ausgeblendet')}`}
                        {item.used > 0 && (
                          <small className="muted">
                            {' '}
                            · {tn('{n}× verwendet', '{n}× verwendet', item.used)}
                          </small>
                        )}
                      </span>
                      {canEdit && (
                        <span className="music-record-actions">
                          <button
                            className="button button-ghost"
                            disabled={index === 0}
                            aria-label={t('{name} nach oben', { name: item.name })}
                            onClick={() => move(item, -1)}
                          >
                            ↑
                          </button>
                          <button
                            className="button button-ghost"
                            disabled={index === items.length - 1}
                            aria-label={t('{name} nach unten', { name: item.name })}
                            onClick={() => move(item, 1)}
                          >
                            ↓
                          </button>
                          <button className="button button-ghost" onClick={() => setEditing(item)}>
                            {t('Bearbeiten')}
                          </button>
                          <button
                            className="button button-ghost"
                            onClick={() =>
                              act(() => api.patch(`${base}${item.id}/`, { active: !item.active }))
                            }
                          >
                            {item.active ? t('Ausblenden') : t('Einblenden')}
                          </button>
                          {item.used === 0 && (
                            <button className="button button-ghost" onClick={() => remove(item)}>
                              {t('Entfernen')}
                            </button>
                          )}
                        </span>
                      )}
                    </>
                  )}
                </li>
              ))}
            </ul>
          </section>
        )
      })}
    </section>
  )
}

function InstrumentForm({
  initial,
  onCancel,
  onSave,
}: {
  initial?: Instrument
  onCancel: () => void
  onSave: (values: { name: string; group: string }) => Promise<void>
}) {
  const [name, setName] = useState(initial?.name ?? '')
  const [group, setGroup] = useState(initial?.group ?? 'other')
  const [busy, setBusy] = useState(false)
  return (
    <form
      className="card stack"
      onSubmit={async (e) => {
        e.preventDefault()
        setBusy(true)
        try {
          await onSave({ name: name.trim(), group })
        } finally {
          setBusy(false)
        }
      }}
    >
      <div className="music-form-fields">
        <label>
          {t('Name des Instruments')}
          <input required maxLength={100} value={name} onChange={(e) => setName(e.target.value)} />
        </label>
        <label>
          {t('Gruppe')}
          <select value={group} onChange={(e) => setGroup(e.target.value)}>
            {instrumentGroups.map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
        </label>
      </div>
      {initial && initial.used > 0 && (
        <p className="muted small">
          {t('Ein neuer Name gilt auch für alle Musiker, Stimmen und Noten mit diesem Instrument.')}
        </p>
      )}
      <div className="actions">
        <button className="button button-primary" disabled={busy}>
          {t('Speichern')}
        </button>
        <button className="button button-ghost" type="button" onClick={onCancel}>
          {t('Abbrechen')}
        </button>
      </div>
    </form>
  )
}
