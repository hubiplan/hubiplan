import { useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { api } from '../../api/client.ts'
import { errorMessage, useLoad } from '../../components/forms.ts'
import { useDraftGuard, confirmLeave } from '../../components/leaveGuard.ts'
import { Alert } from '../../components/ui.tsx'
import { useActiveOrg } from '../../org/OrgContext.tsx'
import { t } from '../../i18n/index.ts'
import { confirmDialog } from '../../components/dialog.ts'
import { SettlementPanel } from './SettlementPanel.tsx'
import { ScoresPage } from './ScoresPage.tsx'
import { ProgramPanel } from './ProgramPanel.tsx'
import { PracticePage } from './PracticePage.tsx'
import { EnsembleTemplatesPage } from './EnsembleTemplatesPage.tsx'
import { StaffingPage } from './StaffingPage.tsx'
import { AvailabilityPage } from './AvailabilityPage.tsx'

type Row = { id: number; [key: string]: string | number | boolean | null }
type Choices = { events: Row[]; members: Row[]; partners: Row[] }
type Field = {
  key: string
  label: string
  type?: string
  options?: [string, string][]
  optional?: boolean
}
const formations: [string, string][] = [
  ['seated', t('Sitzend')],
  ['standing', t('Stehend')],
  ['march', t('Umzug')],
]
const statuses: [string, string][] = [
  ['pending', t('Angefragt')],
  ['accepted', t('Zugesagt')],
  ['declined', t('Abgesagt')],
]

export function MusicPage() {
  const org = useActiveOrg()
  const [params] = useSearchParams()
  if (!org.modules.includes('music') || !org.permissions.includes('music.view'))
    return <Alert kind="error">{t('Dafür fehlt dir die Berechtigung.')}</Alert>
  if (params.get('noten')) return <ScoresPage key={org.id} />
  if (params.get('proben')) return <PracticePage key={org.id} />
  if (params.get('vorlagen')) return <EnsembleTemplatesPage key={org.id} />
  if (params.get('verfuegbarkeit')) return <AvailabilityPage key={org.id} />
  if (/^\d+$/.test(params.get('besetzung') || ''))
    return (
      <StaffingPage
        key={`${org.id}-${params.get('besetzung')}`}
        performance={Number(params.get('besetzung'))}
      />
    )
  if (/^\d+$/.test(params.get('programm') || ''))
    return (
      <ProgramPanel
        key={`${org.id}-${params.get('programm')}`}
        performance={Number(params.get('programm'))}
      />
    )
  return <MusicWorkspace key={org.id} />
}

function MusicWorkspace() {
  const org = useActiveOrg()
  const [params, setParams] = useSearchParams()
  const [error, setError] = useState('')
  const base = `/api/orgs/${org.id}/music/`
  const load = useLoad(async () => {
    const [musicians, skills, performances, positions, assignments, choices] = await Promise.all([
      api.get<Row[]>(`${base}musicians/`),
      api.get<Row[]>(`${base}skills/`),
      api.get<Row[]>(`${base}performances/`),
      api.get<Row[]>(`${base}positions/`),
      api.get<Row[]>(`${base}assignments/`),
      api.get<Choices>(`${base}musicians/choices/`),
    ])
    return { musicians, skills, performances, positions, assignments, choices }
  }, [org.id])
  if (load.error) return <Alert kind="error">{load.error}</Alert>
  if (!load.data) return <p>{t('Lädt …')}</p>
  const d = load.data
  const settlement = d.performances.find((p) => String(p.id) === params.get('abrechnung'))
  if (settlement && org.modules.includes('finance') && org.permissions.includes('finance.view'))
    return (
      <SettlementPanel
        performance={settlement.id}
        title={String(settlement.title)}
        customer={Number(settlement.customer) || null}
        assignments={d.assignments
          .filter((a) => a.performance === settlement.id)
          .map((a) => ({
            id: a.id,
            name: String(d.musicians.find((m) => m.id === a.musician)?.display_name || a.musician),
          }))}
      />
    )
  const opts = (rows: Row[], name: string): [string, string][] =>
    rows.map((r) => [String(r.id), String(r[name] || r.id)])
  const musicianName = (id: unknown) =>
    String(d.musicians.find((m) => m.id === id)?.display_name || id)
  const fields: Record<string, Field[]> = {
    musicians: [
      {
        key: 'membership',
        label: t('Mitglied'),
        options: opts(d.choices.members, 'name'),
        optional: true,
      },
      { key: 'name', label: t('Gastname'), optional: true },
      { key: 'contact', label: t('Kontakt'), optional: true },
      { key: 'active', label: t('Aktiv'), type: 'checkbox' },
    ],
    skills: [
      { key: 'musician', label: t('Musiker'), options: opts(d.musicians, 'display_name') },
      { key: 'instrument', label: t('Instrument') },
      { key: 'register', label: t('Register / Stimme'), optional: true },
      { key: 'primary', label: t('Hauptinstrument'), type: 'checkbox' },
    ],
    performances: [
      { key: 'event', label: t('Termin'), options: opts(d.choices.events, 'title') },
      {
        key: 'customer',
        label: t('Auftraggeber'),
        options: opts(d.choices.partners, 'name'),
        optional: true,
      },
      { key: 'meeting_at', label: t('Treffzeit'), type: 'datetime-local', optional: true },
      { key: 'meeting_place', label: t('Treffpunkt'), optional: true },
      { key: 'setup_at', label: t('Aufbau'), type: 'datetime-local', optional: true },
      { key: 'uniform', label: t('Uniform'), optional: true },
      { key: 'formation', label: t('Spielform'), options: formations },
      { key: 'notes', label: t('Weitere Hinweise'), type: 'textarea', optional: true },
    ],
    positions: [
      { key: 'performance', label: t('Auftritt'), options: opts(d.performances, 'title') },
      { key: 'instrument', label: t('Instrument') },
      { key: 'register', label: t('Register / Stimme'), optional: true },
      { key: 'required', label: t('Sollbesetzung'), type: 'number' },
    ],
    assignments: [
      { key: 'performance', label: t('Auftritt'), options: opts(d.performances, 'title') },
      {
        key: 'position',
        label: t('Besetzungsposition'),
        options: d.positions.map((p) => [
          String(p.id),
          `${d.performances.find((a) => a.id === p.performance)?.title}: ${p.instrument} ${p.register}`,
        ]),
      },
      { key: 'musician', label: t('Musiker'), options: opts(d.musicians, 'display_name') },
      { key: 'status', label: t('Rückmeldung'), options: statuses },
    ],
  }
  const names: Record<string, string> = {
    musicians: t('Musiker'),
    skills: t('Instrumentale Fähigkeiten'),
    performances: t('Auftritte'),
    positions: t('Sollbesetzung'),
    assignments: t('Einteilungen'),
  }
  const kind = fields[params.get('art') || ''] ? params.get('art')! : 'performances'
  const selected = params.get('id')
  const rows =
    d[
      kind as keyof Pick<
        typeof d,
        'musicians' | 'skills' | 'performances' | 'positions' | 'assignments'
      >
    ]
  const row = rows.find((r) => String(r.id) === selected)
  const canEdit = org.permissions.includes('music.edit')
  const choose = async (art: string, id?: string) => {
    if (await confirmLeave()) {
      const next = new URLSearchParams(params)
      next.set('art', art)
      if (id) next.set('id', id)
      else next.delete('id')
      setParams(next)
    }
  }
  return (
    <section className="stack">
      <h1>{t('Musik')}</h1>
      <Link to="/musik?noten=1">{t('Notenbestand')}</Link>
      <Link to="/musik?proben=1">{t('Proben und Notenausgabe')}</Link>
      <Link to="/musik?vorlagen=1">{t('Besetzungsvorlagen')}</Link>
      <Link to="/musik?verfuegbarkeit=1">{t('Verfügbarkeiten')}</Link>
      <nav className="tabs">
        {Object.entries(names).map(([key, label]) => (
          <button
            key={key}
            className={`tab${kind === key ? ' active' : ''}`}
            onClick={() => choose(key)}
          >
            {label}
          </button>
        ))}
      </nav>
      <p>
        {t(
          'Auftritte ergänzen eigene Einzeltermine. Mitglieder beantworten ihre Einteilungen im eigenen Bereich.',
        )}
      </p>
      {error && <Alert kind="error">{error}</Alert>}
      {canEdit && !selected && (
        <button className="button button-primary" onClick={() => choose(kind, 'neu')}>
          {t('Anlegen')}
        </button>
      )}
      {canEdit && selected && (
        <Editor
          key={`${kind}-${selected}`}
          fields={fields[kind]}
          row={row}
          defaults={{ membership: params.get('mitglied') || '', event: params.get('termin') || '' }}
          onClose={() => choose(kind)}
          onSave={async (values) => {
            setError('')
            try {
              if (row) await api.patch(`${base}${kind}/${row.id}/`, values)
              else await api.post(`${base}${kind}/`, values)
              setParams({ art: kind })
              await load.reload()
            } catch (err) {
              setError(errorMessage(err))
            }
          }}
        />
      )}
      <div className="stack">
        {rows
          .filter(
            (r) =>
              kind !== 'musicians' ||
              !params.get('mitglied') ||
              String(r.membership) === params.get('mitglied'),
          )
          .map((r) => (
            <article className="card stack" key={r.id}>
              <strong>
                {kind === 'musicians'
                  ? r.display_name
                  : kind === 'performances'
                    ? r.title
                    : kind === 'assignments'
                      ? musicianName(r.musician)
                      : r.instrument}
              </strong>
              {['positions', 'assignments'].includes(kind) && (
                <p>{d.performances.find((p) => p.id === r.performance)?.title}</p>
              )}
              {kind === 'skills' && (
                <p>
                  {musicianName(r.musician)} · {r.register} ·{' '}
                  {r.primary ? t('Hauptinstrument') : t('Nebeninstrument')}
                </p>
              )}
              {kind === 'musicians' && (
                <p>
                  {r.contact} · {r.active ? t('Aktiv') : t('Inaktiv')}
                </p>
              )}
              {kind === 'performances' && (
                <>
                  <p>
                    {r.starts_at ? new Date(String(r.starts_at)).toLocaleString() : ''} –{' '}
                    {r.ends_at ? new Date(String(r.ends_at)).toLocaleString() : ''} · {r.location}
                  </p>
                  <p>
                    {r.meeting_at ? new Date(String(r.meeting_at)).toLocaleString() : ''} ·{' '}
                    {r.meeting_place} · {r.uniform} ·{' '}
                    {formations.find((f) => f[0] === r.formation)?.[1]}{' '}
                    {r.cancelled ? t('Abgesagt') : ''}
                  </p>
                  <p>{r.notes}</p>
                  <Link to={`/aufgaben?termin=${r.event}`}>{t('Aufgaben zum Auftritt')}</Link>
                  <Link to={`/musik?programm=${r.id}`}>{t('Musikalisches Programm')}</Link>
                  <Link to={`/musik?besetzung=${r.id}`}>{t('Besetzung planen')}</Link>
                  {org.modules.includes('finance') && org.permissions.includes('finance.view') && (
                    <Link to={`/musik?abrechnung=${r.id}`}>{t('Auftrittsabrechnung')}</Link>
                  )}
                  <Link to={`/termine?termin=${r.event}`}>{t('Zum Termin')}</Link>
                  <p>
                    {t('Besetzungsgröße')}:{' '}
                    {d.positions
                      .filter((p) => p.performance === r.id)
                      .reduce((n, p) => n + Number(p.required), 0)}
                  </p>
                </>
              )}
              {kind === 'positions' && (
                <p>
                  {r.register} · {t('Sollbesetzung')}: {r.required} · {t('Zugesagt')}:{' '}
                  {
                    d.assignments.filter((a) => a.position === r.id && a.status === 'accepted')
                      .length
                  }{' '}
                  · {t('Fehlend')}:{' '}
                  {Math.max(
                    0,
                    Number(r.required) -
                      d.assignments.filter((a) => a.position === r.id && a.status === 'accepted')
                        .length,
                  )}
                </p>
              )}
              {kind === 'assignments' && (
                <p>
                  {d.positions.find((p) => p.id === r.position)?.instrument} ·{' '}
                  {statuses.find((s) => s[0] === r.status)?.[1]}
                </p>
              )}
              {canEdit && (
                <button className="button button-ghost" onClick={() => choose(kind, String(r.id))}>
                  {t('Bearbeiten')}
                </button>
              )}
              {canEdit && ['skills', 'positions', 'assignments'].includes(kind) && (
                <button
                  className="button button-ghost"
                  onClick={async () => {
                    if (!(await confirmDialog(t('Eintrag entfernen?')))) return
                    try {
                      await api.del(`${base}${kind}/${r.id}/`)
                      await load.reload()
                    } catch (err) {
                      setError(errorMessage(err))
                    }
                  }}
                >
                  {t('Entfernen')}
                </button>
              )}
            </article>
          ))}
      </div>
    </section>
  )
}

function Editor({
  fields,
  row,
  defaults,
  onClose,
  onSave,
}: {
  fields: Field[]
  row?: Row
  defaults: Record<string, string>
  onClose: () => void
  onSave: (values: Record<string, unknown>) => Promise<void>
}) {
  const initial = Object.fromEntries(
    fields.map((f) => [
      f.key,
      row?.[f.key] ??
        (defaults[f.key] ||
          (f.type === 'checkbox'
            ? f.key === 'active'
            : f.type === 'number'
              ? 1
              : f.optional
                ? ''
                : f.options?.[0]?.[0] || '')),
    ]),
  )
  for (const field of fields) {
    if (field.type === 'datetime-local' && initial[field.key]) {
      const date = new Date(String(initial[field.key]))
      initial[field.key] = new Date(date.getTime() - date.getTimezoneOffset() * 60000)
        .toISOString()
        .slice(0, 16)
    }
  }
  const [values, setValues] = useState(initial)
  const [dirty, setDirty] = useState(false)
  const [busy, setBusy] = useState(false)
  useDraftGuard(dirty)
  return (
    <form
      className="card stack"
      onSubmit={async (e) => {
        e.preventDefault()
        setBusy(true)
        try {
          await onSave(
            Object.fromEntries(
              fields.map((f) => [
                f.key,
                values[f.key] === '' && f.options
                  ? null
                  : f.type === 'datetime-local' && values[f.key]
                    ? new Date(String(values[f.key])).toISOString()
                    : f.type === 'datetime-local'
                      ? null
                      : values[f.key],
              ]),
            ),
          )
        } finally {
          setBusy(false)
        }
      }}
    >
      {fields.map((f) => (
        <label key={f.key}>
          {f.label}
          {f.options ? (
            <select
              required={!f.optional}
              value={String(values[f.key] ?? '')}
              disabled={
                !!row &&
                ['membership', 'event', 'performance', 'position', 'musician'].includes(f.key)
              }
              onChange={(e) => {
                setValues({ ...values, [f.key]: e.target.value })
                setDirty(true)
              }}
            >
              {f.optional && <option value="">—</option>}
              {f.options.map(([v, l]) => (
                <option key={v} value={v}>
                  {l}
                </option>
              ))}
            </select>
          ) : f.type === 'textarea' ? (
            <textarea
              value={String(values[f.key])}
              onChange={(e) => {
                setValues({ ...values, [f.key]: e.target.value })
                setDirty(true)
              }}
            />
          ) : (
            <input
              required={!f.optional && f.type !== 'checkbox'}
              type={f.type || 'text'}
              min={f.type === 'number' ? 1 : undefined}
              max={f.type === 'number' ? 500 : undefined}
              value={f.type === 'checkbox' ? undefined : String(values[f.key] ?? '')}
              checked={f.type === 'checkbox' ? Boolean(values[f.key]) : undefined}
              onChange={(e) => {
                setValues({
                  ...values,
                  [f.key]: f.type === 'checkbox' ? e.target.checked : e.target.value,
                })
                setDirty(true)
              }}
            />
          )}
        </label>
      ))}
      <div className="actions">
        <button className="button button-primary" disabled={busy}>
          {t('Speichern')}
        </button>
        <button className="button button-ghost" type="button" onClick={onClose}>
          {t('Abbrechen')}
        </button>
      </div>
    </form>
  )
}
