import { useState } from 'react'
import { Link } from 'react-router-dom'
import { api, newRequestKey } from '../../api/client.ts'
import { errorMessage, useLoad } from '../../components/forms.ts'
import { confirmLeave, useDraftGuard } from '../../components/leaveGuard.ts'
import { Alert } from '../../components/ui.tsx'
import { useActiveOrg } from '../../org/OrgContext.tsx'
import { t } from '../../i18n/index.ts'

export type TemplatePosition = { instrument: string; register: string; required: number }
export type EnsembleTemplate = {
  id: number
  name: string
  note: string
  active: boolean
  positions: TemplatePosition[]
}

export function EnsembleTemplatesPage() {
  const org = useActiveOrg(),
    url = `/api/orgs/${org.id}/music/ensemble-templates/`
  const load = useLoad(() => api.get<EnsembleTemplate[]>(url), [org.id])
  const [selected, setSelected] = useState<EnsembleTemplate | 'new' | null>(null)
  if (load.error) return <Alert kind="error">{load.error}</Alert>
  if (!load.data) return <p>{t('Lädt …')}</p>
  const canEdit = org.permissions.includes('music.edit')
  return (
    <section className="stack">
      <Link to="/musik">{t('Zurück')}</Link>
      <h1>{t('Besetzungsvorlagen')}</h1>
      <p>
        {t(
          'Vorlagen speichern Instrumente, Stimmen und Sollzahlen. Änderungen an einer Vorlage wirken erst beim erneuten Anwenden auf einen Auftritt.',
        )}
      </p>
      {canEdit && (
        <button
          className="button button-primary"
          onClick={async () => {
            if (await confirmLeave()) setSelected('new')
          }}
        >
          {t('Vorlage anlegen')}
        </button>
      )}
      {canEdit && selected && (
        <TemplateForm
          key={selected === 'new' ? 'new' : selected.id}
          initial={selected === 'new' ? undefined : selected}
          url={url}
          onClose={() => setSelected(null)}
          onSaved={() => load.reload()}
        />
      )}
      {load.data.map((row) => (
        <article className="card stack" key={row.id}>
          <strong>
            {row.name} · {row.active ? t('Aktiv') : t('Archiviert')}
          </strong>
          <p>{row.note}</p>
          {row.positions.map((p, i) => (
            <p key={i}>
              {p.instrument} {p.register} · {t('Sollbesetzung')}: {p.required}
            </p>
          ))}
          {canEdit && (
            <button
              className="button button-ghost"
              onClick={async () => {
                if (await confirmLeave()) setSelected(row)
              }}
            >
              {t('Bearbeiten')}
            </button>
          )}
        </article>
      ))}
    </section>
  )
}

function TemplateForm({
  initial,
  url,
  onClose,
  onSaved,
}: {
  initial?: EnsembleTemplate
  url: string
  onClose: () => void
  onSaved: () => Promise<unknown>
}) {
  const [values, setValues] = useState(() => ({
      name: initial?.name || '',
      note: initial?.note || '',
      active: initial?.active ?? true,
      positions: initial?.positions.map((p) => ({ ...p })) || [
        { instrument: '', register: '', required: 1 },
      ],
    })),
    [clean] = useState(() => JSON.stringify(values)),
    [busy, setBusy] = useState(false),
    [error, setError] = useState(''),
    [key, setKey] = useState(newRequestKey)
  useDraftGuard(JSON.stringify(values) !== clean)
  function update(next: typeof values) {
    setValues(next)
    setKey(newRequestKey())
  }
  return (
    <form
      className="card stack"
      onSubmit={async (e) => {
        e.preventDefault()
        setBusy(true)
        setError('')
        try {
          if (initial) await api.patch(`${url}${initial.id}/`, values)
          else await api.post(url, values, key)
          await onSaved()
          onClose()
        } catch (e) {
          setError(errorMessage(e))
        } finally {
          setBusy(false)
        }
      }}
    >
      {error && <Alert kind="error">{error}</Alert>}
      <fieldset disabled={busy} className="stack">
        <label>
          {t('Name der Besetzungsvorlage')}
          <input
            required
            maxLength={150}
            value={values.name}
            onChange={(e) => update({ ...values, name: e.target.value })}
          />
        </label>
        <label>
          {t('Hinweis')}
          <textarea
            maxLength={1000}
            value={values.note}
            onChange={(e) => update({ ...values, note: e.target.value })}
          />
        </label>
        <label>
          <input
            type="checkbox"
            checked={values.active}
            onChange={(e) => update({ ...values, active: e.target.checked })}
          />
          {t('Aktiv')}
        </label>
        {values.positions.map((p, i) => (
          <fieldset className="stack" key={i}>
            <legend>
              {t('Besetzungsposition')} {i + 1}
            </legend>
            <label>
              {t('Instrument')}
              <input
                required
                maxLength={100}
                value={p.instrument}
                onChange={(e) =>
                  update({
                    ...values,
                    positions: values.positions.map((v, n) =>
                      n === i ? { ...v, instrument: e.target.value } : v,
                    ),
                  })
                }
              />
            </label>
            <label>
              {t('Register / Stimme')}
              <input
                maxLength={100}
                value={p.register}
                onChange={(e) =>
                  update({
                    ...values,
                    positions: values.positions.map((v, n) =>
                      n === i ? { ...v, register: e.target.value } : v,
                    ),
                  })
                }
              />
            </label>
            <label>
              {t('Sollbesetzung')}
              <input
                required
                type="number"
                min={1}
                max={500}
                value={p.required}
                onChange={(e) =>
                  update({
                    ...values,
                    positions: values.positions.map((v, n) =>
                      n === i ? { ...v, required: Number(e.target.value) } : v,
                    ),
                  })
                }
              />
            </label>
            <button
              type="button"
              className="button button-ghost"
              disabled={values.positions.length === 1}
              onClick={() =>
                update({ ...values, positions: values.positions.filter((_, n) => n !== i) })
              }
            >
              {t('Entfernen')}
            </button>
          </fieldset>
        ))}
        <button
          type="button"
          className="button button-ghost"
          disabled={values.positions.length >= 100}
          onClick={() =>
            update({
              ...values,
              positions: [...values.positions, { instrument: '', register: '', required: 1 }],
            })
          }
        >
          {t('Besetzungsposition hinzufügen')}
        </button>
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
