// Mitglieder › Haushalte und Firmen (Konzept Familien, Haushalte und Firmen, H1/H2):
// Mitglieder zu einer Familie oder Firma verbinden. Briefe an eine Familie mit gleicher
// Anschrift gehen als ein Brief; mit Zahler gehen die Beiträge als eine Rechnung.
import { useState } from 'react'
import type { FormEvent } from 'react'
import { Link } from 'react-router-dom'
import { ApiError } from '../../api/client.ts'
import { householdApi } from '../../api/households.ts'
import type {
  Household,
  HouseholdKind,
  HouseholdMember,
  HouseholdRole,
  HouseholdSuggestion,
} from '../../api/households.ts'
import { todayIso } from '../../api/members.ts'
import type { MemberRow } from '../../api/members.ts'
import { PERM } from '../../api/orgs.ts'
import { confirmDialog } from '../../components/dialog.ts'
import { errorMessage, formatDate, useLoad } from '../../components/forms.ts'
import { MemberPicker } from '../../components/MemberPicker.tsx'
import { Segmented } from '../../components/PageHeader.tsx'
import { Alert, Checkbox, Field, Loading, SelectField } from '../../components/ui.tsx'
import { t } from '../../i18n/index.ts'
import { useActiveOrg } from '../../org/OrgContext.tsx'
import { HouseholdPayerPanel } from './HouseholdPayer.tsx'

const ROLE_LABELS: Record<HouseholdRole, string> = {
  adult: t('Erwachsener'),
  child: t('Kind'),
  '': t('ohne Angabe'),
}

function roleOf(birthDate: string | null): HouseholdRole {
  if (!birthDate) return ''
  const born = new Date(birthDate)
  const now = new Date()
  let age = now.getFullYear() - born.getFullYear()
  if (
    now.getMonth() < born.getMonth() ||
    (now.getMonth() === born.getMonth() && now.getDate() < born.getDate())
  )
    age -= 1
  return age >= 18 ? 'adult' : 'child'
}

function otherHousehold(err: unknown): boolean {
  if (!(err instanceof ApiError)) return false
  const body = err.body as { code?: unknown } | null
  return JSON.stringify(body?.code ?? '').includes('other_household')
}

export function HouseholdsPage() {
  const org = useActiveOrg()
  const canEdit = org.permissions.includes(PERM.membersEdit)
  // Beitrag und Zahler (H2) nur mit Modul „Beiträge“ und Leserecht dort
  const billing = org.modules.includes('billing') && org.permissions.includes(PERM.billingView)
  const [kind, setKind] = useState<HouseholdKind>('family')
  const [past, setPast] = useState(false)
  const { data, error, reload } = useLoad(
    () => householdApi.list(org.id, { art: kind, ehemalige: past }),
    [org.id, kind, past],
  )
  const [creating, setCreating] = useState(false)
  const [message, setMessage] = useState<{ kind: 'error' | 'success'; text: string } | null>(null)

  return (
    <div className="stack">
      <p className="muted">
        {t(
          'Familien und Haushalte verbinden Mitglieder, die zusammen wohnen: Rundschreiben und Einladungen an dieselbe Anschrift gehen dann als ein Brief. Unter Firmen stehen Mitglieder, für die eine Firma zahlt.',
        )}
      </p>
      <div className="households-toolbar">
        <Segmented
          label={t('Art')}
          value={kind}
          onChange={(v) => {
            setKind(v)
            setCreating(false)
          }}
          options={[
            { value: 'family', label: t('Familien und Haushalte') },
            { value: 'company', label: t('Firmen') },
          ]}
        />
        <label className="checkbox">
          <input type="checkbox" checked={past} onChange={(e) => setPast(e.target.checked)} />
          <span>{t('Frühere Mitglieder zeigen')}</span>
        </label>
        {canEdit && !creating && (
          <button type="button" className="button" onClick={() => setCreating(true)}>
            {kind === 'family' ? t('Haushalt anlegen') : t('Firma anlegen')}
          </button>
        )}
      </div>
      {message && <Alert kind={message.kind}>{message.text}</Alert>}
      {creating && (
        <NewHousehold
          orgId={org.id}
          kind={kind}
          onDone={(created) => {
            setCreating(false)
            if (created) {
              setMessage({ kind: 'success', text: t('„{name}“ angelegt.', { name: created }) })
              void reload()
            }
          }}
        />
      )}
      {error && <Alert kind="error">{error}</Alert>}
      {!data && !error && <Loading />}
      {data && data.length === 0 && (
        <p className="muted">
          {kind === 'family'
            ? t('Noch keine Familien oder Haushalte angelegt.')
            : t('Noch keine Firmen angelegt.')}
        </p>
      )}
      {data?.map((h) => (
        <HouseholdCard
          key={h.id}
          orgId={org.id}
          household={h}
          canEdit={canEdit}
          billing={billing}
          canEditBilling={billing && org.permissions.includes(PERM.billingEdit)}
          onChange={() => void reload()}
          onMessage={setMessage}
        />
      ))}
      {kind === 'family' && canEdit && (
        <Suggestions orgId={org.id} onCreated={() => void reload()} onMessage={setMessage} />
      )}
    </div>
  )
}

function NewHousehold({
  orgId,
  kind,
  onDone,
}: {
  orgId: number
  kind: HouseholdKind
  onDone: (created: string | null) => void
}) {
  const [name, setName] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  async function submit(e: FormEvent) {
    e.preventDefault()
    setBusy(true)
    try {
      const created = await householdApi.create(orgId, { kind, name })
      onDone(created.name)
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <form className="card stack" onSubmit={(e) => void submit(e)}>
      <h2>{kind === 'family' ? t('Neuer Haushalt') : t('Neue Firma')}</h2>
      {error && <Alert kind="error">{error}</Alert>}
      <Field
        label={t('Name')}
        value={name}
        required
        maxLength={200}
        placeholder={kind === 'family' ? t('z. B. Familie Muster') : t('z. B. Musterbau GmbH')}
        onChange={(e) => setName(e.target.value)}
      />
      <div className="button-row">
        <button type="submit" className="button" disabled={busy}>
          {t('Anlegen')}
        </button>
        <button type="button" className="button button-ghost" onClick={() => onDone(null)}>
          {t('Abbrechen')}
        </button>
      </div>
    </form>
  )
}

function HouseholdCard({
  orgId,
  household,
  canEdit,
  billing,
  canEditBilling,
  onChange,
  onMessage,
}: {
  orgId: number
  household: Household
  canEdit: boolean
  billing: boolean
  canEditBilling: boolean
  onChange: () => void
  onMessage: (m: { kind: 'error' | 'success'; text: string } | null) => void
}) {
  const [adding, setAdding] = useState(false)
  const [renaming, setRenaming] = useState(false)
  const family = household.kind === 'family'
  const current = household.members.filter((m) => m.current)

  async function run(action: () => Promise<unknown>, success: string) {
    onMessage(null)
    try {
      await action()
      onMessage({ kind: 'success', text: success })
      onChange()
    } catch (err) {
      onMessage({ kind: 'error', text: errorMessage(err) })
    }
  }

  async function end(m: HouseholdMember) {
    const ok = await confirmDialog({
      title: t('{name} aus „{household}“ nehmen?', {
        name: `${m.first_name} ${m.last_name}`,
        household: household.name,
      }),
      message: t(
        'Die Zugehörigkeit endet heute. Sie bleibt als früherer Eintrag sichtbar; Briefe gehen dann wieder einzeln.',
      ),
      confirmLabel: t('Herausnehmen'),
      danger: false,
    })
    if (!ok) return
    await run(
      () => householdApi.changeMember(orgId, household.id, m.link, { valid_until: todayIso() }),
      t('{name} gehört nicht mehr zu „{household}“.', {
        name: `${m.first_name} ${m.last_name}`,
        household: household.name,
      }),
    )
  }

  async function togglePays(m: HouseholdMember) {
    const name = `${m.first_name} ${m.last_name}`
    await run(
      () => householdApi.changeMember(orgId, household.id, m.link, { pays_via: !m.pays_via }),
      m.pays_via
        ? t('Der Beitrag für {name} geht wieder einzeln.', { name })
        : t('Der Beitrag für {name} geht über „{household}“.', {
            name,
            household: household.name,
          }),
    )
  }

  async function remove() {
    const ok = await confirmDialog({
      title: t('„{name}“ löschen?', { name: household.name }),
      message: t('Frühere Zugehörigkeiten werden mit gelöscht.'),
      confirmLabel: t('Löschen'),
    })
    if (!ok) return
    await run(
      () => householdApi.remove(orgId, household.id),
      t('„{name}“ gelöscht.', { name: household.name }),
    )
  }

  return (
    <section className="card card-wide" aria-label={household.name}>
      {renaming ? (
        <Rename
          orgId={orgId}
          household={household}
          onDone={(changed) => {
            setRenaming(false)
            if (changed) onChange()
          }}
        />
      ) : (
        <h2>{household.name}</h2>
      )}
      {household.members.length === 0 ? (
        <p className="muted">{t('Niemand zugeordnet.')}</p>
      ) : (
        <ul className="item-list">
          {household.members.map((m) => (
            <li key={m.link} className="item-row">
              <div className="item-row-info">
                <Link to={`/mitglieder/${m.membership}`}>
                  {[m.title, m.first_name, m.last_name].filter(Boolean).join(' ')}
                </Link>
                {family && m.role && <span className="badge">{ROLE_LABELS[m.role]}</span>}
                {billing && m.pays_via && (
                  <span className="badge">{t('Beitrag über den Haushalt')}</span>
                )}
                <span className="muted small">
                  {' '}
                  {m.valid_until
                    ? t('{from} bis {until}', {
                        from: formatDate(m.valid_from),
                        until: formatDate(m.valid_until),
                      })
                    : t('seit {date}', { date: formatDate(m.valid_from) })}
                </span>
              </div>
              {canEdit && m.current && !m.valid_until && (
                <div className="button-row">
                  {billing && (
                    <button
                      type="button"
                      className="link-button"
                      onClick={() => void togglePays(m)}
                    >
                      {m.pays_via ? t('Beitrag einzeln') : t('Beitrag über den Haushalt')}
                    </button>
                  )}
                  <button type="button" className="link-button" onClick={() => void end(m)}>
                    {t('Herausnehmen')}
                  </button>
                </div>
              )}
            </li>
          ))}
        </ul>
      )}
      {billing && (
        <HouseholdPayerPanel orgId={orgId} household={household} canEdit={canEditBilling} />
      )}
      {canEdit &&
        (adding ? (
          <AddMember
            orgId={orgId}
            household={household}
            billing={billing}
            onDone={(changed) => {
              setAdding(false)
              if (changed) onChange()
            }}
          />
        ) : (
          <div className="button-row">
            <button type="button" className="button" onClick={() => setAdding(true)}>
              {t('Mitglied hinzufügen')}
            </button>
            <button type="button" className="button button-ghost" onClick={() => setRenaming(true)}>
              {t('Umbenennen')}
            </button>
            {current.length === 0 && (
              <button type="button" className="button button-ghost" onClick={() => void remove()}>
                {t('Löschen')}
              </button>
            )}
          </div>
        ))}
    </section>
  )
}

function Rename({
  orgId,
  household,
  onDone,
}: {
  orgId: number
  household: Household
  onDone: (changed: boolean) => void
}) {
  const [name, setName] = useState(household.name)
  const [error, setError] = useState<string | null>(null)

  async function submit(e: FormEvent) {
    e.preventDefault()
    try {
      await householdApi.update(orgId, household.id, { name })
      onDone(true)
    } catch (err) {
      setError(errorMessage(err))
    }
  }

  return (
    <form className="stack" onSubmit={(e) => void submit(e)}>
      {error && <Alert kind="error">{error}</Alert>}
      <Field
        label={t('Name')}
        value={name}
        required
        maxLength={200}
        onChange={(e) => setName(e.target.value)}
      />
      <div className="button-row">
        <button type="submit" className="button">
          {t('Speichern')}
        </button>
        <button type="button" className="button button-ghost" onClick={() => onDone(false)}>
          {t('Abbrechen')}
        </button>
      </div>
    </form>
  )
}

function AddMember({
  orgId,
  household,
  billing,
  onDone,
}: {
  orgId: number
  household: Household
  billing: boolean
  onDone: (changed: boolean) => void
}) {
  const family = household.kind === 'family'
  const [member, setMember] = useState<MemberRow | null>(null)
  // Firmen zahlen meist für ihre Mitarbeiter; in Familien nur ausdrücklich (FH-4)
  const [paysVia, setPaysVia] = useState(!family && billing)
  const [role, setRole] = useState<HouseholdRole>('')
  const [since, setSince] = useState(todayIso())
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  function pick(m: MemberRow | null) {
    setMember(m)
    if (m && family) setRole(roleOf(m.birth_date))
  }

  async function save(move: boolean) {
    if (!member) return
    setBusy(true)
    try {
      await householdApi.addMember(orgId, household.id, {
        membership: member.id,
        role: family ? role : '',
        valid_from: since,
        move,
        pays_via: billing && paysVia,
      })
      onDone(true)
    } catch (err) {
      if (!move && otherHousehold(err)) {
        const ok = await confirmDialog({
          title: t('In „{name}“ wechseln?', { name: household.name }),
          message: errorMessage(err),
          confirmLabel: t('Wechseln'),
          danger: false,
        })
        if (ok) {
          setBusy(false)
          await save(true)
          return
        }
      }
      setError(errorMessage(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <form
      className="stack"
      onSubmit={(e) => {
        e.preventDefault()
        void save(false)
      }}
    >
      <h3>{t('Mitglied hinzufügen')}</h3>
      {error && <Alert kind="error">{error}</Alert>}
      <MemberPicker orgId={orgId} value={member} onChange={pick} label={t('Mitglied')} />
      {family && (
        <SelectField
          label={t('Rolle im Haushalt')}
          value={role}
          onChange={(e) => setRole(e.target.value as HouseholdRole)}
        >
          <option value="adult">{ROLE_LABELS.adult}</option>
          <option value="child">{ROLE_LABELS.child}</option>
          <option value="">{ROLE_LABELS['']}</option>
        </SelectField>
      )}
      <Field
        label={t('seit')}
        type="date"
        value={since}
        required
        onChange={(e) => setSince(e.target.value)}
      />
      {billing && (
        <Checkbox
          label={t('Beitrag über den Haushalt')}
          hint={t('Der Beitrag steht dann auf der Rechnung an den Zahler.')}
          checked={paysVia}
          onChange={setPaysVia}
        />
      )}
      <div className="button-row">
        <button type="submit" className="button" disabled={!member || busy}>
          {t('Hinzufügen')}
        </button>
        <button type="button" className="button button-ghost" onClick={() => onDone(false)}>
          {t('Abbrechen')}
        </button>
      </div>
    </form>
  )
}

function Suggestions({
  orgId,
  onCreated,
  onMessage,
}: {
  orgId: number
  onCreated: () => void
  onMessage: (m: { kind: 'error' | 'success'; text: string } | null) => void
}) {
  const [open, setOpen] = useState(false)
  const { data, error, reload } = useLoad(
    () => (open ? householdApi.suggestions(orgId) : Promise.resolve(null)),
    [orgId, open],
  )

  async function create(s: HouseholdSuggestion) {
    onMessage(null)
    const free = s.members.filter((m) => m.household === null)
    try {
      const created = await householdApi.create(orgId, { kind: 'family', name: s.name })
      for (const m of free) {
        await householdApi.addMember(orgId, created.id, {
          membership: m.id,
          role: roleOf(m.birth_date),
        })
      }
      onMessage({
        kind: 'success',
        text: t('„{name}“ mit {count} Mitgliedern angelegt.', {
          name: created.name,
          count: free.length,
        }),
      })
      onCreated()
      void reload()
    } catch (err) {
      onMessage({ kind: 'error', text: errorMessage(err) })
    }
  }

  return (
    <section className="card card-wide" aria-labelledby="haushalt-vorschlaege">
      <h2 id="haushalt-vorschlaege">{t('Vorschläge aus gleicher Anschrift')}</h2>
      {!open ? (
        <>
          <p className="muted">
            {t(
              'HUBIplan sucht aktuelle Mitglieder mit derselben Anschrift, die noch nicht zusammen in einem Haushalt sind. Angelegt wird nur, was du bestätigst.',
            )}
          </p>
          <div className="button-row">
            <button type="button" className="button button-ghost" onClick={() => setOpen(true)}>
              {t('Vorschläge suchen')}
            </button>
          </div>
        </>
      ) : error ? (
        <Alert kind="error">{error}</Alert>
      ) : !data ? (
        <Loading small />
      ) : data.length === 0 ? (
        <p className="muted">{t('Keine Vorschläge.')}</p>
      ) : (
        <ul className="item-list">
          {data.map((s) => (
            <li key={`${s.street}-${s.postal_code}-${s.city}`} className="item-row">
              <div className="item-row-info">
                <strong>{s.name}</strong>
                <span className="muted small">
                  {' '}
                  {[s.street, `${s.postal_code} ${s.city}`.trim()].filter(Boolean).join(', ')}
                </span>
                <br />
                {s.members.map((m) => `${m.first_name} ${m.last_name}`).join(', ')}
                {s.members.some((m) => m.household !== null) && (
                  <span className="muted small">
                    {' '}
                    · {t('teils schon in einem anderen Haushalt')}
                  </span>
                )}
              </div>
              <div className="button-row">
                <button type="button" className="button" onClick={() => void create(s)}>
                  {t('Als Haushalt anlegen')}
                </button>
              </div>
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}
