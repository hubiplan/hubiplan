import { useState } from 'react'
import { CustodyRemindersPage } from './CustodyRemindersPage.tsx'
import { EngagementPage } from './EngagementPage.tsx'
import { PayoutRunsPage } from './PayoutRunsPage.tsx'
import { Link, Navigate, useLocation, useSearchParams } from 'react-router-dom'
import { api } from '../../api/client.ts'
import { errorMessage, formatDateTime, useLoad } from '../../components/forms.ts'
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
import { EquipmentPage } from './EquipmentPage.tsx'
import { PerformanceOverview } from './PerformanceOverview.tsx'
import { MusicLayout, MusicHeader, MusicEmptyState } from './MusicLayout.tsx'

type Row = { id: number; [key: string]: string | number | boolean | null }
type Choices = { events: Row[]; members: Row[]; partners: Row[] }
type Field = {
  key: string
  label: string
  type?: string
  options?: [string, string][]
  optional?: boolean
  initial?: number
  min?: number
  max?: number
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
  if (!org.modules.includes('music') || !org.permissions.includes('music.view'))
    return <Alert kind="error">{t('Dafür fehlt dir die Berechtigung.')}</Alert>
  return (
    <MusicLayout>
      <MusicRoute />
    </MusicLayout>
  )
}

/** Frühere Adressen /musik/noten … → /musik/noten (Menüprüfung M-08) */
const OLD_AREAS: Record<string, string> = {
  uebersicht: 'uebersicht',
  noten: 'noten',
  proben: 'proben',
  verfuegbarkeit: 'verfuegbarkeit',
  vorlagen: 'vorlagen',
  erinnerungen: 'erinnerungen',
  auszahlungen: 'auszahlungen',
  ausstattung: 'ausstattung',
}

/** Bereich aus der Adresse /musik/<bereich> */
export function musicArea(pathname: string): string {
  return pathname.replace(/^\/musik\/?/, '').split('/')[0] ?? ''
}

function MusicRoute() {
  const org = useActiveOrg()
  const [params] = useSearchParams()
  const { pathname } = useLocation()
  const old = Object.keys(OLD_AREAS).find((k) => params.get(k))
  if (old) {
    const rest = new URLSearchParams(params)
    rest.delete(old)
    const query = rest.toString()
    return <Navigate to={`/musik/${OLD_AREAS[old]}${query ? `?${query}` : ''}`} replace />
  }
  const area = musicArea(pathname)
  if (area === 'erinnerungen') return <CustodyRemindersPage key={org.id} />
  if (/^\d+$/.test(params.get('vereinbarung') || ''))
    return (
      <EngagementPage
        key={`${org.id}-${params.get('vereinbarung')}`}
        performance={Number(params.get('vereinbarung'))}
      />
    )
  if (area === 'auszahlungen') return <PayoutRunsPage key={org.id} />
  if (area === 'uebersicht') return <PerformanceOverview key={org.id} />
  if (area === 'ausstattung') return <EquipmentPage key={org.id} />
  if (area === 'noten') return <ScoresPage key={org.id} />
  if (area === 'proben') return <PracticePage key={org.id} />
  if (area === 'vorlagen') return <EnsembleTemplatesPage key={org.id} />
  if (area === 'verfuegbarkeit') return <AvailabilityPage key={org.id} />
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
  if (area !== '' && area !== 'musiker') return <Navigate to="/musik" replace />
  return <MusicWorkspace key={org.id} />
}

function MusicWorkspace() {
  const org = useActiveOrg()
  const [params, setParams] = useSearchParams()
  const { pathname } = useLocation()
  const [error, setError] = useState('')
  const [filter, setFilter] = useState({ kind: '', value: '' })
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
      {
        key: 'guest_email',
        label: t('E-Mail-Adresse für Gasteinladungen'),
        type: 'email',
        optional: true,
      },
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
      {
        key: 'remind_days',
        label: t('Erinnerung Tage vorher (0 = aus)'),
        type: 'number',
        initial: 3,
        min: 0,
        max: 30,
      },
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
  const kind = fields[params.get('art') || '']
    ? params.get('art')!
    : musicArea(pathname) === 'musiker'
      ? 'musicians'
      : 'performances'
  const search = filter.kind === kind ? filter.value : ''
  const musicianArea = ['musicians', 'skills'].includes(kind)
  const descriptions: Record<string, string> = {
    musicians: t('Mitglieder und Gastmusiker verwalten und ihre Instrumente hinterlegen.'),
    skills: t('Instrumente und Stimmen zuordnen, damit passende Musiker eingeplant werden können.'),
    performances: t('Auftritte planen und Besetzung, Programm sowie Abrechnung direkt öffnen.'),
    positions: t(
      'Für jeden Auftritt die benötigten Instrumente, Stimmen und Sollzahlen festlegen.',
    ),
    assignments: t('Einteilungen und Rückmeldungen für die Auftritte verwalten.'),
  }
  const selected = params.get('id')
  const rows =
    d[
      kind as keyof Pick<
        typeof d,
        'musicians' | 'skills' | 'performances' | 'positions' | 'assignments'
      >
    ]
  const row = rows.find((r) => String(r.id) === selected)
  const visibleRows = rows.filter(
    (r) =>
      (kind !== 'musicians' ||
        !params.get('mitglied') ||
        String(r.membership) === params.get('mitglied')) &&
      [
        r.title,
        r.display_name,
        r.name,
        r.contact,
        r.instrument,
        r.register,
        r.notes,
        r.location,
        r.uniform,
        r.musician ? musicianName(r.musician) : '',
        d.performances.find((p) => p.id === r.performance)?.title,
        d.positions.find((p) => p.id === r.position)?.instrument,
      ]
        .join(' ')
        .toLocaleLowerCase()
        .includes(search.trim().toLocaleLowerCase()),
  )
  const canEdit = org.permissions.includes('music.edit')
  const choose = async (art: string, id?: string) => {
    if (await confirmLeave()) {
      const next = new URLSearchParams(params)
      next.set('art', art)
      if (id) next.set('id', id)
      else next.delete('id')
      setParams(next)
      setFilter({ kind: '', value: '' })
    }
  }
  return (
    <section className="stack music-page">
      <MusicHeader title={names[kind]} description={descriptions[kind]} />
      <nav className="tabs" aria-label={t('Ansichten')}>
        {Object.entries(names)
          .filter(([key]) => musicianArea === ['musicians', 'skills'].includes(key))
          .map(([key, label]) => (
            <button
              key={key}
              className={`tab${kind === key ? ' active' : ''}`}
              aria-current={kind === key ? 'page' : undefined}
              onClick={() => choose(key)}
            >
              {label}
            </button>
          ))}
      </nav>
      {error && <Alert kind="error">{error}</Alert>}
      <div className="music-toolbar">
        <label>
          {t('Einträge suchen')}
          <input
            type="search"
            value={search}
            onChange={(e) => setFilter({ kind, value: e.target.value })}
          />
        </label>
        {canEdit && !selected && (
          <button className="button button-primary" onClick={() => choose(kind, 'neu')}>
            {t('Anlegen')}
          </button>
        )}
      </div>
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
        {!visibleRows.length && (
          <MusicEmptyState>
            {search.trim()
              ? t('Keine passenden Einträge gefunden.')
              : t('Noch keine Einträge vorhanden.')}
          </MusicEmptyState>
        )}
        {visibleRows.map((r) => (
          <article className="card stack music-record" key={r.id}>
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
                  {r.starts_at ? formatDateTime(String(r.starts_at)) : ''} –{' '}
                  {r.ends_at ? formatDateTime(String(r.ends_at)) : ''} · {r.location}
                </p>
                <dl className="music-details">
                  {(r.meeting_at || r.meeting_place) && (
                    <div>
                      <dt>{t('Treffpunkt')}</dt>
                      <dd>
                        {[r.meeting_at ? formatDateTime(String(r.meeting_at)) : '', r.meeting_place]
                          .filter(Boolean)
                          .join(' · ')}
                      </dd>
                    </div>
                  )}
                  {!!r.uniform && (
                    <div>
                      <dt>{t('Uniform')}</dt>
                      <dd>{r.uniform}</dd>
                    </div>
                  )}
                  <div>
                    <dt>{t('Spielform')}</dt>
                    <dd>{formations.find((f) => f[0] === r.formation)?.[1] || '—'}</dd>
                  </div>
                  <div>
                    <dt>{t('Besetzungsgröße')}</dt>
                    <dd>
                      {d.positions
                        .filter((p) => p.performance === r.id)
                        .reduce((n, p) => n + Number(p.required), 0)}
                    </dd>
                  </div>
                </dl>
                {!!r.cancelled && (
                  <span className="music-status music-status-declined">{t('Abgesagt')}</span>
                )}
                {!!r.notes && <p>{r.notes}</p>}
                <div className="music-record-links">
                  <Link to={`/aufgaben?termin=${r.event}`}>{t('Aufgaben zum Auftritt')}</Link>
                  <Link to={`/musik?programm=${r.id}`}>{t('Musikalisches Programm')}</Link>
                  <Link to={`/musik?besetzung=${r.id}`}>{t('Besetzung planen')}</Link>
                  {org.modules.includes('finance') && org.permissions.includes('finance.view') && (
                    <Link to={`/musik?abrechnung=${r.id}`}>{t('Auftrittsabrechnung')}</Link>
                  )}
                  <Link to={`/termine?termin=${r.event}`}>{t('Zum Termin')}</Link>
                </div>
              </>
            )}
            {kind === 'positions' && (
              <p>
                {r.register} · {t('Sollbesetzung')}: {r.required} · {t('Zugesagt')}:{' '}
                {d.assignments.filter((a) => a.position === r.id && a.status === 'accepted').length}{' '}
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
              <div className="music-record-actions">
                <button className="button button-ghost" onClick={() => choose(kind, String(r.id))}>
                  {t('Bearbeiten')}
                </button>
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
              </div>
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
              ? (f.initial ?? 1)
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
      <div className="music-form-fields">
        {fields.map((f) => (
          <label key={f.key} className={f.type === 'textarea' ? 'music-field-wide' : undefined}>
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
                min={f.type === 'number' ? (f.min ?? 1) : undefined}
                max={f.type === 'number' ? (f.max ?? 500) : undefined}
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
      </div>
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
