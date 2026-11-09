import { useState } from 'react'
import { api } from '../../api/client.ts'
import { errorMessage, useLoad } from '../../components/forms.ts'
import { confirmLeave, useDraftGuard } from '../../components/leaveGuard.ts'
import { confirmDialog } from '../../components/dialog.ts'
import { Alert } from '../../components/ui.tsx'
import { t, tn } from '../../i18n/index.ts'
import { MusicEmptyState } from './MusicLayout.tsx'
import { LeadersPanel } from './LeadersPanel.tsx'

type Item = {
  id: number
  folder: number
  arrangement: number
  position: number
  number: string
  title: string
  arrangement_name: string
}
type Folder = {
  id: number
  name: string
  kind: 'marchbook' | 'repertoire' | 'other'
  position: number
  departments: number[]
  note: string
  active: boolean
  items: Item[]
}
type Unit = { id: number; name: string }

const folderKinds = (): [Folder['kind'], string][] => [
  ['marchbook', t('Marschbuch')],
  ['repertoire', t('Repertoire')],
  ['other', t('Sonstige Mappe')],
]

/** Feste Notenmappen (Marschbuch, Repertoire) für die App „HUBIplan“. */
export function ScoreFoldersPanel({
  base,
  arrangements,
  canEdit,
  live = false,
}: {
  base: string
  arrangements: [string, string][]
  canEdit: boolean
  /** Modul Musik an: Leitung für die Live-Vorgabe pflegen */
  live?: boolean
}) {
  const [editing, setEditing] = useState<Folder | 'new' | null>(null),
    [open, setOpen] = useState<number | null>(null),
    [error, setError] = useState('')
  const load = useLoad(async () => {
    const [folders, units] = await Promise.all([
      api.get<Folder[]>(base + 'score-folders/'),
      api.get<Unit[]>(base + 'score-folders/units/'),
    ])
    return { folders, units }
  }, [base])
  if (load.error) return <Alert kind="error">{load.error}</Alert>
  if (!load.data) return <p>{t('Lädt …')}</p>
  const { folders, units } = load.data
  const unitNames = (ids: number[]) =>
    ids.length
      ? ids.map((id) => units.find((u) => u.id === id)?.name || '').join(', ')
      : t('alle Musiker')
  const run = async (action: () => Promise<unknown>) => {
    setError('')
    try {
      await action()
      await load.reload()
    } catch (e) {
      setError(errorMessage(e))
    }
  }
  return (
    <div className="stack">
      <p>
        {t(
          'Feste Notenmappen wie Marschbuch oder Repertoire erscheinen in der App unter „Noten“. Jeder Musiker sieht darin nur die Noten seiner Stimme, soweit die Dokumentenablage sie für Mitglieder freigibt.',
        )}
      </p>
      {error && <Alert kind="error">{error}</Alert>}
      {canEdit && !editing && (
        <div className="button-row">
          <button
            className="button button-primary"
            onClick={async () => {
              if (await confirmLeave()) setEditing('new')
            }}
          >
            {t('Mappe anlegen')}
          </button>
        </div>
      )}
      {canEdit && editing && (
        <FolderForm
          key={editing === 'new' ? 'new' : editing.id}
          initial={editing === 'new' ? undefined : editing}
          units={units}
          onClose={() => setEditing(null)}
          onSave={async (values) => {
            if (editing === 'new') await api.post(base + 'score-folders/', values)
            else await api.patch(`${base}score-folders/${editing.id}/`, values)
            setEditing(null)
            await load.reload()
          }}
        />
      )}
      {!folders.length && (
        <MusicEmptyState>{t('Noch keine Notenmappen vorhanden.')}</MusicEmptyState>
      )}
      {folders.map((f) => (
        <article key={f.id} className="card stack music-record">
          <strong>{f.name}</strong>
          <p>
            {folderKinds().find((k) => k[0] === f.kind)?.[1]} · {t('Sichtbar für')}:{' '}
            {unitNames(f.departments)} · {tn('{n} Stück', '{n} Stücke', f.items.length)}
            {f.active ? '' : ` · ${t('Archiviert')}`}
          </p>
          {f.note && <p>{f.note}</p>}
          <div className="button-row">
            <button
              className="button button-ghost"
              aria-expanded={open === f.id}
              onClick={() => setOpen(open === f.id ? null : f.id)}
            >
              {open === f.id ? t('Stücke ausblenden') : t('Stücke zeigen')}
            </button>
            {canEdit && (
              <>
                <button
                  className="button button-ghost"
                  onClick={async () => {
                    if (await confirmLeave()) setEditing(f)
                  }}
                >
                  {t('Bearbeiten')}
                </button>
                <button
                  className="button button-ghost"
                  onClick={async () => {
                    if (
                      await confirmDialog({
                        message: t('Mappe „{name}“ löschen?', { name: f.name }),
                        confirmLabel: t('Löschen'),
                      })
                    )
                      await run(() => api.del(`${base}score-folders/${f.id}/`))
                  }}
                >
                  {t('Löschen')}
                </button>
              </>
            )}
          </div>
          {open === f.id && live && (
            <LeadersPanel base={base} target={{ folder: f.id }} canEdit={canEdit} />
          )}
          {open === f.id && (
            <FolderItems
              base={base}
              folder={f}
              arrangements={arrangements}
              canEdit={canEdit}
              run={run}
            />
          )}
        </article>
      ))}
    </div>
  )
}

function FolderItems({
  base,
  folder,
  arrangements,
  canEdit,
  run,
}: {
  base: string
  folder: Folder
  arrangements: [string, string][]
  canEdit: boolean
  run: (action: () => Promise<unknown>) => Promise<void>
}) {
  const used = new Set(folder.items.map((i) => String(i.arrangement)))
  const free = arrangements.filter(([id]) => !used.has(id))
  const [arrangement, setArrangement] = useState(''),
    [number, setNumber] = useState('')
  const move = (index: number, step: number) => {
    const ids = folder.items.map((i) => i.id)
    const [row] = ids.splice(index, 1)
    ids.splice(index + step, 0, row)
    return run(() => api.post(`${base}score-folders/${folder.id}/reorder/`, { items: ids }))
  }
  return (
    <div className="stack">
      {!folder.items.length && <p>{t('Die Mappe ist noch leer.')}</p>}
      {folder.items.length > 0 && (
        <ul className="item-list">
          {folder.items.map((i, index) => (
            <li key={i.id} className="item-row">
              <span className="item-row-info">
                {i.number && <strong>{t('Nr. {number}', { number: i.number })} </strong>}
                {i.title} · {i.arrangement_name}
              </span>
              {canEdit && (
                <span className="button-row">
                  <button
                    className="button button-ghost"
                    disabled={index === 0}
                    aria-label={t('{title} nach oben', { title: i.title })}
                    onClick={() => move(index, -1)}
                  >
                    ↑
                  </button>
                  <button
                    className="button button-ghost"
                    disabled={index === folder.items.length - 1}
                    aria-label={t('{title} nach unten', { title: i.title })}
                    onClick={() => move(index, 1)}
                  >
                    ↓
                  </button>
                  <NumberEdit
                    value={i.number}
                    title={i.title}
                    onSave={(value) =>
                      run(() => api.patch(`${base}score-folder-items/${i.id}/`, { number: value }))
                    }
                  />
                  <button
                    className="button button-ghost"
                    onClick={async () => {
                      if (
                        await confirmDialog({
                          message: t('„{title}“ aus der Mappe entfernen?', { title: i.title }),
                          confirmLabel: t('Entfernen'),
                        })
                      )
                        await run(() => api.del(`${base}score-folder-items/${i.id}/`))
                    }}
                  >
                    {t('Entfernen')}
                  </button>
                </span>
              )}
            </li>
          ))}
        </ul>
      )}
      {canEdit && (
        <form
          className="music-toolbar"
          onSubmit={async (e) => {
            e.preventDefault()
            if (!arrangement) return
            await run(() =>
              api.post(base + 'score-folder-items/', {
                folder: folder.id,
                arrangement: Number(arrangement),
                number,
              }),
            )
            setArrangement('')
            setNumber('')
          }}
        >
          <label>
            {t('Arrangement')}
            <select required value={arrangement} onChange={(e) => setArrangement(e.target.value)}>
              <option value="">—</option>
              {free.map(([v, l]) => (
                <option key={v} value={v}>
                  {l}
                </option>
              ))}
            </select>
          </label>
          <label>
            {t('Nummer (optional)')}
            <input maxLength={20} value={number} onChange={(e) => setNumber(e.target.value)} />
          </label>
          <button className="button button-primary">{t('Stück hinzufügen')}</button>
        </form>
      )}
    </div>
  )
}

function NumberEdit({
  value,
  title,
  onSave,
}: {
  value: string
  title: string
  onSave: (value: string) => Promise<void>
}) {
  const [draft, setDraft] = useState(value)
  return (
    <form
      className="button-row"
      onSubmit={async (e) => {
        e.preventDefault()
        await onSave(draft)
      }}
    >
      <input
        className="inline-edit"
        size={4}
        maxLength={20}
        aria-label={t('Nummer von {title}', { title })}
        value={draft}
        onChange={(e) => setDraft(e.target.value)}
      />
      {draft !== value && <button className="button button-ghost">{t('Nummer speichern')}</button>}
    </form>
  )
}

function FolderForm({
  initial,
  units,
  onSave,
  onClose,
}: {
  initial?: Folder
  units: Unit[]
  onSave: (values: Partial<Folder>) => Promise<void>
  onClose: () => void
}) {
  const [values, setValues] = useState({
      name: initial?.name || '',
      kind: initial?.kind || ('marchbook' as Folder['kind']),
      position: initial?.position ?? 0,
      departments: initial?.departments || [],
      note: initial?.note || '',
      active: initial?.active ?? true,
    }),
    [busy, setBusy] = useState(false),
    [error, setError] = useState('')
  const [clean] = useState(JSON.stringify(values))
  useDraftGuard(JSON.stringify(values) !== clean)
  return (
    <form
      className="card stack"
      onSubmit={async (e) => {
        e.preventDefault()
        setBusy(true)
        try {
          await onSave(values)
        } catch (err) {
          setError(errorMessage(err))
        } finally {
          setBusy(false)
        }
      }}
    >
      {error && <Alert kind="error">{error}</Alert>}
      <div className="music-form-fields">
        <label>
          {t('Name')}
          <input
            required
            maxLength={150}
            value={values.name}
            onChange={(e) => setValues({ ...values, name: e.target.value })}
          />
        </label>
        <label>
          {t('Art')}
          <select
            value={values.kind}
            onChange={(e) => setValues({ ...values, kind: e.target.value as Folder['kind'] })}
          >
            {folderKinds().map(([v, l]) => (
              <option key={v} value={v}>
                {l}
              </option>
            ))}
          </select>
        </label>
        <label>
          {t('Reihenfolge in der App')}
          <input
            type="number"
            min={0}
            max={1000}
            value={values.position}
            onChange={(e) => setValues({ ...values, position: Number(e.target.value) })}
          />
        </label>
        <label>
          <input
            type="checkbox"
            checked={values.active}
            onChange={(e) => setValues({ ...values, active: e.target.checked })}
          />
          {t('Aktiv')}
        </label>
        <label className="music-field-wide">
          {t('Hinweis')}
          <textarea
            maxLength={1000}
            value={values.note}
            onChange={(e) => setValues({ ...values, note: e.target.value })}
          />
        </label>
      </div>
      {units.length > 0 && (
        <fieldset>
          <legend>{t('Sichtbar für (leer: alle Musiker)')}</legend>
          {units.map((u) => (
            <label key={u.id}>
              <input
                type="checkbox"
                checked={values.departments.includes(u.id)}
                onChange={(e) =>
                  setValues({
                    ...values,
                    departments: e.target.checked
                      ? [...values.departments, u.id]
                      : values.departments.filter((d) => d !== u.id),
                  })
                }
              />
              {u.name}
            </label>
          ))}
        </fieldset>
      )}
      <div className="button-row">
        <button className="button button-primary" disabled={busy}>
          {t('Speichern')}
        </button>
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
    </form>
  )
}
