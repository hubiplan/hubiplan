import { useState } from 'react'
import { Link, useLocation, useSearchParams } from 'react-router-dom'
import { api } from '../../api/client.ts'
import { errorMessage, formatDateTime, useLoad } from '../../components/forms.ts'
import { confirmLeave } from '../../components/leaveGuard.ts'
import { Alert, EmptyState, Loading } from '../../components/ui.tsx'
import { useActiveOrg } from '../../org/OrgContext.tsx'
import { t, tn } from '../../i18n/index.ts'
import { confirmDialog } from '../../components/dialog.ts'
import { SettlementPanel } from './SettlementPanel.tsx'
import { EditAt, EditSlot, editKey } from '../../components/EditInPlace.tsx'
import { PageHeader } from '../../components/PageHeader.tsx'
import { MusicHeader, MusicEmptyState } from './MusicLayout.tsx'
import type { PerformanceKind, Uniform } from './UniformsKindsPage.tsx'
import { loadInstruments } from './InstrumentSelect.tsx'
import { RowEditor } from './RowEditor.tsx'
import { musicArea, type Field, type Row } from './musicHelpers.ts'

type Choices = { events: Row[]; partners: Row[] }
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

export function MusicWorkspace() {
  const org = useActiveOrg()
  const [params, setParams] = useSearchParams()
  const { pathname } = useLocation()
  const [error, setError] = useState('')
  const [filter, setFilter] = useState({ kind: '', value: '' })
  const [kindFilter, setKindFilter] = useState('')
  // „Wer spielt was“: Musiker und Fähigkeiten nach Instrument filtern
  const [instrumentFilter, setInstrumentFilter] = useState('')
  // Vergangene Auftritte sind zunächst ausgeblendet und lassen sich einblenden
  const [showPast, setShowPast] = useState(false)
  const [notice, setNotice] = useState('')
  const base = `/api/orgs/${org.id}/music/`
  const load = useLoad(async () => {
    const [
      musicians,
      skills,
      performances,
      positions,
      assignments,
      choices,
      uniforms,
      kinds,
      instruments,
    ] = await Promise.all([
      api.get<Row[]>(`${base}musicians/`),
      api.get<Row[]>(`${base}skills/`),
      api.get<Row[]>(`${base}performances/`),
      api.get<Row[]>(`${base}positions/`),
      api.get<Row[]>(`${base}assignments/`),
      api.get<Choices>(`${base}musicians/choices/`),
      // Auswahllisten (Issues #712/#713): fehlen sie, bleibt die Seite benutzbar
      api.get<Uniform[]>(`${base}uniforms/`).catch(() => [] as Uniform[]),
      api.get<PerformanceKind[]>(`${base}performance-kinds/`).catch(() => [] as PerformanceKind[]),
      loadInstruments(org.id),
    ])
    return {
      musicians,
      skills,
      performances,
      positions,
      assignments,
      choices,
      uniforms,
      kinds,
      instruments,
    }
  }, [org.id])
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
  const d = load.data
  const opened = d.performances.find((p) => String(p.id) === params.get('abrechnung'))
  // Issue #711: Abrechnung eines weiteren Tages ist die des Hauptauftritts
  const settlement = opened?.main ? d.performances.find((p) => p.id === opened.main) : opened
  const group = settlement
    ? [settlement.id, ...((settlement.days as unknown as number[] | undefined) || [])]
    : []
  if (settlement && org.modules.includes('finance') && org.permissions.includes('finance.view'))
    return (
      <SettlementPanel
        performance={settlement.id}
        title={String(settlement.title)}
        customer={Number(settlement.customer) || null}
        assignments={d.assignments
          .filter((a) => group.includes(Number(a.performance)))
          .map((a) => ({
            id: a.id,
            name:
              String(d.musicians.find((m) => m.id === a.musician)?.display_name || a.musician) +
              (group.length > 1
                ? ` · ${d.performances.find((p) => p.id === a.performance)?.title || ''}`
                : ''),
          }))}
      />
    )
  const opts = (rows: Row[], name: string): [string, string][] =>
    rows.map((r) => [String(r.id), String(r[name] || r.id)])
  const pick = <T extends { id: number; active: boolean; name: string }>(
    rows: T[],
    current: unknown,
  ): [string, string][] =>
    rows.filter((r) => r.active || r.id === current).map((r) => [String(r.id), r.name])
  const editing = d.performances.find((p) => String(p.id) === params.get('id'))
  const kindById = (id: unknown) => d.kinds.find((k) => k.id === Number(id))
  const titleWithDate = (p: Row) =>
    `${p.title}${p.starts_at ? ` (${formatDateTime(String(p.starts_at))})` : ''}`
  const musicianName = (id: unknown) =>
    String(d.musicians.find((m) => m.id === id)?.display_name || id)
  const fields: Record<string, Field[]> = {
    musicians: [
      ...(org.permissions.includes('members.view')
        ? [{ key: 'membership', label: t('Mitglied'), member: true, optional: true }]
        : []),
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
      { key: 'instrument', label: t('Instrument'), type: 'instrument' },
      { key: 'register', label: t('Register / Stimme'), optional: true },
      { key: 'primary', label: t('Hauptinstrument'), type: 'checkbox' },
    ],
    performances: [
      { key: 'event', label: t('Termin'), options: opts(d.choices.events, 'title') },
      {
        key: 'kind',
        label: t('Auftrittsart'),
        options: pick(d.kinds, editing?.kind),
        optional: true,
        suggest: (value) => {
          const kind = kindById(value)
          return {
            ...(kind?.formation ? { formation: kind.formation } : {}),
            ...(kind?.uniform ? { uniform_choice: String(kind.uniform) } : {}),
          }
        },
      },
      {
        key: 'main',
        label: t('Weiterer Tag von (Vertrag und Gage dort)'),
        options: d.performances
          .filter(
            (p) =>
              !p.main &&
              p.id !== editing?.id &&
              !(editing?.days as unknown as number[] | undefined)?.length,
          )
          .map((p) => [String(p.id), titleWithDate(p)]),
        optional: true,
      },
      {
        key: 'customer',
        label: t('Auftraggeber'),
        options: opts(d.choices.partners, 'name'),
        optional: true,
        lockedBy: (values) =>
          values.main ? t('Kommt vom Hauptauftritt und gilt für alle Tage.') : null,
      },
      { key: 'meeting_at', label: t('Treffzeit'), type: 'datetime-local', optional: true },
      { key: 'meeting_place', label: t('Treffpunkt'), optional: true },
      { key: 'setup_at', label: t('Aufbau'), type: 'datetime-local', optional: true },
      {
        key: 'uniform_choice',
        label: t('Uniform'),
        options: pick(d.uniforms, editing?.uniform_choice),
        optional: true,
      },
      { key: 'uniform', label: t('Ergänzung zur Uniform'), optional: true },
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
      { key: 'instrument', label: t('Instrument'), type: 'instrument' },
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
  // W-11/X-01: Suche, Anlegen und Leerzustand mit dem Wort der Ansicht statt „Einträge“
  const wording: Record<string, { search: string; add: string; empty: string; next: string }> = {
    musicians: {
      search: t('Musiker durchsuchen'),
      add: t('Neuer Musiker'),
      empty: t('Noch keine Musiker.'),
      next: t('Lege Mitglieder oder Gastmusiker an, um sie für Auftritte einzuplanen.'),
    },
    skills: {
      search: t('Fähigkeiten durchsuchen'),
      add: t('Neue Fähigkeit'),
      empty: t('Noch keine Fähigkeiten.'),
      next: t(
        'Hinterlege Instrumente und Stimmen der Musiker, damit passende Musiker eingeplant werden können.',
      ),
    },
    performances: {
      search: t('Auftritte durchsuchen'),
      add: t('Neuer Auftritt'),
      empty: t('Noch keine Auftritte.'),
      next: t('Lege einen Auftritt zu einem Termin an, um Besetzung und Programm zu planen.'),
    },
    positions: {
      search: t('Sollbesetzung durchsuchen'),
      add: t('Neue Position'),
      empty: t('Noch keine Sollbesetzung.'),
      next: t('Lege für einen Auftritt fest, welche Instrumente und Stimmen gebraucht werden.'),
    },
    assignments: {
      search: t('Einteilungen durchsuchen'),
      add: t('Neue Einteilung'),
      empty: t('Noch keine Einteilungen.'),
      next: t('Teile Musiker für einen Auftritt ein und sammle ihre Rückmeldungen.'),
    },
  }
  const words = wording[kind]
  const selected = params.get('id')
  const rows =
    d[
      kind as keyof Pick<
        typeof d,
        'musicians' | 'skills' | 'performances' | 'positions' | 'assignments'
      >
    ]
  const row = rows.find((r) => String(r.id) === selected)
  // Instrument → Musiker, die es spielen (aus den Fähigkeiten)
  const playersOf = new Map<string, Set<number>>()
  for (const s of d.skills) {
    const name = String(s.instrument)
    if (!playersOf.has(name)) playersOf.set(name, new Set())
    playersOf.get(name)!.add(Number(s.musician))
  }
  const listed = [...playersOf.keys()].sort((a, b) => {
    const pos = (n: string) => d.instruments.find((i) => i.name === n)?.position ?? 99999
    return pos(a) - pos(b) || a.localeCompare(b)
  })
  const instrumentsOf = (musician: unknown) =>
    d.skills
      .filter((s) => s.musician === musician)
      .sort((a, b) => Number(b.primary) - Number(a.primary))
      .map((s) => String(s.instrument))
  const now = Date.now()
  const pastIds = new Set(
    d.performances
      .filter((p) => {
        const end = p.ends_at || p.starts_at
        return !!end && new Date(String(end)).getTime() < now
      })
      .map((p) => p.id),
  )
  const performanceOf = (r: Row) => Number(kind === 'performances' ? r.id : r.performance)
  const withPast = ['performances', 'positions', 'assignments'].includes(kind)
  const hiddenPast = withPast && !showPast ? rows.filter((r) => pastIds.has(performanceOf(r))) : []
  const visibleRows = rows.filter(
    (r) =>
      !hiddenPast.includes(r) &&
      (kind !== 'performances' || !kindFilter || String(r.kind) === kindFilter) &&
      (!musicianArea ||
        !instrumentFilter ||
        (kind === 'skills'
          ? r.instrument === instrumentFilter
          : (playersOf.get(instrumentFilter) ?? new Set()).has(Number(r.id)))) &&
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
        r.uniform_text,
        r.kind_name,
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
      {notice && <Alert kind="success">{notice}</Alert>}
      <div className="music-toolbar">
        <label>
          {words.search}
          <input
            type="search"
            value={search}
            onChange={(e) => setFilter({ kind, value: e.target.value })}
          />
        </label>
        {musicianArea && listed.length > 0 && (
          <label>
            {t('Instrument')}
            <select value={instrumentFilter} onChange={(e) => setInstrumentFilter(e.target.value)}>
              <option value="">{t('Alle')}</option>
              {listed.map((name) => (
                <option key={name} value={name}>
                  {`${name} (${playersOf.get(name)!.size})`}
                </option>
              ))}
            </select>
          </label>
        )}
        {kind === 'performances' && d.kinds.length > 0 && (
          <label>
            {t('Auftrittsart')}
            <select value={kindFilter} onChange={(e) => setKindFilter(e.target.value)}>
              <option value="">{t('Alle')}</option>
              {d.kinds.map((k) => (
                <option key={k.id} value={k.id}>
                  {k.name}
                </option>
              ))}
            </select>
          </label>
        )}
        {withPast && pastIds.size > 0 && (
          <label className="checkbox">
            <input
              type="checkbox"
              checked={showPast}
              onChange={(e) => setShowPast(e.target.checked)}
            />
            <span>
              {kind === 'performances'
                ? t('Vergangene Auftritte zeigen')
                : t('Vergangene Auftritte einbeziehen')}
              {!showPast &&
                hiddenPast.length > 0 &&
                ` (${tn('{n} ausgeblendet', '{n} ausgeblendet', hiddenPast.length)})`}
            </span>
          </label>
        )}
        {canEdit && !selected && (
          <button className="button button-primary" onClick={() => choose(kind, 'neu')}>
            {words.add}
          </button>
        )}
      </div>
      {kind === 'performances' && !selected && (
        <KindStatistics performances={d.performances} kinds={d.kinds} />
      )}
      {canEdit && selected && (
        <EditAt at={row ? editKey(kind, row.id) : null}>
          <RowEditor
            key={`${kind}-${selected}`}
            fields={fields[kind]}
            instruments={d.instruments}
            row={row}
            defaults={{
              membership: params.get('mitglied') || '',
              event: params.get('termin') || '',
            }}
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
            onAutoSave={
              row
                ? async (changes) => {
                    await api.patch(`${base}${kind}/${row.id}/`, changes)
                    void load.reload()
                  }
                : undefined
            }
          />
        </EditAt>
      )}
      <div className="stack">
        {!visibleRows.length &&
          (search.trim() ? (
            <MusicEmptyState>{t('Keine passenden Einträge gefunden.')}</MusicEmptyState>
          ) : (
            <EmptyState
              title={words.empty}
              action={
                canEdit && !selected ? (
                  <button className="button" onClick={() => choose(kind, 'neu')}>
                    {words.add}
                  </button>
                ) : undefined
              }
            >
              {words.next}
            </EmptyState>
          ))}
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
                {instrumentsOf(r.id).length > 0 && `${instrumentsOf(r.id).join(', ')} · `}
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
                  {!!r.kind_name && (
                    <div>
                      <dt>{t('Auftrittsart')}</dt>
                      <dd>{r.kind_name}</dd>
                    </div>
                  )}
                  {!!r.uniform_text && (
                    <div>
                      <dt>{t('Uniform')}</dt>
                      <dd>{r.uniform_text}</dd>
                    </div>
                  )}
                  {!!r.main && (
                    <div>
                      <dt>{t('Vertrag und Gage')}</dt>
                      <dd>
                        {t('über {title}', {
                          title: String(d.performances.find((p) => p.id === r.main)?.title || ''),
                        })}
                      </dd>
                    </div>
                  )}
                  {!!(r.days as unknown as number[])?.length && (
                    <div>
                      <dt>{t('Vertrag und Gage')}</dt>
                      <dd>
                        {t('für {n} Tage', {
                          n: String((r.days as unknown as number[]).length + 1),
                        })}
                      </dd>
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
                  <Link className="button button-ghost" to={`/aufgaben?termin=${r.event}`}>
                    {t('Aufgaben zum Auftritt')}
                  </Link>
                  <Link className="button button-ghost" to={`/musik?programm=${r.id}`}>
                    {t('Musikalisches Programm')}
                  </Link>
                  <Link className="button button-ghost" to={`/musik?besetzung=${r.id}`}>
                    {t('Besetzung planen')}
                  </Link>
                  {org.modules.includes('finance') && org.permissions.includes('finance.view') && (
                    <Link
                      className="button button-ghost"
                      to={`/musik?abrechnung=${r.main || r.id}`}
                    >
                      {r.main ? t('Abrechnung des Festes') : t('Auftrittsabrechnung')}
                    </Link>
                  )}
                  {canEdit && !r.main && !!r.project && (
                    <button
                      className="button button-ghost"
                      onClick={async () => {
                        setError('')
                        setNotice('')
                        try {
                          const result = await api.post<{
                            added: number[]
                            skipped: { title: string; reason: string }[]
                          }>(`${base}performances/${r.id}/combine/`)
                          setNotice(
                            [
                              tn(
                                '{n} weiterer Tag angehängt.',
                                '{n} weitere Tage angehängt.',
                                result.added.length,
                              ),
                              ...result.skipped.map((x) => `${x.title}: ${x.reason}`),
                            ].join(' '),
                          )
                          await load.reload()
                        } catch (err) {
                          setError(errorMessage(err))
                        }
                      }}
                    >
                      {t('Alle Tage der Veranstaltung zusammenfassen')}
                    </button>
                  )}
                  <Link className="button button-ghost" to={`/termine?termin=${r.event}`}>
                    {t('Zum Termin')}
                  </Link>
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
                      if (
                        !(await confirmDialog({
                          final: true,
                          message: t('Eintrag entfernen?'),
                          confirmLabel: t('Entfernen'),
                        }))
                      )
                        return
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
            <EditSlot id={editKey(kind, r.id)} />
          </article>
        ))}
      </div>
    </section>
  )
}

/** Auftritte je Jahr und Art (Issue #713); abgesagte zählen nicht mit. */
function KindStatistics({
  performances,
  kinds,
}: {
  performances: Row[]
  kinds: PerformanceKind[]
}) {
  const counts = new Map<string, Map<string, number>>()
  for (const p of performances) {
    if (p.cancelled || !p.starts_at) continue
    const year = String(p.starts_at).slice(0, 4)
    const name = p.kind ? kinds.find((k) => k.id === p.kind)?.name || '' : ''
    const label = name || t('Ohne Art')
    const row = counts.get(label) ?? new Map<string, number>()
    row.set(year, (row.get(year) ?? 0) + 1)
    counts.set(label, row)
  }
  if (!counts.size) return null
  const years = [...new Set([...counts.values()].flatMap((m) => [...m.keys()]))].sort()
  return (
    <details className="card music-statistics">
      <summary>{t('Auftritte je Jahr und Art')}</summary>
      <div className="table-scroll">
        <table className="table">
          <thead>
            <tr>
              <th scope="col">{t('Auftrittsart')}</th>
              {years.map((y) => (
                <th scope="col" key={y}>
                  {y}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {[...counts.entries()]
              .sort((a, b) => a[0].localeCompare(b[0]))
              .map(([label, row]) => (
                <tr key={label}>
                  <th scope="row">{label}</th>
                  {years.map((y) => (
                    <td key={y}>{row.get(y) ?? 0}</td>
                  ))}
                </tr>
              ))}
          </tbody>
        </table>
      </div>
    </details>
  )
}
