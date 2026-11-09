// Meldungen: Ausschreibungen erfassen, Mannschaften und Personen melden, Fassungen.
// Konzept: konzepte/meldungen.md, Doku docs/meldungen.md.
import { useCallback, useState } from 'react'
import type { FormEvent } from 'react'
import { Link, Route, Routes, useNavigate, useParams } from 'react-router-dom'
import {
  BLOCK_LABELS,
  CHANNEL_LABELS,
  STATUS_LABELS,
  entriesApi,
  type BlockKind,
  type BlockSettings,
  type Call,
  type CallBlock,
  type CallDetail,
  type Candidate,
  type Channel,
  type Conditions,
  type Entry,
  type EntryOptions,
  type EntryPerson,
  type EntryTeam,
  type Scope,
} from '../../api/entries.ts'
import type { PickedMember } from '../../api/members.ts'
import { DataTable } from '../../components/DataTable.tsx'
import { MemberPicker } from '../../components/MemberPicker.tsx'
import { confirmDialog, promptDialog } from '../../components/dialog.ts'
import { errorMessage, formatDate, useAutoSave, useForm, useLoad } from '../../components/forms.ts'
import { confirmDiscard, useChangesGuard } from '../../components/leaveGuard.ts'
import {
  Alert,
  Checkbox,
  Field,
  LoadError,
  SaveStatus,
  SelectField,
  Tabs,
  Loading,
} from '../../components/ui.tsx'
import { PERM } from '../../api/orgs.ts'
import { useActiveOrg } from '../../org/OrgContext.tsx'
import { CallEventCard, InterestCard } from './CallEvent.tsx'
import { UnitEntryPage, UnitsPanel } from './UnitEntries.tsx'
import { EntryResultsCard } from './EntryResults.tsx'
import { locale, t } from '../../i18n/index.ts'

export function EntriesPage() {
  return (
    <Routes>
      <Route index element={<CallList />} />
      <Route path=":id/*" element={<CallArea />} />
    </Routes>
  )
}

function statusText(c: Call): string {
  if (c.unit_counts)
    return t('{x1} von {x2} gemeldet', { x1: c.unit_counts.submitted, x2: c.unit_counts.addressed })
  if (!c.entry_status) return t('noch nicht gemeldet')
  const label = STATUS_LABELS[c.entry_status]
  return c.entry_changed && c.entry_status !== 'entwurf' ? `${label}, geändert` : label
}

function CallList() {
  const org = useActiveOrg()
  const navigate = useNavigate()
  const { data, error, reload } = useLoad(() => entriesApi.list(org.id), [org.id])
  const [creating, setCreating] = useState(false)
  return (
    <section>
      <h1>{t('Meldungen')}</h1>
      <p className="muted">
        {t(
          'Mannschaften, Personen und Angaben an einen Veranstalter melden, etwa zu einem Vergleichsschießen oder einem Verbandsfest. Die Meldung geht als Brief auf eurem Briefbogen, per E-Mail oder als Tabelle hinaus; Änderungen werden als neue Fassung festgehalten.',
        )}
      </p>
      {error && <LoadError message={error} onRetry={reload} />}
      {!creating && (
        <div className="button-row">
          <button type="button" className="button" onClick={() => setCreating(true)}>
            {t('Neue Ausschreibung erfassen')}
          </button>
        </div>
      )}
      {creating && (
        <NewCall
          org={org.id}
          onClose={() => setCreating(false)}
          onCreated={(id) => navigate(`/meldungen/${id}/ausschreibung`)}
        />
      )}
      {data && (
        <DataTable<Call>
          label={t('Ausschreibungen')}
          rows={data}
          rowKey={(c) => c.id}
          initialSort={{ key: 'deadline', dir: 'desc' }}
          emptyText={t('Noch keine Ausschreibungen.')}
          columns={[
            {
              key: 'deadline',
              label: t('Meldeschluss'),
              value: (c) => c.deadline ?? '',
              render: (c) => (c.deadline ? formatDate(c.deadline) : '—'),
            },
            {
              key: 'title',
              label: t('Ausschreibung'),
              value: (c) => c.title,
              render: (c) => <Link to={`/meldungen/${c.id}`}>{c.title}</Link>,
            },
            { key: 'organizer', label: t('Veranstalter'), value: (c) => c.organizer },
            {
              key: 'date',
              label: t('Datum'),
              value: (c) => c.date ?? '',
              render: (c) => (c.date ? formatDate(c.date) : '—'),
              optional: true,
            },
            { key: 'status', label: t('Meldung'), value: statusText, filter: true },
          ]}
        />
      )}
    </section>
  )
}

function NewCall({
  org,
  onClose,
  onCreated,
}: {
  org: number
  onClose: () => void
  onCreated: (id: number) => void
}) {
  const active = useActiveOrg()
  const canIssue = active.permissions.includes(PERM.entriesManage)
  const form = useForm({
    title: '',
    organizer: '',
    date: '',
    deadline: '',
    template: 'mannschaften',
    internal: false,
  })
  const { values: v, set, errors } = form
  const draft = useChangesGuard(v)

  async function save(e: FormEvent) {
    e.preventDefault()
    const created = await form.submit(() =>
      entriesApi.create(org, {
        title: v.title,
        organizer: v.internal ? '' : v.organizer,
        internal: v.internal,
        date: v.date || null,
        deadline: v.deadline || null,
        template: v.template,
      }),
    )
    if (created) {
      draft.markSaved()
      onCreated((created as CallDetail).id)
    }
  }

  return (
    <div className="card card-wide">
      <form onSubmit={save}>
        <div className="card-head">
          <h2>{t('Neue Ausschreibung')}</h2>
          <button
            type="button"
            className="button button-ghost push-right"
            disabled={form.busy}
            onClick={async () => {
              if (await confirmDiscard(draft.dirty)) onClose()
            }}
          >
            {t('Abbrechen')}
          </button>
        </div>
        {canIssue && (
          <Checkbox
            label={t('Wir schreiben selbst aus, unsere Untereinheiten melden')}
            hint={t('z. B. ein Preisschießen, zu dem die Züge ihre Schützen melden')}
            checked={v.internal}
            onChange={(on) => set('internal', on)}
          />
        )}
        <p className="muted">
          {v.internal
            ? t(
                'Die Untereinheiten finden die Ausschreibung in ihrem Bereich unter „Meldungen“ und melden dort; ihr bestätigt im Eingang.',
              )
            : t(
                'Übertragt hier die Ausschreibung, die ihr per Brief oder Mail bekommen habt. Bei jährlichen Anlässen könnt ihr später die Ausschreibung des Vorjahres kopieren.',
              )}
        </p>
        <div className="grid-3">
          <Field
            label={t('Titel')}
            required
            placeholder={t('z. B. Vergleichsschießen 2027')}
            value={v.title}
            error={errors.title}
            onChange={(e) => set('title', e.target.value)}
          />
          {!v.internal && (
            <Field
              label={t('Veranstalter')}
              required
              placeholder={t('z. B. Bürger-Schützenverein')}
              value={v.organizer}
              error={errors.organizer}
              onChange={(e) => set('organizer', e.target.value)}
            />
          )}
          <SelectField
            label={t('Vorlage')}
            value={v.template}
            onChange={(e) => set('template', e.target.value)}
          >
            <option value="mannschaften">{t('Mannschaften melden')}</option>
            <option value="">{t('leer (Bausteine selbst anlegen)')}</option>
          </SelectField>
          <Field
            label={t('Datum des Anlasses')}
            type="date"
            value={v.date}
            error={errors.date}
            onChange={(e) => set('date', e.target.value)}
          />
          <Field
            label={t('Meldeschluss')}
            type="date"
            value={v.deadline}
            error={errors.deadline}
            onChange={(e) => set('deadline', e.target.value)}
          />
        </div>
        {form.message && <Alert kind={form.message.kind}>{form.message.text}</Alert>}
        <div className="button-row">
          <button type="submit" className="button" disabled={form.busy}>
            {t('Anlegen')}
          </button>
        </div>
      </form>
    </div>
  )
}

function CallArea() {
  const org = useActiveOrg()
  const id = Number(useParams().id)
  const call = useLoad(() => entriesApi.get(org.id, id), [org.id, id])
  const entry = useLoad(() => entriesApi.entry(org.id, id), [org.id, id])
  const options = useLoad(() => entriesApi.options(org.id), [org.id])
  const error = call.error || entry.error || options.error
  if (error)
    return (
      <LoadError
        message={error}
        onRetry={() => {
          void call.reload()
          void entry.reload()
          void options.reload()
        }}
      />
    )
  if (!call.data || !options.data || (entry.loading && entry.data === null)) return <Loading />
  const c = call.data
  const base = `/meldungen/${id}`
  return (
    <section>
      <p>
        <Link to="/meldungen">{t('← Alle Meldungen')}</Link>
      </p>
      <h1>{c.title}</h1>
      <p className="muted">
        {t('Veranstalter: ')}
        {c.organizer}
        {c.date ? ` · ${formatDate(c.date)}` : ''}
        {c.location ? ` · ${c.location}` : ''}
        {c.deadline ? t(' · Meldeschluss {x1}', { x1: formatDate(c.deadline) }) : ''}
      </p>
      {c.internal ? (
        <Tabs
          items={[
            { to: base, label: t('Eingang') },
            { to: `${base}/ausschreibung`, label: t('Ausschreibung') },
          ]}
        />
      ) : (
        <Tabs
          items={[
            { to: base, label: t('Meldung') },
            { to: `${base}/ausschreibung`, label: t('Ausschreibung') },
            { to: `${base}/fassungen`, label: t('Fassungen') },
          ]}
        />
      )}
      {c.internal && (
        <Routes>
          <Route index element={<UnitsPanel org={org.id} call={c} />} />
          <Route
            path="einheit/:unit"
            element={<UnitEntryPage org={org.id} call={c} options={options.data} />}
          />
        </Routes>
      )}
      <Routes>
        <Route
          index
          element={
            c.internal ? null : (
              <EntryPanel
                org={org.id}
                call={c}
                entry={entry.data ?? null}
                options={options.data}
                setEntry={(e) => {
                  entry.setData(e)
                  void call.reload()
                }}
              />
            )
          }
        />
        <Route
          path="ausschreibung"
          element={
            <CallEditor
              org={org.id}
              call={c}
              options={options.data}
              onChanged={(d) => call.setData(d)}
              reload={() => {
                void call.reload()
                void entry.reload()
              }}
            />
          }
        />
        <Route
          path="fassungen"
          element={<VersionsPanel org={org.id} call={c} entry={entry.data ?? null} />}
        />
      </Routes>
    </section>
  )
}

// --- Meldung zusammenstellen ---

export function EntryPanel({
  org,
  call,
  entry,
  options,
  setEntry,
  organizer = false,
}: {
  org: Scope
  call: CallDetail
  entry: Entry | null
  options: EntryOptions
  setEntry: (e: Entry | null) => void
  /** Veranstalter bearbeitet die Meldung einer Untereinheit (bestätigen, zurückgeben) */
  organizer?: boolean
}) {
  const [message, setMessage] = useState<string | null>(null)
  const run = useCallback(
    async (action: () => Promise<Entry | unknown>) => {
      setMessage(null)
      try {
        const result = await action()
        if (result && typeof result === 'object' && 'status' in result) setEntry(result as Entry)
        return true
      } catch (err) {
        setMessage(errorMessage(err))
        return false
      }
    },
    [setEntry],
  )

  if (!entry) {
    return (
      <div className="card card-wide">
        <p>{t('Zu dieser Ausschreibung gibt es noch keine Meldung.')}</p>
        {call.blocks.length === 0 && (
          <Alert kind="info">
            {t(
              'Die Ausschreibung hat noch keine Bausteine. Legt unter „Ausschreibung“ fest, was gemeldet wird, z. B. Mannschaften.',
            )}
          </Alert>
        )}
        {message && <Alert kind="error">{message}</Alert>}
        <div className="button-row">
          <button
            type="button"
            className="button"
            onClick={() => void run(() => entriesApi.createEntry(org, call.id))}
          >
            {t('Meldung zusammenstellen')}
          </button>
        </div>
      </div>
    )
  }

  const withdrawn = entry.status === 'zurueckgezogen'
  const locked = withdrawn
  return (
    <>
      <div className="card card-wide">
        <div className="card-head">
          <h2>
            {t('Meldung: ')}
            {STATUS_LABELS[entry.status]}
            {entry.changed && entry.status !== 'entwurf'
              ? t(' (geändert, noch nicht gemeldet)')
              : ''}
          </h2>
        </div>
        {entry.confirmed_note && (
          <p className="muted">
            {t('Bestätigung: ')}
            {entry.confirmed_note}
          </p>
        )}
        {entry.question && (
          <Alert kind="info">
            {t('Rückfrage ')}
            {call.internal ? t('von {x1}', { x1: call.organizer }) : ''}: {entry.question}
            {!organizer && t(' Bitte prüfen und die Meldung erneut abgeben.')}
          </Alert>
        )}
        {entry.after_deadline && !withdrawn && (
          <Alert kind="info">
            {t('Der Meldeschluss ist vorbei.')}{' '}
            {call.changes_after_deadline === 'frei'
              ? t('Änderungen sind bis zum Anlass möglich.')
              : call.changes_after_deadline === 'ersatz'
                ? t('Möglich ist nur noch der Ersatz von Personen.')
                : t('Änderungen sind nicht mehr vorgesehen.')}
          </Alert>
        )}
        {entry.hints.length > 0 && (
          <div className="alert alert-info" role="status">
            <strong>{t('Bitte prüfen')}</strong>
            {call.strict ? t(' (so lässt sich nicht abgeben):') : t(' (Abgeben bleibt möglich):')}
            <ul>
              {entry.hints.map((h, i) => (
                <li key={i}>{h.text}</li>
              ))}
            </ul>
          </div>
        )}
        {entry.competition && !call.internal && (
          <p>
            {t('Zur Meldung gehört der Wettbewerb')}{' '}
            <Link to={`/wettbewerbe/${entry.competition}`}>{call.title}</Link>
            {t('; dort tragt ihr später eure Plätze ein.')}
          </p>
        )}
        {message && <Alert kind="error">{message}</Alert>}
      </div>
      {/* Ausschreibung an Untereinheiten: Ergebnisse kommen nach Abschluss hierher zurück */}
      {entry.competition && call.internal && <EntryResultsCard org={org} call={call.id} />}
      <InterestCard org={org} call={call} entry={entry} locked={locked} run={run} />
      {call.blocks.map((b) => (
        <BlockEntry
          key={b.id}
          org={org}
          call={call}
          block={b}
          entry={entry}
          locked={locked}
          run={run}
        />
      ))}
      {!locked && <NoteCard org={org} call={call} entry={entry} setEntry={setEntry} />}
      {!locked && (
        <SubmitCard
          org={org}
          call={call}
          entry={entry}
          options={options}
          run={run}
          onDiscarded={() => setEntry(null)}
        />
      )}
      {withdrawn && (
        <WithdrawnCard
          org={org}
          call={call}
          entry={entry}
          run={run}
          onDeleted={() => setEntry(null)}
        />
      )}
      {organizer && <OrganizerCard org={org} call={call} entry={entry} run={run} />}
    </>
  )
}

/** Zurückgezogene Meldung: wieder öffnen oder ganz löschen (die Ausschreibung bleibt). */
function WithdrawnCard({
  org,
  call,
  entry,
  run,
  onDeleted,
}: {
  org: Scope
  call: CallDetail
  entry: Entry
  run: Run
  onDeleted: () => void
}) {
  async function remove() {
    const ok = await confirmDialog({
      title: t('Meldung löschen'),
      message: t(
        'Die Meldung mit allen Mannschaften, Personen und {x1} Fassungen löschen? Die Ausschreibung bleibt erhalten.',
        { x1: entry.versions.length },
      ),
      confirmLabel: t('Löschen'),
      danger: true,
    })
    if (ok && (await run(() => entriesApi.discard(org, call.id)))) onDeleted()
  }
  return (
    <div className="card card-wide">
      <div className="card-head">
        <h2>{t('Zurückgezogen')}</h2>
      </div>
      <p className="muted">
        {t(
          'Öffnet ihr die Meldung wieder, wird sie zum Entwurf mit den bisherigen Angaben; die Fassungen bleiben erhalten. Beim Löschen verschwindet die Meldung mit allen Fassungen, und ihr könnt neu anfangen.',
        )}
      </p>
      <div className="button-row">
        <button
          type="button"
          className="button"
          onClick={() => void run(() => entriesApi.reopen(org, call.id))}
        >
          {t('Wieder öffnen')}
        </button>
        <button type="button" className="button button-ghost" onClick={remove}>
          {t('Meldung löschen')}
        </button>
      </div>
    </div>
  )
}

type Run = (action: () => Promise<Entry | unknown>) => Promise<boolean>

function BlockEntry({
  org,
  call,
  block,
  entry,
  locked,
  run,
}: {
  org: Scope
  call: CallDetail
  block: CallBlock
  entry: Entry
  locked: boolean
  run: Run
}) {
  const s = block.settings
  if (block.kind === 'mannschaften') {
    const teams = entry.teams.filter((t) => t.block === block.id)
    return (
      <div className="card card-wide">
        <div className="card-head">
          <h2>{block.label}</h2>
        </div>
        {block.help_text && <p className="muted">{block.help_text}</p>}
        <p className="muted small">
          {rangeText(s.min_teams, s.max_teams, t('Mannschaft'), t('Mannschaften'))}
          {s.min_size || s.max_size
            ? t(' · je {x1}', { x1: rangeText(s.min_size, s.max_size, t('Person'), t('Personen')) })
            : ''}
          {s.substitutes ? t(' · bis {x1} Ersatz', { x1: s.substitutes }) : ''}
        </p>
        {teams.map((t) => (
          <TeamCard
            key={t.id}
            org={org}
            call={call}
            block={block}
            team={t}
            entry={entry}
            locked={locked}
            run={run}
          />
        ))}
        {!locked && (
          <div className="button-row">
            <button
              type="button"
              className="button button-ghost"
              onClick={() => void run(() => entriesApi.addTeam(org, call.id, block.id))}
            >
              {t('Mannschaft hinzufügen')}
            </button>
          </div>
        )}
      </div>
    )
  }
  if (block.kind === 'personen') {
    const persons = entry.persons.filter((p) => p.block === block.id)
    return (
      <div className="card card-wide">
        <div className="card-head">
          <h2>{block.label}</h2>
        </div>
        {block.help_text && <p className="muted">{block.help_text}</p>}
        <PersonList
          org={org}
          call={call}
          block={block}
          persons={persons}
          entry={entry}
          locked={locked}
          run={run}
        />
        {!locked && (
          <PersonAdder org={org} call={call} block={block} team={null} entry={entry} run={run} />
        )}
      </div>
    )
  }
  return (
    <div className="card card-wide">
      <AnswerField
        key={`${block.id}-${JSON.stringify(entry.answers[String(block.id)] ?? null)}`}
        org={org}
        call={call}
        block={block}
        value={entry.answers[String(block.id)]}
        locked={locked}
        run={run}
      />
    </div>
  )
}

function rangeText(min: number | undefined, max: number | undefined, one: string, many: string) {
  const word = (n: number) => (n === 1 ? one : many)
  if (min && max != null && min === max) return t('genau {x1} {x2}', { x1: min, x2: word(min) })
  if (min && max != null) return t('{x1} bis {x2} {x3}', { x1: min, x2: max, x3: many })
  if (min) return t('mindestens {x1} {x2}', { x1: min, x2: word(min) })
  if (max != null) return t('höchstens {x1} {x2}', { x1: max, x2: word(max) })
  return t('beliebig viele {x1}', { x1: many })
}

function TeamCard({
  org,
  call,
  block,
  team,
  entry,
  locked,
  run,
}: {
  org: Scope
  call: CallDetail
  block: CallBlock
  team: EntryTeam
  entry: Entry
  locked: boolean
  run: Run
}) {
  const [name, setName] = useState(team.name)
  const persons = entry.persons.filter((p) => p.team === team.id)

  async function remove() {
    const ok = await confirmDialog({
      title: t('Mannschaft entfernen'),
      message: t('„{x1}“ mit {x2} Personen aus der Meldung nehmen?', {
        x1: team.name,
        x2: persons.length,
      }),
      confirmLabel: t('Entfernen'),
      danger: true,
    })
    if (ok) await run(() => entriesApi.removeTeam(org, call.id, team.id))
  }

  return (
    <div className="card">
      <div className="card-head">
        {locked ? (
          <h3>{team.name}</h3>
        ) : (
          <Field
            label={t('Name der Mannschaft')}
            value={name}
            onChange={(e) => setName(e.target.value)}
            onBlur={() => {
              if (name.trim() && name !== team.name)
                void run(() => entriesApi.updateTeam(org, call.id, team.id, { name }))
            }}
          />
        )}
        {!locked && (
          <button type="button" className="button button-ghost push-right" onClick={remove}>
            {t('Mannschaft entfernen')}
          </button>
        )}
      </div>
      <PersonList
        org={org}
        call={call}
        block={block}
        persons={persons}
        entry={entry}
        locked={locked}
        run={run}
      />
      {!locked && (
        <PersonAdder org={org} call={call} block={block} team={team} entry={entry} run={run} />
      )}
    </div>
  )
}

function PersonList({
  org,
  call,
  block,
  persons,
  entry,
  locked,
  run,
}: {
  org: Scope
  call: CallDetail
  block: CallBlock
  persons: EntryPerson[]
  entry: Entry
  locked: boolean
  run: Run
}) {
  const [replacing, setReplacing] = useState<number | null>(null)
  const positions = block.settings.positions ?? []
  if (persons.length === 0) return <p className="muted">{t('Noch niemand gemeldet.')}</p>
  const hintsFor = (p: EntryPerson) => entry.hints.filter((h) => h.person === p.id)
  return (
    <table className="table">
      <thead>
        <tr>
          <th scope="col">{t('Nr.')}</th>
          <th scope="col">{t('Name')}</th>
          {positions.length > 0 && <th scope="col">{t('Aufgabe')}</th>}
          {block.kind === 'mannschaften' && <th scope="col">{t('Ersatz')}</th>}
          {!locked && <th scope="col">{t('Aktionen')}</th>}
        </tr>
      </thead>
      <tbody>
        {persons.map((p, i) => (
          <tr key={p.id}>
            <td>{i + 1}</td>
            <td>
              {p.name}
              {p.club && <span className="muted"> ({p.club})</span>}
              {p.guest && <span className="muted small">{t(' · Gast')}</span>}
              {hintsFor(p).map((h, j) => (
                <div key={j} className="muted small">
                  ⚠ {h.text}
                </div>
              ))}
              {replacing === p.id && (
                <MemberChooser
                  org={org}
                  call={call}
                  label={t('Ersatz: neues Mitglied auf diesem Platz')}
                  onPick={async (m) => {
                    const ok = await run(() =>
                      entriesApi.updatePerson(org, call.id, p.id, { membership: m }),
                    )
                    if (ok) setReplacing(null)
                  }}
                />
              )}
            </td>
            {positions.length > 0 && (
              <td>
                <select
                  aria-label={t('Aufgabe von {name}', { name: p.name })}
                  value={p.position}
                  disabled={locked}
                  onChange={(e) =>
                    void run(() =>
                      entriesApi.updatePerson(org, call.id, p.id, { position: e.target.value }),
                    )
                  }
                >
                  <option value="">—</option>
                  {positions.map((pos) => (
                    <option key={pos} value={pos}>
                      {pos}
                    </option>
                  ))}
                </select>
              </td>
            )}
            {block.kind === 'mannschaften' && (
              <td>
                <input
                  type="checkbox"
                  aria-label={t('{name} als Ersatz', { name: p.name })}
                  checked={p.substitute}
                  disabled={locked}
                  onChange={(e) =>
                    void run(() =>
                      entriesApi.updatePerson(org, call.id, p.id, {
                        substitute: e.target.checked,
                      }),
                    )
                  }
                />
              </td>
            )}
            {!locked && (
              <td>
                {entry.can_pick_members && (
                  <button
                    type="button"
                    className="link-button"
                    onClick={() => setReplacing(replacing === p.id ? null : p.id)}
                  >
                    {replacing === p.id ? t('kein Ersatz') : t('ersetzen')}
                  </button>
                )}{' '}
                <button
                  type="button"
                  className="link-button"
                  onClick={() => void run(() => entriesApi.removePerson(org, call.id, p.id))}
                >
                  {t('streichen')}
                </button>
              </td>
            )}
          </tr>
        ))}
      </tbody>
    </table>
  )
}

type PickedCandidate = PickedMember & { candidate: Candidate }

/** Mitglied aus der kompletten Mitgliederliste wählen (Ralf 2026-11-01), auf Wunsch auch
 *  Ausgetretene. */
function MemberChooser({
  org,
  call,
  label,
  onPick,
}: {
  org: Scope
  call: CallDetail
  label: string
  onPick: (membership: number) => void
}) {
  const [all, setAll] = useState(false)
  const search = useCallback(
    (term: string) =>
      entriesApi.candidates(org, call.id, term, all).then((rows) =>
        rows.map((r): PickedCandidate => ({
          id: r.membership,
          first_name: r.first_name,
          last_name: r.last_name,
          email: [
            r.unit_name,
            r.birth_year ? t('geb. {year}', { year: r.birth_year }) : '',
            r.active ? '' : t('nicht aktiv'),
            r.taken ? t('schon gemeldet') : '',
            r.response === 'yes' ? t('hat zugesagt') : r.response === 'no' ? t('hat abgesagt') : '',
          ]
            .filter(Boolean)
            .join(' · '),
          candidate: r,
        })),
      ),
    [org, call.id, all],
  )
  return (
    <div>
      <MemberPicker<PickedCandidate>
        orgId={typeof org === 'number' ? org : 0}
        label={label}
        value={null}
        search={search}
        onChange={(m) => m && onPick(m.id)}
      />
      <Checkbox label={t('auch ausgetretene Mitglieder')} checked={all} onChange={setAll} />
    </div>
  )
}

function PersonAdder({
  org,
  call,
  block,
  team,
  entry,
  run,
}: {
  org: Scope
  call: CallDetail
  block: CallBlock
  team: EntryTeam | null
  entry: Entry
  run: Run
}) {
  const [guest, setGuest] = useState(false)
  const [name, setName] = useState('')
  const [club, setClub] = useState('')
  const target = { block: block.id, team: team?.id ?? null }
  return (
    <div className="grid-3">
      {entry.can_pick_members && !guest && (
        <MemberChooser
          org={org}
          call={call}
          label={t('Mitglied hinzufügen')}
          onPick={(m) =>
            void run(() => entriesApi.addPerson(org, call.id, { ...target, membership: m }))
          }
        />
      )}
      {(guest || !entry.can_pick_members) && (
        <>
          <Field
            label={t('Name des Gastes')}
            value={name}
            onChange={(e) => setName(e.target.value)}
          />
          <Field label={t('Verein')} value={club} onChange={(e) => setClub(e.target.value)} />
          <div className="button-row">
            <button
              type="button"
              className="button button-ghost"
              disabled={!name.trim()}
              onClick={async () => {
                const ok = await run(() =>
                  entriesApi.addPerson(org, call.id, { ...target, name, club }),
                )
                if (ok) {
                  setName('')
                  setClub('')
                }
              }}
            >
              {t('Gast hinzufügen')}
            </button>
          </div>
        </>
      )}
      {entry.can_pick_members && (
        <Checkbox label={t('Gast (kein Mitglied)')} checked={guest} onChange={setGuest} />
      )}
    </div>
  )
}

function AnswerField({
  org,
  call,
  block,
  value,
  locked,
  run,
}: {
  org: Scope
  call: CallDetail
  block: CallBlock
  value: unknown
  locked: boolean
  run: Run
}) {
  const initial =
    value == null ? '' : Array.isArray(value) ? value.map(String) : String(value as string)
  const [current, setCurrent] = useState<string | string[]>(initial)
  const save = (v: unknown) => void run(() => entriesApi.answer(org, call.id, block.id, v))
  const label = block.required ? `${block.label} (Pflicht)` : block.label
  if (block.kind === 'auswahl') {
    const opts = block.settings.options ?? []
    if (block.settings.multiple) {
      const chosen = Array.isArray(current) ? current : current ? [current] : []
      return (
        <fieldset disabled={locked}>
          <legend>{label}</legend>
          {opts.map((o) => (
            <Checkbox
              key={o}
              label={o}
              checked={chosen.includes(o)}
              onChange={(on) => {
                const next = on ? [...chosen, o] : chosen.filter((x) => x !== o)
                setCurrent(next)
                save(next)
              }}
            />
          ))}
        </fieldset>
      )
    }
    return (
      <SelectField
        label={label}
        value={typeof current === 'string' ? current : ''}
        disabled={locked}
        hint={block.help_text || undefined}
        onChange={(e) => {
          setCurrent(e.target.value)
          save(e.target.value)
        }}
      >
        <option value="">—</option>
        {opts.map((o) => (
          <option key={o} value={o}>
            {o}
          </option>
        ))}
      </SelectField>
    )
  }
  if (block.kind === 'text' && block.settings.multiline) {
    return (
      <label className="field">
        <span>{label}</span>
        <textarea
          rows={3}
          disabled={locked}
          value={typeof current === 'string' ? current : ''}
          onChange={(e) => setCurrent(e.target.value)}
          onBlur={() => current !== initial && save(current)}
        />
      </label>
    )
  }
  return (
    <Field
      label={label}
      type={block.kind === 'zahl' ? 'number' : 'text'}
      disabled={locked}
      hint={block.help_text || undefined}
      value={typeof current === 'string' ? current : ''}
      onChange={(e) => setCurrent(e.target.value)}
      onBlur={() => current !== initial && save(current)}
    />
  )
}

function NoteCard({
  org,
  call,
  entry,
  setEntry,
}: {
  org: Scope
  call: CallDetail
  entry: Entry
  setEntry: (e: Entry) => void
}) {
  const [note, setNote] = useState(entry.note)
  return (
    <div className="card card-wide">
      <label className="field">
        <span>{t('Interne Notiz (geht nicht an den Veranstalter)')}</span>
        <textarea
          rows={2}
          value={note}
          onChange={(e) => setNote(e.target.value)}
          onBlur={async () => {
            if (note !== entry.note) setEntry(await entriesApi.updateEntry(org, call.id, { note }))
          }}
        />
      </label>
    </div>
  )
}

function SubmitCard({
  org,
  call,
  entry,
  options,
  run,
  onDiscarded,
}: {
  org: Scope
  call: CallDetail
  entry: Entry
  options: EntryOptions
  run: Run
  onDiscarded: () => void
}) {
  const [channel, setChannel] = useState<Channel>(call.organizer_email ? 'email' : 'brief')
  const [email, setEmail] = useState(call.organizer_email)
  const [sentTo, setSentTo] = useState('')
  const [fn, setFn] = useState(options.functions[0] ?? '')
  const [busy, setBusy] = useState(false)
  // Nach Rückzug und „Wieder öffnen“ ist die nächste Abgabe wieder eine neue Meldung
  const first = entry.versions.length === 0 || entry.versions.at(-1)?.kind === 'rueckzug'
  const nothingNew = !first && !entry.changed
  const preview = (fmt: 'pdf' | 'xlsx' | 'csv') => entriesApi.previewUrl(org, call.id, fmt)

  async function submit() {
    setBusy(true)
    await run(() =>
      entriesApi.submit(org, call.id, {
        channel,
        email: channel === 'email' ? email : undefined,
        sent_to: channel === 'sonstiges' ? sentTo : undefined,
        function: fn,
      }),
    )
    setBusy(false)
  }

  async function withdraw() {
    const reason = await promptDialog({
      title: t('Meldung zurückziehen'),
      message: t(
        'Die Rückzugserklärung wird als neue Fassung festgehalten und über den gewählten Meldeweg verschickt bzw. als Brief erstellt.',
      ),
      label: t('Grund (optional)'),
      confirmLabel: t('Zurückziehen'),
      danger: true,
    })
    if (reason === null) return
    await run(() =>
      entriesApi.submit(org, call.id, {
        channel,
        email: channel === 'email' ? email : undefined,
        sent_to: channel === 'sonstiges' ? sentTo : undefined,
        function: fn,
        withdraw: true,
        reason,
      }),
    )
  }

  async function confirmed() {
    const note = await promptDialog({
      title: t('Bestätigung vermerken'),
      label: t('Wie und wann bestätigt?'),
      defaultValue: t('per Mail am {x1}', { x1: new Date().toLocaleDateString(locale()) }),
    })
    if (note !== null) await run(() => entriesApi.confirm(org, call.id, note))
  }

  async function discard() {
    const ok = await confirmDialog({
      title: t('Entwurf verwerfen'),
      message:
        entry.versions.length > 0
          ? `Alle Mannschaften, Personen und Angaben dieses Entwurfs samt ${entry.versions.length} früheren Fassungen löschen?`
          : t('Alle Mannschaften, Personen und Angaben dieses Entwurfs löschen?'),
      confirmLabel: t('Verwerfen'),
      danger: true,
    })
    if (ok && (await run(() => entriesApi.discard(org, call.id)))) onDiscarded()
  }

  if (call.internal)
    return (
      <div className="card card-wide">
        <div className="card-head">
          <h2>{first ? t('Meldung abgeben') : t('Änderung melden')}</h2>
        </div>
        <p className="muted">
          {t('Die Meldung geht in HUBIplan an ')}
          {call.organizer}
          {t('; dort wird sie bestätigt.')}
        </p>
        {nothingNew && entry.status !== 'rueckfrage' ? (
          <p className="muted">{t('Seit der letzten Fassung hat sich nichts geändert.')}</p>
        ) : (
          <div className="button-row">
            <button type="button" className="button" disabled={busy} onClick={submit}>
              {entry.status === 'rueckfrage' && nothingNew
                ? t('Erneut abgeben')
                : first
                  ? t('Meldung abgeben')
                  : t('Änderung melden')}
            </button>
          </div>
        )}
        <div className="button-row">
          {!first && (
            <button type="button" className="button button-ghost" onClick={withdraw}>
              {t('Meldung zurückziehen')}
            </button>
          )}
          {first && (
            <button type="button" className="button button-ghost" onClick={discard}>
              {t('Entwurf verwerfen')}
            </button>
          )}
        </div>
      </div>
    )

  return (
    <div className="card card-wide">
      <div className="card-head">
        <h2>{first ? t('Meldung abgeben') : t('Änderung melden')}</h2>
      </div>
      <p>
        {t('Vorschau:')}{' '}
        <a href={preview('pdf')} target="_blank" rel="noreferrer">
          {t('Brief (PDF)')}
        </a>{' '}
        · <a href={preview('xlsx')}>{t('Tabelle (Excel)')}</a> · <a href={preview('csv')}>CSV</a>
      </p>
      {nothingNew ? (
        <p className="muted">{t('Seit der letzten Fassung hat sich nichts geändert.')}</p>
      ) : (
        <>
          <div className="grid-3">
            <SelectField
              label={t('Meldeweg')}
              value={channel}
              onChange={(e) => setChannel(e.target.value as Channel)}
            >
              {(Object.keys(CHANNEL_LABELS) as Channel[]).map((k) => (
                <option key={k} value={k}>
                  {CHANNEL_LABELS[k]}
                </option>
              ))}
            </SelectField>
            {channel === 'email' && (
              <Field
                label={t('E-Mail des Veranstalters')}
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
              />
            )}
            {channel === 'sonstiges' && (
              <Field
                label={t('Vermerk')}
                placeholder={t('z. B. persönlich übergeben')}
                value={sentTo}
                onChange={(e) => setSentTo(e.target.value)}
              />
            )}
            {options.functions.length > 0 && (
              <SelectField
                label={t('Unterschrift als')}
                value={fn}
                onChange={(e) => setFn(e.target.value)}
              >
                {options.functions.map((f) => (
                  <option key={f} value={f}>
                    {f}
                  </option>
                ))}
              </SelectField>
            )}
          </div>
          <p className="muted small">
            {t('Unterzeichnet von ')}
            {options.signer}
            {t('. Im Brief bleibt Platz für die eigenhändige Unterschrift.')}
            {channel === 'brief' &&
              t(' Nach dem Abgeben findet ihr den Brief unter „Fassungen“ zum Drucken.')}
            {channel === 'email' && t(' Ihr bekommt eine Kopie an eure eigene Adresse.')}
          </p>
          <div className="button-row">
            <button type="button" className="button" disabled={busy} onClick={submit}>
              {first ? t('Meldung abgeben') : t('Änderung melden')}
            </button>
          </div>
        </>
      )}
      <div className="button-row">
        {entry.status === 'abgegeben' && (
          <button type="button" className="button button-ghost" onClick={confirmed}>
            {t('Bestätigung des Veranstalters vermerken')}
          </button>
        )}
        {entry.status === 'bestaetigt' && (
          <button
            type="button"
            className="button button-ghost"
            onClick={() => void run(() => entriesApi.unconfirm(org, call.id))}
          >
            {t('Bestätigung zurücknehmen')}
          </button>
        )}
        {!first && (
          <button type="button" className="button button-ghost" onClick={withdraw}>
            {t('Meldung zurückziehen')}
          </button>
        )}
        {first && (
          <button type="button" className="button button-ghost" onClick={discard}>
            {t('Entwurf verwerfen')}
          </button>
        )}
      </div>
    </div>
  )
}

/** Veranstalter: Meldung einer Untereinheit bestätigen oder mit Rückfrage zurückgeben. */
function OrganizerCard({
  org,
  call,
  entry,
  run,
}: {
  org: Scope
  call: CallDetail
  entry: Entry
  run: Run
}) {
  async function giveBack() {
    const question = await promptDialog({
      title: t('Mit Rückfrage zurückgeben'),
      label: t('Rückfrage'),
      message: t('Die Zugführung bekommt eine Mail und gibt danach erneut ab.'),
      confirmLabel: t('Zurückgeben'),
    })
    if (question) await run(() => entriesApi.returnEntry(org, call.id, question))
  }
  return (
    <div className="card card-wide">
      <h2>{t('Als Veranstalter')}</h2>
      {entry.status === 'entwurf' && (
        <p className="muted">{t('Die Meldung ist noch nicht abgegeben.')}</p>
      )}
      <div className="button-row">
        {entry.status === 'abgegeben' && (
          <button
            type="button"
            className="button"
            onClick={() => void run(() => entriesApi.confirm(org, call.id, ''))}
          >
            {t('Meldung bestätigen')}
          </button>
        )}
        {entry.status === 'bestaetigt' && (
          <button
            type="button"
            className="button button-ghost"
            onClick={() => void run(() => entriesApi.unconfirm(org, call.id))}
          >
            {t('Bestätigung zurücknehmen')}
          </button>
        )}
        {(entry.status === 'abgegeben' || entry.status === 'bestaetigt') && (
          <button type="button" className="button button-ghost" onClick={giveBack}>
            {t('Mit Rückfrage zurückgeben')}
          </button>
        )}
      </div>
      {entry.competition && (
        <p className="muted small">
          {t('Bestätigte Personen stehen als Starter im Wettbewerb')}{' '}
          <Link to={`/wettbewerbe/${entry.competition}`}>{call.title}</Link>.
        </p>
      )}
    </div>
  )
}

// --- Fassungen ---

function VersionsPanel({
  org,
  call,
  entry,
}: {
  org: Scope
  call: CallDetail
  entry: Entry | null
}) {
  if (!entry || entry.versions.length === 0)
    return <p className="muted">{t('Noch nichts abgegeben.')}</p>
  const url = (n: number, fmt: 'pdf' | 'xlsx' | 'csv') =>
    entriesApi.versionUrl(org, call.id, n, fmt)
  return (
    <div className="card card-wide">
      <table className="table">
        <thead>
          <tr>
            <th scope="col">{t('Fassung')}</th>
            <th scope="col">{t('Abgegeben')}</th>
            <th scope="col">{t('Meldeweg')}</th>
            <th scope="col">{t('Inhalt')}</th>
            <th scope="col">{t('Belege')}</th>
          </tr>
        </thead>
        <tbody>
          {[...entry.versions].reverse().map((v) => (
            <tr key={v.id}>
              <td>
                {v.number} · {v.kind_label}
              </td>
              <td>
                {new Date(v.created_at).toLocaleString(locale(), {
                  dateStyle: 'short',
                  timeStyle: 'short',
                })}
                <div className="muted small">{v.signed_by}</div>
              </td>
              <td>
                {v.channel_label}
                {v.sent_to && <div className="muted small">{v.sent_to}</div>}
              </td>
              <td>
                {v.changes.length > 0 ? (
                  <ul>
                    {v.changes.map((c, i) => (
                      <li key={i}>{c}</li>
                    ))}
                  </ul>
                ) : (
                  t('vollständige Meldung')
                )}
                {v.reason && (
                  <div className="muted small">
                    {t('Grund: ')}
                    {v.reason}
                  </div>
                )}
                {v.shortened && (
                  <div className="muted small">{t('nach Ablauf der Frist auf Namen gekürzt')}</div>
                )}
              </td>
              <td>
                <a href={url(v.number, 'pdf')} target="_blank" rel="noreferrer">
                  {t('Brief')}
                </a>{' '}
                · <a href={url(v.number, 'xlsx')}>Excel</a> · <a href={url(v.number, 'csv')}>CSV</a>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

// --- Ausschreibung bearbeiten ---

function numOrNull(raw: string): number | null {
  if (raw.trim() === '') return null
  const n = Number(raw)
  return Number.isFinite(n) ? n : null
}

function CallEditor({
  org,
  call,
  options,
  onChanged,
  reload,
}: {
  org: number
  call: CallDetail
  options: EntryOptions
  onChanged: (c: CallDetail) => void
  reload: () => void
}) {
  const navigate = useNavigate()
  const form = useForm({
    title: call.title,
    organizer: call.organizer,
    organizer_address: call.organizer_address,
    organizer_email: call.organizer_email,
    salutation: call.salutation,
    description: call.description,
    date: call.date ?? '',
    location: call.location,
    deadline: call.deadline ?? '',
    reference_date: call.reference_date ?? '',
    person_fields: call.person_fields,
    conditions: call.conditions,
    fee_amount: call.fee_amount ?? '',
    fee_per: call.fee_per,
    changes_after_deadline: call.changes_after_deadline,
    create_competition: call.create_competition,
    units: call.units,
    strict: call.strict,
  })
  const { values: v, set, errors } = form
  const auto = useAutoSave(
    form,
    (changes) => {
      const data: Record<string, unknown> = { ...changes }
      for (const k of ['date', 'deadline', 'reference_date', 'fee_amount'] as const)
        if (k in data && data[k] === '') data[k] = null
      return entriesApi.update(org, call.id, data as Partial<Call>)
    },
    { onSaved: (saved) => onChanged(saved as CallDetail) },
  )
  const cond = v.conditions
  const setCond = (c: Partial<Conditions>) => set('conditions', { ...cond, ...c })
  const toggle = (list: number[] | undefined, id: number, on: boolean) =>
    on ? [...(list ?? []), id] : (list ?? []).filter((x) => x !== id)

  async function copy() {
    const created = await entriesApi.copy(org, call.id)
    navigate(`/meldungen/${created.id}/ausschreibung`)
  }

  async function remove() {
    const ok = await confirmDialog({
      title: t('Ausschreibung löschen'),
      message: t('„{x1}“ samt Entwurf löschen?', { x1: call.title }),
      confirmLabel: t('Löschen'),
      danger: true,
    })
    if (!ok) return
    try {
      await entriesApi.remove(org, call.id)
      navigate('/meldungen')
    } catch (err) {
      form.setMessage({ kind: 'error', text: errorMessage(err) })
    }
  }

  return (
    <>
      <div className="card card-wide">
        <div className="card-head">
          <h2>{t('Ausschreibung')}</h2>
          <SaveStatus auto={auto} />
        </div>
        <div className="grid-3">
          <Field
            label={t('Titel')}
            value={v.title}
            error={errors.title}
            onChange={(e) => set('title', e.target.value)}
          />
          <Field
            label={t('Datum des Anlasses')}
            type="date"
            value={v.date}
            error={errors.date}
            onChange={(e) => set('date', e.target.value)}
          />
          <Field
            label={t('Ort')}
            value={v.location}
            error={errors.location}
            onChange={(e) => set('location', e.target.value)}
          />
          <Field
            label={t('Meldeschluss')}
            type="date"
            value={v.deadline}
            error={errors.deadline}
            onChange={(e) => set('deadline', e.target.value)}
          />
          <SelectField
            label={t('Nach Meldeschluss')}
            value={v.changes_after_deadline}
            onChange={(e) =>
              set('changes_after_deadline', e.target.value as Call['changes_after_deadline'])
            }
          >
            <option value="ersatz">{t('nur Ersatz von Personen')}</option>
            <option value="keine">{t('keine Änderungen')}</option>
            <option value="frei">{t('Änderungen bis zum Anlass')}</option>
          </SelectField>
          <Field
            label={t('Stichtag für Alter und Mitgliedschaft')}
            type="date"
            hint={t('leer: Datum des Anlasses')}
            value={v.reference_date}
            error={errors.reference_date}
            onChange={(e) => set('reference_date', e.target.value)}
          />
        </div>
        {call.internal && (
          <fieldset>
            <legend>
              {t('Angeschriebene ')}
              {options.unit_label}
              {t('-Einheiten (keine Auswahl: alle direkt darunter)')}
            </legend>
            {options.units.map((u) => (
              <Checkbox
                key={u.id}
                label={u.name}
                checked={v.units.includes(u.id)}
                onChange={(on) => set('units', toggle(v.units, u.id, on))}
              />
            ))}
          </fieldset>
        )}
        {!call.internal && <h3>{t('Veranstalter')}</h3>}
        {!call.internal && (
          <div className="grid-3">
            <Field
              label={t('Name')}
              value={v.organizer}
              error={errors.organizer}
              onChange={(e) => set('organizer', e.target.value)}
            />
            <label className="field">
              <span>{t('Anschrift (ohne Name)')}</span>
              <textarea
                rows={3}
                value={v.organizer_address}
                onChange={(e) => set('organizer_address', e.target.value)}
              />
            </label>
            <Field
              label={t('E-Mail')}
              type="email"
              value={v.organizer_email}
              error={errors.organizer_email}
              onChange={(e) => set('organizer_email', e.target.value)}
            />
            <Field
              label={t('Anrede im Brief')}
              value={v.salutation}
              error={errors.salutation}
              onChange={(e) => set('salutation', e.target.value)}
            />
          </div>
        )}
        <label className="field">
          <span>{t('Beschreibung (z. B. Auszug aus der Ausschreibung)')}</span>
          <textarea
            rows={3}
            value={v.description}
            onChange={(e) => set('description', e.target.value)}
          />
        </label>
        <h3>{t('Meldegebühr')}</h3>
        <div className="grid-3">
          <Field
            label={t('Betrag (€)')}
            inputMode="decimal"
            value={v.fee_amount}
            error={errors.fee_amount}
            onChange={(e) => set('fee_amount', e.target.value)}
          />
          <SelectField
            label={t('berechnet')}
            value={v.fee_per}
            onChange={(e) => set('fee_per', e.target.value as Call['fee_per'])}
          >
            <option value="mannschaft">{t('je Mannschaft')}</option>
            <option value="person">{t('je Person')}</option>
            <option value="pauschal">{t('pauschal')}</option>
          </SelectField>
        </div>
        <h3>{t('Angaben je Person')}</h3>
        <p className="muted small">
          {t('Nur angekreuzte Angaben gehen an den Veranstalter. Der Name steht immer drin.')}
        </p>
        <div className="grid-3">
          {options.person_fields.map((f) => (
            <Checkbox
              key={f.key}
              label={f.label}
              checked={v.person_fields.includes(f.key)}
              onChange={(on) =>
                set(
                  'person_fields',
                  on ? [...v.person_fields, f.key] : v.person_fields.filter((k) => k !== f.key),
                )
              }
            />
          ))}
        </div>
        <h3>{t('Bedingungen')}</h3>
        <p className="muted small">
          {t(
            'HUBIplan weist auf Verstöße hin; abgeben bleibt möglich, der Veranstalter entscheidet.',
          )}
        </p>
        {call.internal && (
          <Checkbox
            label={t('Verstöße sperren das Abgeben')}
            hint={t('sonst nur Hinweise; ihr entscheidet beim Bestätigen')}
            checked={v.strict}
            onChange={(on) => set('strict', on)}
          />
        )}
        <div className="grid-3">
          <Checkbox
            label={t('nur aktive Mitglieder am Stichtag')}
            checked={!!cond.active}
            onChange={(on) => setCond({ active: on })}
          />
          <Checkbox
            label={t('Gäste (Nichtmitglieder) erlaubt')}
            checked={!!cond.guests}
            onChange={(on) => setCond({ guests: on })}
          />
          <Checkbox
            label={t('jede Person nur in einer Mannschaft')}
            checked={!!cond.one_team}
            onChange={(on) => setCond({ one_team: on })}
          />
          <Field
            label={t('Mindestalter')}
            type="number"
            min={0}
            value={cond.min_age ?? ''}
            error={errors.min_age}
            onChange={(e) => setCond({ min_age: numOrNull(e.target.value) ?? undefined })}
          />
          <Field
            label={t('Höchstalter')}
            type="number"
            min={0}
            value={cond.max_age ?? ''}
            error={errors.max_age}
            onChange={(e) => setCond({ max_age: numOrNull(e.target.value) ?? undefined })}
          />
        </div>
        {options.member_types.length > 0 && (
          <fieldset>
            <legend>{t('nur diese Mitgliedsarten (keine Auswahl: alle)')}</legend>
            {options.member_types.map((t) => (
              <Checkbox
                key={t.id}
                label={t.name}
                checked={(cond.member_types ?? []).includes(t.id)}
                onChange={(on) => setCond({ member_types: toggle(cond.member_types, t.id, on) })}
              />
            ))}
          </fieldset>
        )}
        {options.units.length > 0 && (
          <fieldset>
            <legend>
              {t('nur aus diesen ')}
              {options.unit_label}
              {t('-Einheiten (keine Auswahl: alle)')}
            </legend>
            {options.units.map((u) => (
              <Checkbox
                key={u.id}
                label={u.name}
                checked={(cond.units ?? []).includes(u.id)}
                onChange={(on) => setCond({ units: toggle(cond.units, u.id, on) })}
              />
            ))}
          </fieldset>
        )}
        {options.competitions_enabled && (
          <Checkbox
            label={
              call.internal
                ? t('bestätigte Meldungen als Starter in einen eigenen Wettbewerb übernehmen')
                : t('beim Abgeben einen fremden Wettbewerb mit den Mannschaften anlegen')
            }
            hint={
              call.internal
                ? t(
                    'der Wettbewerb entsteht beim ersten Bestätigen, mit Wertung der Untereinheiten',
                  )
                : t('dort tragt ihr später eure Plätze ein')
            }
            checked={v.create_competition}
            onChange={(on) => set('create_competition', on)}
          />
        )}
        {form.message && <Alert kind={form.message.kind}>{form.message.text}</Alert>}
        <div className="button-row">
          <button type="button" className="button button-ghost" onClick={copy}>
            {t('Für das nächste Jahr kopieren')}
          </button>
          {!call.has_versions && (
            <button type="button" className="button button-ghost" onClick={remove}>
              {t('Ausschreibung löschen')}
            </button>
          )}
        </div>
      </div>
      <CallEventCard org={org} call={call} onChanged={onChanged} />
      <BlocksEditor org={org} call={call} reload={reload} />
    </>
  )
}

function BlocksEditor({
  org,
  call,
  reload,
}: {
  org: number
  call: CallDetail
  reload: () => void
}) {
  const [kind, setKind] = useState<BlockKind>('mannschaften')
  const [message, setMessage] = useState<string | null>(null)
  async function add() {
    setMessage(null)
    try {
      await entriesApi.addBlock(org, call.id, {
        kind,
        label: BLOCK_LABELS[kind],
        settings: kind === 'auswahl' ? { options: ['ja', 'nein'] } : {},
      })
      reload()
    } catch (err) {
      setMessage(errorMessage(err))
    }
  }
  return (
    <div className="card card-wide">
      <div className="card-head">
        <h2>{t('Was gemeldet wird')}</h2>
      </div>
      <p className="muted">
        {t(
          'Bausteine des Meldeformulars: Mannschaften, eine Personenliste (z. B. Delegierte), eine Zahl (z. B. Teilnehmer am Umzug), eine Auswahl oder ein Text.',
        )}
      </p>
      {call.blocks.map((b) => (
        <BlockCard key={b.id} org={org} call={call} block={b} reload={reload} />
      ))}
      {message && <Alert kind="error">{message}</Alert>}
      <div className="grid-3">
        <SelectField
          label={t('Baustein')}
          value={kind}
          onChange={(e) => setKind(e.target.value as BlockKind)}
        >
          {(Object.keys(BLOCK_LABELS) as BlockKind[]).map((k) => (
            <option key={k} value={k}>
              {BLOCK_LABELS[k]}
            </option>
          ))}
        </SelectField>
        <div className="button-row">
          <button type="button" className="button button-ghost" onClick={add}>
            {t('Baustein hinzufügen')}
          </button>
        </div>
      </div>
    </div>
  )
}

function BlockCard({
  org,
  call,
  block,
  reload,
}: {
  org: number
  call: CallDetail
  block: CallBlock
  reload: () => void
}) {
  const form = useForm({
    label: block.label,
    help_text: block.help_text,
    required: block.required,
    settings: block.settings,
  })
  const { values: v, set, errors } = form
  const auto = useAutoSave(form, (changes) =>
    entriesApi.updateBlock(org, call.id, block.id, changes),
  )
  const s = v.settings
  const setS = (x: Partial<BlockSettings>) => set('settings', { ...s, ...x })
  const num = (key: keyof BlockSettings, label: string) => (
    <Field
      label={label}
      type="number"
      min={0}
      value={(s[key] as number | undefined) ?? ''}
      error={errors[key]}
      onChange={(e) => setS({ [key]: numOrNull(e.target.value) ?? undefined })}
    />
  )
  const list = (key: 'positions' | 'options', label: string, hint: string) => (
    <Field
      label={label}
      hint={hint}
      value={(s[key] ?? []).join(', ')}
      error={errors[key]}
      onChange={(e) =>
        setS({
          [key]: e.target.value
            .split(',')
            .map((x) => x.trim())
            .filter(Boolean),
        })
      }
    />
  )

  async function remove() {
    const ok = await confirmDialog({
      title: t('Baustein entfernen'),
      message: t('„{x1}“ samt den Einträgen der Meldung entfernen?', { x1: block.label }),
      confirmLabel: t('Entfernen'),
      danger: true,
    })
    if (!ok) return
    try {
      await entriesApi.removeBlock(org, call.id, block.id)
      reload()
    } catch (err) {
      form.setMessage({ kind: 'error', text: errorMessage(err) })
    }
  }

  return (
    <div className="card">
      <div className="card-head">
        <h3>{BLOCK_LABELS[block.kind]}</h3>
        <SaveStatus auto={auto} />
        <button type="button" className="button button-ghost push-right" onClick={remove}>
          {t('Entfernen')}
        </button>
      </div>
      <div className="grid-3">
        <Field
          label={t('Bezeichnung')}
          value={v.label}
          error={errors.label}
          onChange={(e) => set('label', e.target.value)}
        />
        <Field
          label={t('Hinweis')}
          value={v.help_text}
          error={errors.help_text}
          onChange={(e) => set('help_text', e.target.value)}
        />
        <Checkbox
          label={t('Pflicht')}
          checked={v.required}
          onChange={(on) => set('required', on)}
        />
        {block.kind === 'mannschaften' && (
          <>
            {num('min_teams', t('Mannschaften mindestens'))}
            {num('max_teams', t('Mannschaften höchstens'))}
            {num('min_size', t('Personen je Mannschaft mindestens'))}
            {num('max_size', t('Personen je Mannschaft höchstens'))}
            {num('substitutes', t('Ersatzleute je Mannschaft höchstens'))}
            {list('positions', t('Aufgaben'), t('z. B. Mannschaftsführer, mit Komma getrennt'))}
          </>
        )}
        {block.kind === 'personen' && (
          <>
            {num('min', t('Personen mindestens'))}
            {num('max', t('Personen höchstens'))}
            {list('positions', t('Aufgaben'), t('z. B. Delegierter, Fahnenträger'))}
          </>
        )}
        {block.kind === 'zahl' && (
          <>
            {num('min', t('kleinster Wert'))}
            {num('max', t('größter Wert'))}
          </>
        )}
        {block.kind === 'auswahl' && (
          <>
            {list('options', t('Antworten'), t('mit Komma getrennt'))}
            <Checkbox
              label={t('mehrere Antworten möglich')}
              checked={!!s.multiple}
              onChange={(on) => setS({ multiple: on })}
            />
          </>
        )}
        {block.kind === 'text' && (
          <Checkbox
            label={t('mehrzeilig')}
            checked={!!s.multiline}
            onChange={(on) => setS({ multiline: on })}
          />
        )}
      </div>
      {form.message && <Alert kind={form.message.kind}>{form.message.text}</Alert>}
    </div>
  )
}
