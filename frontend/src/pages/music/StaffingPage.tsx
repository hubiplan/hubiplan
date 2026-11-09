import { useState } from 'react'
import { Link } from 'react-router-dom'
import { api, newRequestKey } from '../../api/client.ts'
import { errorMessage, useLoad } from '../../components/forms.ts'
import { confirmDiscard, useDraftGuard } from '../../components/leaveGuard.ts'
import { Alert } from '../../components/ui.tsx'
import { useActiveOrg } from '../../org/OrgContext.tsx'
import { t } from '../../i18n/index.ts'
import type { EnsembleTemplate } from './EnsembleTemplatesPage.tsx'
import { AvailabilityHint } from './AvailabilityPage.tsx'
import { MusicHeader, MusicEmptyState, MusicStatus } from './MusicLayout.tsx'
import { GuestAccessPanel } from './GuestAccessPanel.tsx'
import { LeadersPanel } from './LeadersPanel.tsx'

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
  assignments: {
    id: number
    name: string
    position: number
    status: string
    availability?: string[]
    is_guest?: boolean
  }[]
  candidates: {
    id: number
    name: string
    positions: number[]
    availability?: string[]
    preferred_positions?: number[]
  }[]
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
  const [replacement, setReplacement] = useState<number | null>(null)
  const [guest, setGuest] = useState<number | null>(null)
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
  const candidates = plan.candidates
    .filter(
      (m) => replacement === null || (m.positions.includes(replacement) && !m.availability?.length),
    )
    .sort((a, b) =>
      replacement === null
        ? 0
        : Number(b.preferred_positions?.includes(replacement) || false) -
          Number(a.preferred_positions?.includes(replacement) || false),
    )
  const blockedSelection = Object.keys(selected).some((id) => {
    const m = plan.candidates.find((v) => v.id === Number(id))
    return !m || !!m.availability?.length
  })
  function select(next: Record<number, number>) {
    setSelected(next)
    setAssignKey(newRequestKey())
    setMessage('')
  }
  return (
    <section className="stack music-page">
      <MusicHeader title={t('Besetzung planen')} context={plan.title} />
      <div className="music-actions">
        <Link className="button button-ghost" to="/musik?art=assignments">
          {t('Einteilungen bearbeiten')}
        </Link>
      </div>
      {error && <Alert kind="error">{error}</Alert>}
      {message && <Alert kind="success">{message}</Alert>}
      {plan.cancelled && <Alert kind="error">{t('Auftritt abgesagt')}</Alert>}
      <article className="card stack music-record">
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
      <article className="card stack music-record">
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
      <article className="card stack music-record">
        <h2>{t('Sammeleinteilung')}</h2>
        {replacement !== null && (
          <div className="stack">
            <p>
              {t('Ersatz für diese Position')}:{' '}
              {plan.positions.find((p) => p.id === replacement)?.instrument}{' '}
              {plan.positions.find((p) => p.id === replacement)?.register}
            </p>
            <button className="button button-ghost" onClick={() => setReplacement(null)}>
              {t('Alle Kandidaten anzeigen')}
            </button>
          </div>
        )}
        <p>
          {t(
            'Aktive, noch nicht eingeteilte Musiker mit passender instrumentaler Fähigkeit auswählen. Neue Einteilungen beginnen als Angefragt; bestehende Absagen werden nicht überschrieben.',
          )}
        </p>
        {canEdit && (
          <>
            <div className="music-candidates">
              {candidates.map((m) => {
                const matching = counts.filter(
                  (p) =>
                    m.positions.includes(p.id) && (replacement === null || p.id === replacement),
                )
                const first = matching.find((p) => p.assigned < p.required)
                return (
                  <div className="music-candidate stack" key={m.id}>
                    <label>
                      <input
                        type="checkbox"
                        disabled={
                          busy ||
                          plan.cancelled ||
                          ((!first || !!m.availability?.length) && !(m.id in selected))
                        }
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
                    <AvailabilityHint reasons={m.availability} />
                    <label>
                      {t('Besetzungsposition für {name}', { name: m.name })}
                      <select
                        disabled={busy || !(m.id in selected) || !!m.availability?.length}
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
            </div>
            {!candidates.length && <p>{t('Keine weiteren passenden Musiker vorhanden.')}</p>}
            {Object.keys(selected).length > 0 && (
              <button className="button button-ghost" disabled={busy} onClick={() => select({})}>
                {t('Auswahl zurücksetzen')}
              </button>
            )}
            {overfull && (
              <Alert kind="error">
                {t(
                  'Die Auswahl überschreitet die freie Sollbesetzung. Bitte die Auswahl oder die Sollzahl anpassen.',
                )}
              </Alert>
            )}
            <button
              className="button button-primary"
              disabled={
                busy ||
                plan.cancelled ||
                !Object.keys(selected).length ||
                overfull ||
                blockedSelection
              }
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
                  await load.reload()
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
      <article className="card stack music-record">
        <LeadersPanel base={base} target={{ performance }} canEdit={canEdit} />
      </article>
      <article className="card stack music-record">
        <h2>{t('Bestehende Einteilungen')}</h2>
        {!plan.assignments.length && <MusicEmptyState />}
        {plan.assignments.map((a) => (
          <div className="music-row music-actions" key={a.id}>
            <strong>{a.name}</strong>
            <span>
              {plan.positions.find((p) => p.id === a.position)?.instrument}{' '}
              {plan.positions.find((p) => p.id === a.position)?.register}
            </span>
            <MusicStatus status={a.status} />
            <AvailabilityHint reasons={a.availability} />
            {canEdit && a.is_guest && (
              <button className="button button-ghost" onClick={() => setGuest(a.id)}>
                {t('Gasteinladung verwalten')}
              </button>
            )}
            {canEdit && a.status === 'declined' && !plan.cancelled && (
              <button
                className="button button-ghost"
                onClick={async () => {
                  if (await confirmDiscard(Object.keys(selected).length > 0)) {
                    select({})
                    setReplacement(a.position)
                  }
                }}
              >
                {t('Ersatz suchen')}
              </button>
            )}
          </div>
        ))}
      </article>
      {canEdit && guest !== null && (
        <GuestAccessPanel
          key={guest}
          assignment={guest}
          name={plan.assignments.find((a) => a.id === guest)?.name || ''}
          onClose={() => setGuest(null)}
        />
      )}
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
