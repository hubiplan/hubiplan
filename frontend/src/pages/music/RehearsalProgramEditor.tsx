import { useState } from 'react'
import { api } from '../../api/client.ts'
import { errorMessage, useLoad } from '../../components/forms.ts'
import { confirmDiscard, confirmLeave, useDraftGuard } from '../../components/leaveGuard.ts'
import { confirmDialog } from '../../components/dialog.ts'
import { Alert } from '../../components/ui.tsx'
import { t } from '../../i18n/index.ts'

type Item = { arrangement: number; focus: string; title?: string }
type Content = { focus: string; items: Item[] }
type Program = Content & { overridden: boolean; is_series: boolean; template: Content }
type Props = {
  url: string
  originalStart: string
  startsAt: string
  title: string
  arrangements: { id: number; name: string }[]
  onClose: () => void
  onSaved: () => Promise<unknown>
}

export function RehearsalProgramEditor(props: Props) {
  const load = useLoad(
    () =>
      api.get<Program>(`${props.url}?original_start=${encodeURIComponent(props.originalStart)}`),
    [props.url, props.originalStart],
  )
  if (load.error) return <Alert kind="error">{load.error}</Alert>
  if (!load.data) return <p>{t('Lädt …')}</p>
  return <ProgramForm {...props} initial={load.data} />
}

function editable(content: Content): Content {
  return {
    focus: content.focus,
    items: content.items.map(({ arrangement, focus }) => ({ arrangement, focus })),
  }
}

function ProgramForm({ initial, ...props }: Props & { initial: Program }) {
  const [scope, setScope] = useState('occurrence'),
    [values, setValues] = useState(() => editable(initial)),
    [clean, setClean] = useState(() => JSON.stringify(editable(initial))),
    [busy, setBusy] = useState(false),
    [error, setError] = useState('')
  const dirty = JSON.stringify(values) !== clean
  useDraftGuard(dirty)
  async function save(action: string) {
    setBusy(true)
    setError('')
    try {
      await api.post(props.url, { original_start: props.originalStart, scope: action, ...values })
      setClean(JSON.stringify(values))
      await props.onSaved()
      props.onClose()
    } catch (e) {
      setError(errorMessage(e))
    } finally {
      setBusy(false)
    }
  }
  return (
    <form
      className="card stack"
      onSubmit={async (e) => {
        e.preventDefault()
        await save(scope)
      }}
    >
      <h2>
        {t('Probenprogramm bearbeiten')}: {props.title} ·{' '}
        {new Date(props.startsAt).toLocaleString()}
      </h2>
      {error && <Alert kind="error">{error}</Alert>}
      <fieldset disabled={busy} className="music-form-fields">
        {initial.is_series && (
          <label>
            {t('Änderungen gelten für')}
            <select
              value={scope}
              onChange={async (e) => {
                const next = e.target.value
                if (!(await confirmDiscard(dirty))) return
                const content = editable(next === 'series' ? initial.template : initial)
                setScope(next)
                setValues(content)
                setClean(JSON.stringify(content))
              }}
            >
              <option value="occurrence">{t('Nur diesen Termin')}</option>
              <option value="series">{t('Gesamte Serie')}</option>
            </select>
          </label>
        )}
        <p>
          {scope === 'series'
            ? t(
                'Die Serienvorlage ändert sich. Termine mit eigenem Programm behalten ihre Inhalte.',
              )
            : t('Dieser Termin erhält ein eigenes Programm. Andere Termine bleiben unverändert.')}
        </p>
        <label>
          {t('Probenschwerpunkt')}
          <textarea
            maxLength={2000}
            value={values.focus}
            onChange={(e) => setValues({ ...values, focus: e.target.value })}
          />
        </label>
        {values.items.map((item, index) => (
          <fieldset key={index} className="music-position-fields">
            <legend>
              {t('Probenstück')} {index + 1}
            </legend>
            <label>
              {t('Arrangement')}
              <select
                required
                value={item.arrangement}
                onChange={(e) =>
                  setValues({
                    ...values,
                    items: values.items.map((v, i) =>
                      i === index ? { ...v, arrangement: Number(e.target.value) } : v,
                    ),
                  })
                }
              >
                {props.arrangements.map((a) => (
                  <option key={a.id} value={a.id}>
                    {a.name}
                  </option>
                ))}
              </select>
            </label>
            <label>
              {t('Schwerpunkt für dieses Stück')}
              <input
                maxLength={500}
                value={item.focus}
                onChange={(e) =>
                  setValues({
                    ...values,
                    items: values.items.map((v, i) =>
                      i === index ? { ...v, focus: e.target.value } : v,
                    ),
                  })
                }
              />
            </label>
            <button
              type="button"
              className="button button-ghost"
              onClick={() =>
                setValues({ ...values, items: values.items.filter((_, i) => i !== index) })
              }
            >
              {t('Entfernen')}
            </button>
          </fieldset>
        ))}
        <button
          type="button"
          className="button button-ghost"
          disabled={!props.arrangements.length || values.items.length >= 200}
          onClick={() =>
            setValues({
              ...values,
              items: [...values.items, { arrangement: props.arrangements[0].id, focus: '' }],
            })
          }
        >
          {t('Probenstück hinzufügen')}
        </button>
        <div className="actions">
          <button className="button button-primary">{t('Speichern')}</button>
          <button
            type="button"
            className="button button-ghost"
            onClick={async () => {
              if (await confirmLeave()) props.onClose()
            }}
          >
            {t('Abbrechen')}
          </button>
          {initial.overridden && scope === 'occurrence' && (
            <button
              type="button"
              className="button button-ghost"
              onClick={async () => {
                if (
                  await confirmDialog(
                    t('Eigenes Programm entfernen und die aktuelle Serienvorlage übernehmen?'),
                  )
                )
                  await save('inherit')
              }}
            >
              {t('Serienprogramm übernehmen')}
            </button>
          )}
        </div>
      </fieldset>
    </form>
  )
}
