import { useState } from 'react'
import { Link } from 'react-router-dom'
import { api, newRequestKey } from '../../api/client.ts'
import { errorMessage, useLoad } from '../../components/forms.ts'
import { confirmDiscard, useDraftGuard } from '../../components/leaveGuard.ts'
import { Alert } from '../../components/ui.tsx'
import { useActiveOrg } from '../../org/OrgContext.tsx'
import { t } from '../../i18n/index.ts'
import type { EnsembleTemplate } from './EnsembleTemplatesPage.tsx'

type Position = {
  id: number
  instrument: string
  register: string
  required: number
  assigned: number
}
type Plan = {
  title: string
  cancelled: boolean
  positions: Position[]
  assignments: { id: number; name: string; position: number; status: string }[]
  candidates: { id: number; name: string; positions: number[] }[]
}

export function StaffingPage({ performance }: { performance: number }) {
  const org = useActiveOrg(),
    base = `/api/orgs/${org.id}/music/`,
    url = `${base}performances/${performance}/staffing/`
  const load = useLoad(async () => {
    const [plan, templates] = await Promise.all([
      api.get<Plan>(url),
      api.get<EnsembleTemplate[]>(base + 'ensemble-templates/'),
    ])
    return { plan, templates }
  }, [org.id, performance])
  const [template, setTemplate] = useState(''),
    [selected, setSelected] = useState<Record<number, number>>({}),
    [busy, setBusy] = useState(false),
    [error, setError] = useState(''),
    [message, setMessage] = useState(''),
    [applyKey, setApplyKey] = useState(newRequestKey),
    [assignKey, setAssignKey] = useState(newRequestKey)
  useDraftGuard(Object.keys(selected).length > 0)
  if (load.error) return <Alert kind="error">{load.error}</Alert>
  if (!load.data) return <p>{t('Lädt …')}</p>
  const { plan, templates } = load.data,
    canEdit = org.permissions.includes('music.edit'),
    chosenTemplate = templates.find((v) => String(v.id) === template && v.active)
  const label = (p: Position) => `${p.instrument} ${p.register}`.trim()
  const counts = plan.positions.map((p) => ({
    ...p,
    selected: Object.values(selected).filter((id) => id === p.id).length,
  }))
  const overfull = counts.some((p) => p.selected > 0 && p.assigned + p.selected > p.required)
  function select(next: Record<number, number>) {
    setSelected(next)
    setAssignKey(newRequestKey())
    setMessage('')
  }
  return (
    <section className="stack">
      <Link to="/musik">{t('Zurück')}</Link>
      <h1>
        {t('Besetzung planen')}: {plan.title}
      </h1>
      <Link to="/musik?vorlagen=1">{t('Besetzungsvorlagen')}</Link>
      {error && <Alert kind="error">{error}</Alert>}
      {message && <Alert kind="success">{message}</Alert>}
      {plan.cancelled && <Alert kind="error">{t('Auftritt abgesagt')}</Alert>}
      <article className="card stack">
        <h2>{t('Besetzungsvorlage anwenden')}</h2>
        <p>
          {t(
            'Die Vorlage ergänzt fehlende Stimmen und erhöht vorhandene Sollzahlen bei Bedarf. Andere Positionen, Einteilungen und Rückmeldungen bleiben erhalten.',
          )}
        </p>
        {canEdit && (
          <>
            <label>
              {t('Besetzungsvorlage')}
              <select
                disabled={busy}
                value={template}
                onChange={(e) => {
                  setTemplate(e.target.value)
                  setApplyKey(newRequestKey())
                }}
              >
                <option value="">{t('Bitte wählen')}</option>
                {templates
                  .filter((v) => v.active)
                  .map((v) => (
                    <option key={v.id} value={v.id}>
                      {v.name}
                    </option>
                  ))}
              </select>
            </label>
            {chosenTemplate && (
              <div>
                {chosenTemplate.positions.map((p, i) => (
                  <p key={i}>
                    {p.instrument} {p.register} · {t('Sollbesetzung')}: {p.required}
                  </p>
                ))}
              </div>
            )}
            <button
              className="button button-primary"
              disabled={busy || !chosenTemplate}
              onClick={async () => {
                if (!(await confirmDiscard(Object.keys(selected).length > 0))) return
                setBusy(true)
                setError('')
                setMessage('')
                try {
                  await api.post(
                    url,
                    { action: 'apply_template', template: Number(template) },
                    applyKey,
                  )
                  setSelected({})
                  setAssignKey(newRequestKey())
                  setApplyKey(newRequestKey())
                  await load.reload()
                  setMessage(t('Besetzungsvorlage angewendet.'))
                } catch (e) {
                  setError(errorMessage(e))
                } finally {
                  setBusy(false)
                }
              }}
            >
              {t('Vorlage anwenden')}
            </button>
          </>
        )}
      </article>
      <article className="card stack">
        <h2>{t('Sollbesetzung')}</h2>
        {counts.map((p) => (
          <p key={p.id}>
            {label(p)} · {t('Sollbesetzung')}: {p.required} · {t('Eingeteilt')}: {p.assigned} ·{' '}
            {t('Ausgewählt')}: {p.selected} · {t('Freie Plätze')}:{' '}
            {Math.max(0, p.required - p.assigned - p.selected)}
          </p>
        ))}
        {!counts.length && (
          <p>
            {t('Zuerst eine Besetzungsvorlage anwenden oder Sollpositionen beim Auftritt anlegen.')}
          </p>
        )}
        {canEdit && plan.positions.length > 0 && (
          <SaveTemplate url={url} onSaved={() => load.reload()} />
        )}
      </article>
      <article className="card stack">
        <h2>{t('Sammeleinteilung')}</h2>
        <p>
          {t(
            'Aktive, noch nicht eingeteilte Musiker mit passender instrumentaler Fähigkeit auswählen. Neue Einteilungen beginnen als Angefragt; bestehende Absagen werden nicht überschrieben.',
          )}
        </p>
        {canEdit && (
          <>
            {plan.candidates.map((m) => {
              const matching = counts.filter((p) => m.positions.includes(p.id))
              const first = matching.find((p) => p.assigned < p.required)
              return (
                <div className="card stack" key={m.id}>
                  <label>
                    <input
                      type="checkbox"
                      disabled={busy || plan.cancelled || !first}
                      checked={m.id in selected}
                      onChange={(e) => {
                        const next = { ...selected }
                        if (e.target.checked && first) next[m.id] = first.id
                        else delete next[m.id]
                        select(next)
                      }}
                    />
                    {m.name}
                  </label>
                  <label>
                    {t('Besetzungsposition für {name}', { name: m.name })}
                    <select
                      disabled={busy || !(m.id in selected)}
                      value={selected[m.id] ?? first?.id ?? matching[0]?.id ?? ''}
                      onChange={(e) => select({ ...selected, [m.id]: Number(e.target.value) })}
                    >
                      {matching.map((p) => (
                        <option key={p.id} value={p.id} disabled={p.assigned >= p.required}>
                          {label(p)}
                        </option>
                      ))}
                    </select>
                  </label>
                </div>
              )
            })}
            {!plan.candidates.length && <p>{t('Keine weiteren passenden Musiker vorhanden.')}</p>}
            {overfull && (
              <Alert kind="error">
                {t(
                  'Die Auswahl überschreitet die freie Sollbesetzung. Bitte die Auswahl oder die Sollzahl anpassen.',
                )}
              </Alert>
            )}
            <button
              className="button button-primary"
              disabled={busy || plan.cancelled || !Object.keys(selected).length || overfull}
              onClick={async () => {
                setBusy(true)
                setError('')
                setMessage('')
                try {
                  await api.post(
                    url,
                    {
                      action: 'assign',
                      assignments: Object.entries(selected).map(([musician, position]) => ({
                        musician: Number(musician),
                        position,
                      })),
                    },
                    assignKey,
                  )
                  setSelected({})
                  setAssignKey(newRequestKey())
                  await load.reload()
                  setMessage(t('Ausgewählte Musiker wurden angefragt.'))
                } catch (e) {
                  setError(errorMessage(e))
                } finally {
                  setBusy(false)
                }
              }}
            >
              {t('Ausgewählte Musiker anfragen')}
            </button>
          </>
        )}
      </article>
      <article className="card stack">
        <h2>{t('Bestehende Einteilungen')}</h2>
        {plan.assignments.map((a) => (
          <p key={a.id}>
            {a.name} · {plan.positions.find((p) => p.id === a.position)?.instrument}{' '}
            {plan.positions.find((p) => p.id === a.position)?.register} ·{' '}
            {a.status === 'accepted'
              ? t('Zugesagt')
              : a.status === 'declined'
                ? t('Abgesagt')
                : t('Angefragt')}
          </p>
        ))}
      </article>
    </section>
  )
}

function SaveTemplate({ url, onSaved }: { url: string; onSaved: () => Promise<unknown> }) {
  const [name, setName] = useState(''),
    [key, setKey] = useState(newRequestKey),
    [busy, setBusy] = useState(false),
    [error, setError] = useState('')
  useDraftGuard(name !== '')
  return (
    <form
      className="stack"
      onSubmit={async (e) => {
        e.preventDefault()
        setBusy(true)
        setError('')
        try {
          await api.post(url, { action: 'save_template', name }, key)
          setName('')
          setKey(newRequestKey())
          await onSaved()
        } catch (e) {
          setError(errorMessage(e))
        } finally {
          setBusy(false)
        }
      }}
    >
      {error && <Alert kind="error">{error}</Alert>}
      <label>
        {t('Name der Besetzungsvorlage')}
        <input
          required
          disabled={busy}
          maxLength={150}
          value={name}
          onChange={(e) => {
            setName(e.target.value)
            setKey(newRequestKey())
          }}
        />
      </label>
      <button className="button button-ghost" disabled={busy}>
        {t('Auftrittsbesetzung als Vorlage speichern')}
      </button>
    </form>
  )
}
