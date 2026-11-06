// Helferdienste und Schichtpläne (konzepte/helferdienste.md, Schritt H1): Dienstpläne,
// Dienste, Schichten mit Schnelleingabe, Einteilung durch die Verwaltung, Druck und Export.
import { useCallback, useState } from 'react'
import type { FormEvent } from 'react'
import { ApiError, saveBlob } from '../../api/client.ts'
import { helperApi } from '../../api/helpers.ts'
import type { Duty, HelperPlan, PlanStatus, Shift } from '../../api/helpers.ts'
import type { PickedMember } from '../../api/members.ts'
import { PERM } from '../../api/orgs.ts'
import { MemberPicker } from '../../components/MemberPicker.tsx'
import { useDetailParam } from '../../components/detailParam.ts'
import { confirmDialog } from '../../components/dialog.ts'
import { errorMessage, useLoad } from '../../components/forms.ts'
import { locale, t } from '../../i18n/index.ts'
import { useOrg } from '../../org/OrgContext.tsx'
import './helpers.css'

const ZONE = 'Europe/Berlin'

function statusLabel(status: PlanStatus) {
  if (status === 'published') return t('veröffentlicht')
  if (status === 'closed') return t('abgeschlossen')
  return t('in Vorbereitung')
}

function dayText(value: string) {
  return new Date(value).toLocaleDateString(locale(), {
    timeZone: ZONE,
    weekday: 'short',
    day: '2-digit',
    month: '2-digit',
  })
}

function timeText(value: string) {
  return new Date(value).toLocaleTimeString(locale(), {
    timeZone: ZONE,
    hour: '2-digit',
    minute: '2-digit',
  })
}

function shiftText(s: Shift) {
  return `${dayText(s.starts_at)} ${timeText(s.starts_at)}–${timeText(s.ends_at)}`
}

export function HelpersPage() {
  const { active, activeDept } = useOrg()
  const permissions = active?.permissions ?? activeDept?.permissions ?? []
  const enabled = active ? active.modules.includes('helpers') : !!activeDept?.helpers_enabled
  if (!enabled || !permissions.includes(PERM.helpersView)) {
    return <p>{t('Dafür fehlt dir die Berechtigung.')}</p>
  }
  const base = active ? `/api/orgs/${active.id}/helpers/` : `/api/depts/${activeDept!.id}/helpers/`
  return (
    <Plans
      key={base}
      base={base}
      orgId={active?.id ?? activeDept!.id}
      canEdit={permissions.includes(PERM.helpersEdit)}
    />
  )
}

function Plans({ base, orgId, canEdit }: { base: string; orgId: number; canEdit: boolean }) {
  const detail = useDetailParam('plan')
  const list = useLoad(() => helperApi.list(base), [base])
  const [creating, setCreating] = useState(false)
  if (detail.value) {
    return (
      <PlanDetail
        base={base}
        orgId={orgId}
        id={Number(detail.value)}
        onClose={async () => {
          detail.close()
          await list.reload()
        }}
      />
    )
  }
  const rows = list.data ?? []
  return (
    <div className="helpers">
      <div className="page-heading">
        <h1>{t('Helferdienste')}</h1>
        {canEdit && !creating && (
          <button className="button" onClick={() => setCreating(true)}>
            {t('Neuer Dienstplan')}
          </button>
        )}
      </div>
      {creating && (
        <NewPlan
          base={base}
          onDone={async (created) => {
            setCreating(false)
            if (created) {
              await list.reload()
              detail.open(String(created.id))
            }
          }}
        />
      )}
      {list.error && <p role="alert">{list.error}</p>}
      {list.data && rows.length === 0 ? (
        <p className="muted">{t('Noch kein Dienstplan.')}</p>
      ) : (
        <table className="table">
          <thead>
            <tr>
              <th>{t('Dienstplan')}</th>
              <th>{t('Termin')}</th>
              <th>{t('Offene Plätze')}</th>
              <th>{t('Stand')}</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((p) => (
              <tr key={p.id}>
                <td>
                  <button
                    type="button"
                    className="link-button"
                    onClick={() => detail.open(String(p.id))}
                  >
                    {p.title}
                  </button>
                </td>
                <td>
                  {p.event_title}
                  {p.event_starts_at && ` · ${dayText(p.event_starts_at)}`}
                </td>
                <td>{t('{open} von {needed}', { open: p.open, needed: p.needed })}</td>
                <td>
                  <span className="badge">{statusLabel(p.status)}</span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  )
}

function EventSelect({
  base,
  value,
  onChange,
}: {
  base: string
  value: number | null
  onChange: (id: number | null) => void
}) {
  const events = useLoad(() => helperApi.events(base), [base])
  return (
    <label className="field">
      <span>{t('Termin (optional)')}</span>
      <select
        value={value ?? ''}
        onChange={(e) => onChange(e.target.value ? Number(e.target.value) : null)}
      >
        <option value="">{t('ohne Termin')}</option>
        {(events.data ?? []).map((e) => (
          <option key={e.id} value={e.id}>
            {dayText(e.starts_at)} · {e.title}
          </option>
        ))}
      </select>
    </label>
  )
}

function NewPlan({
  base,
  onDone,
}: {
  base: string
  onDone: (created: HelperPlan | null) => Promise<void>
}) {
  const [title, setTitle] = useState('')
  const [event, setEvent] = useState<number | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  return (
    <form
      className="card stack"
      onSubmit={async (e) => {
        e.preventDefault()
        setBusy(true)
        setError('')
        try {
          await onDone(await helperApi.create(base, { title, event }))
        } catch (err) {
          setError(errorMessage(err))
        } finally {
          setBusy(false)
        }
      }}
    >
      <h2>{t('Neuer Dienstplan')}</h2>
      <label className="field">
        <span>{t('Titel')}</span>
        <input
          value={title}
          maxLength={200}
          required
          placeholder={t('z. B. Schützenfest')}
          onChange={(e) => setTitle(e.target.value)}
        />
      </label>
      <EventSelect base={base} value={event} onChange={setEvent} />
      {error && <p role="alert">{error}</p>}
      <div className="button-row">
        <button type="button" className="button button-ghost" onClick={() => onDone(null)}>
          {t('Abbrechen')}
        </button>
        <button className="button button-primary" disabled={busy || !title.trim()}>
          {t('Anlegen')}
        </button>
      </div>
    </form>
  )
}

function PlanDetail({
  base,
  orgId,
  id,
  onClose,
}: {
  base: string
  orgId: number
  id: number
  onClose: () => void
}) {
  const loaded = useLoad(() => helperApi.get(base, id), [base, id])
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const plan = loaded.data
  if (loaded.error) return <p role="alert">{loaded.error}</p>
  if (!plan) return <p>{t('Wird geladen …')}</p>
  const editable = plan.can_edit && plan.status !== 'closed'
  const run = async (action: () => Promise<unknown>) => {
    setBusy(true)
    setError('')
    try {
      await action()
      await loaded.reload()
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setBusy(false)
    }
  }
  const setStatus = (status: PlanStatus) => run(() => helperApi.update(base, plan, { status }))
  return (
    <div className="helpers">
      <div className="page-heading">
        <h1>
          {plan.title}
          <span className="badge">{statusLabel(plan.status)}</span>
        </h1>
        <button className="button button-ghost" onClick={onClose}>
          {t('Zurück zur Übersicht')}
        </button>
      </div>
      <p>
        {plan.event_title &&
          `${plan.event_title}${plan.event_starts_at ? ` · ${dayText(plan.event_starts_at)}` : ''} · `}
        {t('{open} von {needed} Plätzen offen', { open: plan.open, needed: plan.needed })}
      </p>
      {error && <p role="alert">{error}</p>}
      <div className="button-row">
        <button
          type="button"
          className="button button-ghost"
          disabled={busy}
          onClick={() =>
            run(async () =>
              saveBlob(await helperApi.export(base, plan.id, 'pdf'), `dienstplan-${plan.id}.pdf`),
            )
          }
        >
          {t('Aushang als PDF')}
        </button>
        <button
          type="button"
          className="button button-ghost"
          disabled={busy}
          onClick={() =>
            run(async () =>
              saveBlob(await helperApi.export(base, plan.id, 'xlsx'), `dienstplan-${plan.id}.xlsx`),
            )
          }
        >
          {t('Liste als Excel')}
        </button>
        {plan.can_edit && plan.status === 'draft' && (
          <button
            type="button"
            className="button"
            disabled={busy}
            onClick={() => setStatus('published')}
          >
            {t('Veröffentlichen')}
          </button>
        )}
        {plan.can_edit && plan.status === 'published' && (
          <button
            type="button"
            className="button"
            disabled={busy}
            onClick={() => setStatus('closed')}
          >
            {t('Abschließen')}
          </button>
        )}
        {plan.can_edit && plan.status !== 'draft' && (
          <button
            type="button"
            className="button button-ghost"
            disabled={busy}
            onClick={() => setStatus(plan.status === 'closed' ? 'published' : 'draft')}
          >
            {plan.status === 'closed' ? t('Wieder öffnen') : t('Zurück in Vorbereitung')}
          </button>
        )}
        {plan.can_edit && plan.status !== 'published' && (
          <button
            type="button"
            className="button button-danger"
            disabled={busy}
            onClick={async () => {
              const yes = await confirmDialog({
                title: t('Dienstplan löschen?'),
                message: t('Dienste, Schichten und Einteilungen werden ebenfalls gelöscht.'),
                confirmLabel: t('Löschen'),
              })
              if (!yes) return
              setBusy(true)
              try {
                await helperApi.remove(base, plan.id)
                onClose()
              } catch (err) {
                setError(errorMessage(err))
                setBusy(false)
              }
            }}
          >
            {t('Löschen')}
          </button>
        )}
      </div>
      <p className="muted">
        {plan.status === 'draft'
          ? t('Im Mitgliederbereich erscheint der Plan erst nach dem Veröffentlichen.')
          : plan.status === 'published'
            ? t('Der Plan steht im Mitgliederbereich.')
            : t('Der Plan ist abgeschlossen.')}
      </p>
      {editable && (
        <PlanSettings key={plan.version} base={base} plan={plan} onSaved={loaded.reload} />
      )}
      {(plan.duties ?? []).map((duty) => (
        <DutyCard
          key={duty.id}
          base={base}
          orgId={orgId}
          duty={duty}
          editable={editable}
          onChanged={loaded.reload}
        />
      ))}
      {plan.duties?.length === 0 && (
        <p className="muted">{t('Lege zuerst die Dienste an, etwa Theke, Kasse oder Aufbau.')}</p>
      )}
      {editable && <NewDuty base={base} plan={plan.id} onSaved={loaded.reload} />}
    </div>
  )
}

function NewDuty({
  base,
  plan,
  onSaved,
}: {
  base: string
  plan: number
  onSaved: () => Promise<void>
}) {
  const [name, setName] = useState('')
  const [location, setLocation] = useState('')
  const [minAge, setMinAge] = useState('')
  const [error, setError] = useState('')
  return (
    <form
      className="card helper-form"
      onSubmit={async (e) => {
        e.preventDefault()
        setError('')
        try {
          await helperApi.addDuty(base, plan, {
            name,
            location,
            min_age: minAge ? Number(minAge) : null,
          })
          setName('')
          setLocation('')
          setMinAge('')
          await onSaved()
        } catch (err) {
          setError(errorMessage(err))
        }
      }}
    >
      <h2>{t('Dienst hinzufügen')}</h2>
      <div className="helper-fields">
        <label className="field">
          <span>{t('Dienst')}</span>
          <input
            value={name}
            maxLength={100}
            required
            placeholder={t('z. B. Theke Festzelt')}
            onChange={(e) => setName(e.target.value)}
          />
        </label>
        <label className="field">
          <span>{t('Ort')}</span>
          <input value={location} maxLength={200} onChange={(e) => setLocation(e.target.value)} />
        </label>
        <label className="field">
          <span>{t('Mindestalter')}</span>
          <input
            type="number"
            min={1}
            max={99}
            value={minAge}
            onChange={(e) => setMinAge(e.target.value)}
          />
        </label>
      </div>
      {error && <p role="alert">{error}</p>}
      <div className="button-row">
        <button className="button button-primary" disabled={!name.trim()}>
          {t('Dienst hinzufügen')}
        </button>
      </div>
    </form>
  )
}

function DutyCard({
  base,
  orgId,
  duty,
  editable,
  onChanged,
}: {
  base: string
  orgId: number
  duty: Duty
  editable: boolean
  onChanged: () => Promise<void>
}) {
  const [error, setError] = useState('')
  const [assigning, setAssigning] = useState<number | null>(null)
  const act = async (action: () => Promise<unknown>) => {
    setError('')
    try {
      await action()
      await onChanged()
    } catch (err) {
      setError(errorMessage(err))
    }
  }
  return (
    <section className="card stack" aria-labelledby={`duty-${duty.id}`}>
      <div className="duty-head">
        <h2 id={`duty-${duty.id}`}>{duty.name}</h2>
        {editable && (
          <button
            type="button"
            className="button button-ghost"
            onClick={async () => {
              const yes = await confirmDialog({
                title: t('Dienst „{name}“ löschen?', { name: duty.name }),
                message: t('Die Schichten werden ebenfalls gelöscht.'),
                confirmLabel: t('Löschen'),
              })
              if (yes) await act(() => helperApi.removeDuty(base, duty.id))
            }}
          >
            {t('Dienst löschen')}
          </button>
        )}
      </div>
      {(duty.location || duty.min_age) && (
        <p className="muted">
          {[duty.location, duty.min_age ? t('ab {age} Jahren', { age: duty.min_age }) : '']
            .filter(Boolean)
            .join(' · ')}
        </p>
      )}
      {error && <p role="alert">{error}</p>}
      {duty.shifts.length > 0 && (
        <table className="table shift-table">
          <thead>
            <tr>
              <th>{t('Schicht')}</th>
              <th>{t('Besetzt')}</th>
              <th>{t('Eingeteilt')}</th>
            </tr>
          </thead>
          <tbody>
            {duty.shifts.map((s) => {
              const people = s.assignments.filter((a) => a.status === 'active')
              const label = shiftText(s)
              return (
                <tr key={s.id}>
                  <td>
                    {label}
                    {s.note && <div className="muted small">{s.note}</div>}
                  </td>
                  <td className={people.length < s.needed ? 'shift-open' : undefined}>
                    {t('{taken} von {needed}', { taken: people.length, needed: s.needed })}
                  </td>
                  <td>
                    <ul className="people">
                      {people.map((a) => (
                        <li key={a.id}>
                          {a.name}
                          {a.external && <span className="badge">{t('extern')}</span>}
                          {a.phone && <span className="muted small"> {a.phone}</span>}
                          {editable && (
                            <button
                              type="button"
                              className="link-button"
                              aria-label={t('{name} aus der Schicht {shift} nehmen', {
                                name: a.name,
                                shift: label,
                              })}
                              onClick={() => act(() => helperApi.removeAssignment(base, a.id))}
                            >
                              {t('Entfernen')}
                            </button>
                          )}
                        </li>
                      ))}
                    </ul>
                    {editable &&
                      (assigning === s.id ? (
                        <AssignForm
                          base={base}
                          orgId={orgId}
                          shift={s}
                          label={label}
                          onDone={async (changed) => {
                            setAssigning(null)
                            if (changed) await onChanged()
                          }}
                        />
                      ) : (
                        <div className="button-row">
                          <button
                            type="button"
                            className="button button-ghost"
                            aria-label={t('Person einteilen: {shift}', { shift: label })}
                            onClick={() => setAssigning(s.id)}
                          >
                            {t('Einteilen')}
                          </button>
                          {people.length === 0 && (
                            <button
                              type="button"
                              className="button button-ghost"
                              aria-label={t('Schicht löschen: {shift}', { shift: label })}
                              onClick={() => act(() => helperApi.removeShift(base, s.id))}
                            >
                              {t('Schicht löschen')}
                            </button>
                          )}
                        </div>
                      ))}
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      )}
      {editable && <NewShifts base={base} duty={duty} onSaved={onChanged} />}
    </section>
  )
}

function NewShifts({
  base,
  duty,
  onSaved,
}: {
  base: string
  duty: Duty
  onSaved: () => Promise<void>
}) {
  const [day, setDay] = useState('')
  const [quick, setQuick] = useState('')
  const [needed, setNeeded] = useState('2')
  const [error, setError] = useState('')
  return (
    <form
      className="helper-form"
      aria-label={t('Schichten für {name} anlegen', { name: duty.name })}
      onSubmit={async (e) => {
        e.preventDefault()
        setError('')
        try {
          await helperApi.addShifts(base, duty.id, { day, quick, needed: Number(needed) || 1 })
          setQuick('')
          await onSaved()
        } catch (err) {
          setError(errorMessage(err))
        }
      }}
    >
      <div className="helper-fields">
        <label className="field">
          <span>{t('Tag')}</span>
          <input type="date" value={day} required onChange={(e) => setDay(e.target.value)} />
        </label>
        <label className="field">
          <span>{t('Zeiten')}</span>
          <input
            value={quick}
            required
            maxLength={300}
            placeholder={t('z. B. 14-18, 18-22, 22-02')}
            onChange={(e) => setQuick(e.target.value)}
          />
        </label>
        <label className="field">
          <span>{t('Personen je Schicht')}</span>
          <input
            type="number"
            min={1}
            max={500}
            value={needed}
            onChange={(e) => setNeeded(e.target.value)}
          />
        </label>
      </div>
      {error && <p role="alert">{error}</p>}
      <div className="button-row">
        <button className="button" disabled={!day || !quick.trim()}>
          {t('Schichten anlegen')}
        </button>
      </div>
    </form>
  )
}

function AssignForm({
  base,
  orgId,
  shift,
  label,
  onDone,
}: {
  base: string
  orgId: number
  shift: Shift
  label: string
  onDone: (changed: boolean) => Promise<void>
}) {
  const [external, setExternal] = useState(false)
  const [member, setMember] = useState<PickedMember | null>(null)
  const [name, setName] = useState('')
  const [phone, setPhone] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const search = useCallback((term: string) => helperApi.members(base, term), [base])
  const submit = async (e: FormEvent) => {
    e.preventDefault()
    const data = external ? { name, phone } : { membership: member?.id }
    setBusy(true)
    setError('')
    try {
      try {
        await helperApi.assign(base, shift.id, data)
      } catch (err) {
        const body = err instanceof ApiError ? (err.body as { warnings?: string[] }) : null
        if (!body?.warnings?.length) throw err
        const yes = await confirmDialog({
          title: t('Trotzdem einteilen?'),
          message: errorMessage(err),
          confirmLabel: t('Trotzdem einteilen'),
        })
        if (!yes) return
        await helperApi.assign(base, shift.id, { ...data, force: true })
      }
      await onDone(true)
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setBusy(false)
    }
  }
  return (
    <form
      className="assign-form stack"
      aria-label={t('Einteilen: {shift}', { shift: label })}
      onSubmit={submit}
    >
      <div className="segmented" role="group" aria-label={t('Wer?')}>
        <button
          type="button"
          className={`button button-ghost${!external ? ' is-active' : ''}`}
          aria-pressed={!external}
          onClick={() => setExternal(false)}
        >
          {t('Mitglied')}
        </button>
        <button
          type="button"
          className={`button button-ghost${external ? ' is-active' : ''}`}
          aria-pressed={external}
          onClick={() => setExternal(true)}
        >
          {t('Externe Person')}
        </button>
      </div>
      {external ? (
        <>
          <label className="field">
            <span>{t('Name')}</span>
            <input
              value={name}
              maxLength={200}
              required
              onChange={(e) => setName(e.target.value)}
            />
          </label>
          <label className="field">
            <span>{t('Telefon')}</span>
            <input
              type="tel"
              value={phone}
              maxLength={50}
              onChange={(e) => setPhone(e.target.value)}
            />
          </label>
        </>
      ) : (
        <MemberPicker
          orgId={orgId}
          value={member}
          onChange={setMember}
          label={t('Mitglied')}
          search={search}
        />
      )}
      {error && <p role="alert">{error}</p>}
      <div className="button-row">
        <button type="button" className="button button-ghost" onClick={() => onDone(false)}>
          {t('Abbrechen')}
        </button>
        <button
          className="button button-primary"
          disabled={busy || (external ? !name.trim() : !member)}
        >
          {t('Einteilen')}
        </button>
      </div>
    </form>
  )
}

function PlanSettings({
  base,
  plan,
  onSaved,
}: {
  base: string
  plan: HelperPlan
  onSaved: () => Promise<void>
}) {
  const initial = {
    title: plan.title,
    event: plan.event,
    signup: plan.signup,
    cancel_days: String(plan.cancel_days),
    max_shifts: plan.max_shifts ? String(plan.max_shifts) : '',
    remind_days: plan.remind_days ? String(plan.remind_days) : '',
    show_names: plan.show_names,
    note: plan.note ?? '',
  }
  const [v, setV] = useState(initial)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const dirty = JSON.stringify(v) !== JSON.stringify(initial)
  const set = <K extends keyof typeof v>(key: K, value: (typeof v)[K]) =>
    setV((prev) => ({ ...prev, [key]: value }))
  return (
    <details className="card">
      <summary>{t('Einstellungen des Plans')}</summary>
      <form
        className="stack"
        onSubmit={async (e) => {
          e.preventDefault()
          setBusy(true)
          setError('')
          try {
            await helperApi.update(base, plan, {
              title: v.title,
              event: v.event,
              signup: v.signup,
              cancel_days: Number(v.cancel_days) || 0,
              max_shifts: v.max_shifts ? Number(v.max_shifts) : null,
              remind_days: v.remind_days ? Number(v.remind_days) : null,
              show_names: v.show_names,
              note: v.note,
            })
            await onSaved()
          } catch (err) {
            setError(errorMessage(err))
          } finally {
            setBusy(false)
          }
        }}
      >
        <div className="helper-fields">
          <label className="field">
            <span>{t('Titel')}</span>
            <input
              value={v.title}
              maxLength={200}
              required
              onChange={(e) => set('title', e.target.value)}
            />
          </label>
          <EventSelect base={base} value={v.event} onChange={(id) => set('event', id)} />
          <label className="field">
            <span>{t('Art der Eintragung')}</span>
            <select
              value={v.signup}
              onChange={(e) => set('signup', e.target.value as HelperPlan['signup'])}
            >
              <option value="self">{t('Mitglieder tragen sich selbst ein')}</option>
              <option value="assign">{t('nur Einteilung durch die Verwaltung')}</option>
            </select>
          </label>
          <label className="field">
            <span>{t('Absagen bis Tage vorher')}</span>
            <input
              type="number"
              min={0}
              max={60}
              value={v.cancel_days}
              onChange={(e) => set('cancel_days', e.target.value)}
            />
          </label>
          <label className="field">
            <span>{t('Höchstens Schichten je Person')}</span>
            <input
              type="number"
              min={1}
              max={50}
              value={v.max_shifts}
              onChange={(e) => set('max_shifts', e.target.value)}
            />
          </label>
          <label className="field">
            <span>{t('Erinnerung Tage vorher')}</span>
            <input
              type="number"
              min={1}
              max={14}
              value={v.remind_days}
              onChange={(e) => set('remind_days', e.target.value)}
            />
          </label>
        </div>
        <label className="checkbox">
          <input
            type="checkbox"
            checked={v.show_names}
            onChange={(e) => set('show_names', e.target.checked)}
          />
          {t('Eingetragene sehen, wer noch in ihrer Schicht ist')}
        </label>
        <label className="field">
          <span>{t('Hinweis für die Helfer')}</span>
          <textarea
            value={v.note}
            rows={3}
            maxLength={5000}
            onChange={(e) => set('note', e.target.value)}
          />
        </label>
        {error && <p role="alert">{error}</p>}
        <div className="button-row">
          <button className="button button-primary" disabled={busy || !dirty}>
            {t('Einstellungen speichern')}
          </button>
        </div>
      </form>
    </details>
  )
}
