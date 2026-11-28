// Meldungen: Blöcke einer Meldung ausfüllen (Mannschaften, Personen, Antworten).
import { useCallback, useState } from 'react'
import {
  entriesApi,
  type CallBlock,
  type CallDetail,
  type Candidate,
  type Entry,
  type EntryPerson,
  type EntryTeam,
  type Scope,
} from '../../api/entries.ts'
import type { PickedMember } from '../../api/members.ts'
import { MemberPicker } from '../../components/MemberPicker.tsx'
import { confirmDialog } from '../../components/dialog.ts'
import { Checkbox, Field, SelectField } from '../../components/ui.tsx'
import { t } from '../../i18n/index.ts'
import { type Run } from './EntryPanel.tsx'

export function BlockEntry({
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
      final: true,
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
