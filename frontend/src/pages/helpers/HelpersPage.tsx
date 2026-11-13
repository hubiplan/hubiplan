// Helferdienste und Schichtpläne (konzepte/helferdienste.md, Schritte H1–H3): Dienstpläne,
// Dienste, Schichten mit Schnelleingabe, Einteilung durch die Verwaltung, Druck und Export,
// Kontingente für Untereinheiten, Kopie, Aufruf per Rundschreiben und geleistete Dienste (H4).
import { useCallback, useEffect, useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { berlin } from '../../components/calendar/time.ts'
import type { FormEvent } from 'react'
import { ApiError, saveBlob } from '../../api/client.ts'
import { helperApi } from '../../api/helpers.ts'
import type { Duty, HelperPlan, PlanStatus, Shift, UnitQuota } from '../../api/helpers.ts'
import type { PickedMember } from '../../api/members.ts'
import { PERM } from '../../api/orgs.ts'
import { MemberPicker } from '../../components/MemberPicker.tsx'
import { useDetailParam } from '../../components/detailParam.ts'
import { confirmDialog } from '../../components/dialog.ts'
import { errorMessage, useLoad } from '../../components/forms.ts'
import { Why } from '../../learning/Aids.tsx'
import { locale, t } from '../../i18n/index.ts'
import { useOrg } from '../../org/OrgContext.tsx'
import { PageHeader } from '../../components/PageHeader.tsx'
import { Loading } from '../../components/ui.tsx'
import './helpers.css'
import { PlaceField } from '../../components/PlaceField.tsx'

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

function started(s: Shift) {
  return new Date(s.starts_at).getTime() <= Date.now()
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
  // Aus dem Termin-Dialog: ?neu=1&termin=<id> öffnet „Neuer Dienstplan“ mit diesem Termin
  const [params, setParams] = useSearchParams()
  const [preset] = useState(() =>
    canEdit && params.get('neu') === '1' ? Number(params.get('termin')) || null : null,
  )
  const [creating, setCreating] = useState(canEdit && params.get('neu') === '1')
  useEffect(() => {
    if (!params.get('neu')) return
    const next = new URLSearchParams(params)
    next.delete('neu')
    next.delete('termin')
    setParams(next, { replace: true })
  }, [params, setParams])
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
        onOpen={async (id) => {
          await list.reload()
          detail.open(String(id))
        }}
      />
    )
  }
  const rows = list.data ?? []
  return (
    <div className="helpers">
      <PageHeader
        primary={
          canEdit && !creating
            ? { label: t('Neuer Dienstplan'), onClick: () => setCreating(true) }
            : null
        }
      />
      {creating && (
        <NewPlan
          base={base}
          event={preset}
          onDone={async (created) => {
            setCreating(false)
            if (created) {
              await list.reload()
              detail.open(String(created.id))
            }
          }}
        />
      )}
      {!base.startsWith('/api/orgs/') && <UnitQuotas base={base} orgId={orgId} canEdit={canEdit} />}
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
      {rows.length > 0 && <DoneCard base={base} />}
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
  event: initialEvent = null,
  onDone,
}: {
  base: string
  event?: number | null
  onDone: (created: HelperPlan | null) => Promise<void>
}) {
  const [title, setTitle] = useState('')
  const [event, setEvent] = useState<number | null>(initialEvent)
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
  onOpen,
}: {
  base: string
  orgId: number
  id: number
  onClose: () => void
  onOpen: (id: number) => Promise<void>
}) {
  const navigate = useNavigate()
  const [copying, setCopying] = useState(false)
  const loaded = useLoad(() => helperApi.get(base, id), [base, id])
  const club = base.startsWith('/api/orgs/')
  const unitList = useLoad(
    () => (club ? helperApi.units(base).catch(() => []) : Promise.resolve([])),
    [base, club],
  )
  const qualifications = useLoad(() => helperApi.qualifications(base).catch(() => []), [base])
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const plan = loaded.data
  if (loaded.error) return <p role="alert">{loaded.error}</p>
  if (!plan) return <Loading />
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
      <PageHeader
        title={plan.title}
        status={<span className="badge">{statusLabel(plan.status)}</span>}
        onBack={onClose}
      />
      <p>
        {plan.event && plan.event_title && (
          <>
            <Link
              to={`/termine?termin=${plan.event}${plan.event_starts_at ? `&datum=${berlin(plan.event_starts_at).date}` : ''}`}
              title={t('Termin im Kalender')}
            >
              {plan.event_title}
              {plan.event_starts_at ? ` · ${dayText(plan.event_starts_at)}` : ''}
            </Link>
            {' · '}
          </>
        )}
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
        {plan.can_callout && plan.status === 'published' && plan.open > 0 && (
          <button
            type="button"
            className="button button-ghost"
            disabled={busy}
            onClick={() =>
              run(async () => {
                const { circular } = await helperApi.callout(base, plan.id)
                navigate(`/rundschreiben/${circular}`)
              })
            }
          >
            {t('Aufruf als Rundschreiben')}
          </button>
        )}
        {plan.can_edit && !copying && (
          <button
            type="button"
            className="button button-ghost"
            disabled={busy}
            onClick={() => setCopying(true)}
          >
            {t('Plan kopieren')}
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
      {copying && (
        <CopyForm
          base={base}
          plan={plan}
          onDone={async (created) => {
            setCopying(false)
            if (created) await onOpen(created)
          }}
        />
      )}
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
          canMark={plan.can_edit}
          units={editable ? (unitList.data ?? []) : []}
          qualifications={editable ? (qualifications.data ?? []) : []}
          onChanged={loaded.reload}
        />
      ))}
      {plan.duties?.length === 0 && (
        <p className="muted">{t('Lege zuerst die Dienste an, etwa Theke, Kasse oder Aufbau.')}</p>
      )}
      {editable && (
        <NewDuty
          base={base}
          plan={plan.id}
          qualifications={qualifications.data ?? []}
          onSaved={loaded.reload}
        />
      )}
    </div>
  )
}

/** Auswahl der vorausgesetzten Qualifikation (nur mit Modul Qualifikationen und Arten). */
function QualificationSelect({
  value,
  options,
  onChange,
  label = t('Voraussetzung'),
}: {
  value: string
  options: { id: number; name: string }[]
  onChange: (value: string) => void
  label?: string
}) {
  return (
    <label className="field">
      <span>{label}</span>
      <select value={value} onChange={(e) => onChange(e.target.value)}>
        <option value="">{t('keine')}</option>
        {options.map((k) => (
          <option key={k.id} value={k.id}>
            {k.name}
          </option>
        ))}
      </select>
    </label>
  )
}

function NewDuty({
  base,
  plan,
  qualifications,
  onSaved,
}: {
  base: string
  plan: number
  qualifications: { id: number; name: string }[]
  onSaved: () => Promise<void>
}) {
  const [name, setName] = useState('')
  const [location, setLocation] = useState('')
  const [minAge, setMinAge] = useState('')
  const [qualification, setQualification] = useState('')
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
            ...(qualification ? { qualification: Number(qualification) } : {}),
          })
          setName('')
          setLocation('')
          setMinAge('')
          setQualification('')
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
        <PlaceField label={t('Ort')} value={location} onChange={setLocation} />
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
        {qualifications.length > 0 && (
          <QualificationSelect
            value={qualification}
            options={qualifications}
            onChange={setQualification}
          />
        )}
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
  canMark,
  units,
  qualifications,
  onChanged,
}: {
  base: string
  orgId: number
  duty: Duty
  editable: boolean
  canMark: boolean
  units: { id: number; name: string }[]
  qualifications: { id: number; name: string }[]
  onChanged: () => Promise<void>
}) {
  const [error, setError] = useState('')
  const [assigning, setAssigning] = useState<number | null>(null)
  const [quotaFor, setQuotaFor] = useState<number | null>(null)
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
      {(duty.location || duty.min_age || duty.qualification_name) && (
        <p className="muted">
          {[
            duty.location,
            duty.min_age ? t('ab {age} Jahren', { age: duty.min_age }) : '',
            duty.qualification_name
              ? t('Voraussetzung: {name}', { name: duty.qualification_name })
              : '',
          ]
            .filter(Boolean)
            .join(' · ')}
        </p>
      )}
      {editable && (qualifications.length > 0 || duty.qualification) && (
        <div className="duty-tools">
          <QualificationSelect
            label={t('Voraussetzung für „{name}“', { name: duty.name })}
            value={duty.qualification ? String(duty.qualification) : ''}
            options={
              duty.qualification && !qualifications.some((k) => k.id === duty.qualification)
                ? [...qualifications, { id: duty.qualification, name: duty.qualification_name }]
                : qualifications
            }
            onChange={(v) =>
              void act(() =>
                helperApi.updateDuty(base, duty.id, { qualification: v ? Number(v) : null }),
              )
            }
          />
        </div>
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
                    {s.quotas.map((q) => (
                      <div key={q.id} className="muted small">
                        {t('Kontingent {unit}: {filled} von {count}', {
                          unit: q.unit,
                          filled: q.filled,
                          count: q.count,
                        })}
                      </div>
                    ))}
                  </td>
                  <td>
                    <ul className="people">
                      {people.map((a) => (
                        <li key={a.id}>
                          {a.name}
                          {a.external && <span className="badge">{t('extern')}</span>}
                          {a.quota && (
                            <span className="badge">
                              {s.quotas.find((q) => q.id === a.quota)?.unit}
                            </span>
                          )}
                          {a.phone && <span className="muted small"> {a.phone}</span>}
                          {a.qualification_issue && (
                            <span className="badge badge-open" title={t('Hinweis')}>
                              {a.qualification_issue}
                            </span>
                          )}
                          {canMark && started(s) && (
                            <label className="done-mark">
                              <input
                                type="checkbox"
                                checked={a.done === true}
                                onChange={(e) =>
                                  act(() =>
                                    helperApi.updateAssignment(base, a.id, {
                                      done: e.target.checked,
                                    }),
                                  )
                                }
                              />
                              <span>{t('geleistet')}</span>
                            </label>
                          )}
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
                    {quotaFor === s.id && (
                      <QuotaForm
                        base={base}
                        shift={s}
                        label={label}
                        units={units}
                        onDone={async (changed) => {
                          setQuotaFor(null)
                          if (changed) await onChanged()
                        }}
                      />
                    )}
                    {editable &&
                      quotaFor !== s.id &&
                      (assigning === s.id ? (
                        <AssignForm
                          base={base}
                          orgId={orgId}
                          label={label}
                          assign={(data) => helperApi.assign(base, s.id, data)}
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
                          {units.length > 0 && (
                            <button
                              type="button"
                              className="button button-ghost"
                              aria-label={t('Kontingent vergeben: {shift}', { shift: label })}
                              onClick={() => setQuotaFor(s.id)}
                            >
                              {t('Kontingent')}
                            </button>
                          )}
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
  label,
  assign,
  membersOnly = false,
  onDone,
}: {
  base: string
  orgId: number
  label: string
  assign: (data: object) => Promise<unknown>
  membersOnly?: boolean
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
        await assign(data)
      } catch (err) {
        const body = err instanceof ApiError ? (err.body as { warnings?: string[] }) : null
        if (!body?.warnings?.length) throw err
        const yes = await confirmDialog({
          title: t('Trotzdem einteilen?'),
          message: errorMessage(err),
          confirmLabel: t('Trotzdem einteilen'),
        })
        if (!yes) return
        await assign({ ...data, force: true })
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
      {!membersOnly && (
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
      )}
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
        <Why k="helpers_names" />
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

function QuotaForm({
  base,
  shift,
  label,
  units,
  onDone,
}: {
  base: string
  shift: Shift
  label: string
  units: { id: number; name: string }[]
  onDone: (changed: boolean) => Promise<void>
}) {
  const [unit, setUnit] = useState(String(units[0]?.id ?? ''))
  const current = shift.quotas.find((q) => String(q.department) === unit)
  const [count, setCount] = useState(String(current?.count ?? 1))
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  return (
    <form
      className="assign-form stack"
      aria-label={t('Kontingent vergeben: {shift}', { shift: label })}
      onSubmit={async (e) => {
        e.preventDefault()
        setBusy(true)
        setError('')
        try {
          await helperApi.setQuota(base, shift.id, Number(unit), Number(count) || 0)
          await onDone(true)
        } catch (err) {
          setError(errorMessage(err))
        } finally {
          setBusy(false)
        }
      }}
    >
      <label className="field">
        <span>{t('Untereinheit')}</span>
        <select
          value={unit}
          onChange={(e) => {
            setUnit(e.target.value)
            const q = shift.quotas.find((x) => String(x.department) === e.target.value)
            setCount(String(q?.count ?? 1))
          }}
        >
          {units.map((u) => (
            <option key={u.id} value={u.id}>
              {u.name}
            </option>
          ))}
        </select>
      </label>
      <label className="field">
        <span>{t('Plätze (0 entfernt das Kontingent)')}</span>
        <input
          type="number"
          min={0}
          max={shift.needed}
          value={count}
          onChange={(e) => setCount(e.target.value)}
        />
      </label>
      {error && <p role="alert">{error}</p>}
      <div className="button-row">
        <button type="button" className="button button-ghost" onClick={() => onDone(false)}>
          {t('Abbrechen')}
        </button>
        <button className="button button-primary" disabled={busy || !unit}>
          {t('Kontingent speichern')}
        </button>
      </div>
    </form>
  )
}

function UnitQuotas({ base, orgId, canEdit }: { base: string; orgId: number; canEdit: boolean }) {
  const loaded = useLoad(() => helperApi.unitQuotas(base), [base])
  const [filling, setFilling] = useState<number | null>(null)
  const [error, setError] = useState('')
  const rows = loaded.data ?? []
  if (rows.length === 0) return null
  const remove = async (id: number) => {
    setError('')
    try {
      await helperApi.removeFromQuota(base, id)
      await loaded.reload()
    } catch (err) {
      setError(errorMessage(err))
    }
  }
  return (
    <section className="card stack" aria-labelledby="unit-quotas">
      <h2 id="unit-quotas">{t('Kontingente vom Verein')}</h2>
      <p className="muted">
        {t('Diese Plätze hat der Verein eurer Untereinheit gegeben. Teile eigene Mitglieder ein.')}
      </p>
      {error && <p role="alert">{error}</p>}
      <table className="table shift-table">
        <thead>
          <tr>
            <th>{t('Schicht')}</th>
            <th>{t('Besetzt')}</th>
            <th>{t('Eingeteilt')}</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((q: UnitQuota) => {
            const label = `${q.duty} ${dayText(q.starts_at)} ${timeText(q.starts_at)}–${timeText(q.ends_at)}`
            return (
              <tr key={q.id}>
                <td>
                  <strong>{q.duty}</strong> · {q.plan}
                  <div>
                    {dayText(q.starts_at)} {timeText(q.starts_at)}–{timeText(q.ends_at)}
                    {q.location && ` · ${q.location}`}
                  </div>
                  {q.note && <div className="muted small">{q.note}</div>}
                </td>
                <td className={q.filled < q.count ? 'shift-open' : undefined}>
                  {t('{taken} von {needed}', { taken: q.filled, needed: q.count })}
                </td>
                <td>
                  <ul className="people">
                    {q.assignments.map((a) => (
                      <li key={a.id}>
                        {a.name}
                        {canEdit && (
                          <button
                            type="button"
                            className="link-button"
                            aria-label={t('{name} aus der Schicht {shift} nehmen', {
                              name: a.name,
                              shift: label,
                            })}
                            onClick={() => remove(a.id)}
                          >
                            {t('Entfernen')}
                          </button>
                        )}
                      </li>
                    ))}
                  </ul>
                  {canEdit &&
                    (filling === q.id ? (
                      <AssignForm
                        base={base}
                        orgId={orgId}
                        label={label}
                        membersOnly
                        assign={(data) => helperApi.fillQuota(base, q.id, data)}
                        onDone={async (changed) => {
                          setFilling(null)
                          if (changed) await loaded.reload()
                        }}
                      />
                    ) : (
                      q.filled < q.count && (
                        <button
                          type="button"
                          className="button button-ghost"
                          aria-label={t('Person einteilen: {shift}', { shift: label })}
                          onClick={() => setFilling(q.id)}
                        >
                          {t('Einteilen')}
                        </button>
                      )
                    ))}
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </section>
  )
}

function CopyForm({
  base,
  plan,
  onDone,
}: {
  base: string
  plan: HelperPlan
  onDone: (created: number | null) => Promise<void>
}) {
  const starts = (plan.duties ?? []).flatMap((d) => d.shifts.map((x) => x.starts_at)).sort()
  const firstDay = starts.length
    ? new Date(starts[0]).toLocaleDateString('sv-SE', { timeZone: ZONE })
    : ''
  const [title, setTitle] = useState(plan.title)
  const [day, setDay] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const days =
    firstDay && day
      ? Math.round(
          (Date.parse(day + 'T12:00:00Z') - Date.parse(firstDay + 'T12:00:00Z')) / 86400000,
        )
      : 0
  return (
    <form
      className="card stack"
      aria-label={t('Plan kopieren')}
      onSubmit={async (e) => {
        e.preventDefault()
        setBusy(true)
        setError('')
        try {
          const created = await helperApi.copy(base, plan.id, { title, days })
          await onDone(created.id)
        } catch (err) {
          setError(errorMessage(err))
          setBusy(false)
        }
      }}
    >
      <p className="muted">
        {t(
          'Die Kopie übernimmt Dienste, Schichten, Kontingente und Einstellungen, aber keine Einteilungen.',
        )}
      </p>
      <label className="field">
        <span>{t('Titel')}</span>
        <input value={title} maxLength={200} required onChange={(e) => setTitle(e.target.value)} />
      </label>
      {firstDay && (
        <label className="field">
          <span>{t('Erster Tag des neuen Plans')}</span>
          <input type="date" value={day} onChange={(e) => setDay(e.target.value)} />
        </label>
      )}
      {error && <p role="alert">{error}</p>}
      <div className="button-row">
        <button type="button" className="button button-ghost" onClick={() => onDone(null)}>
          {t('Abbrechen')}
        </button>
        <button className="button button-primary" disabled={busy || !title.trim()}>
          {t('Kopie anlegen')}
        </button>
      </div>
    </form>
  )
}

function DoneCard({ base }: { base: string }) {
  const [year, setYear] = useState(() => new Date().getFullYear())
  const done = useLoad(() => helperApi.done(base, year), [base, year])
  const people = done.data?.people ?? []
  const hours = (minutes: number) =>
    (minutes / 60).toLocaleString(locale(), { maximumFractionDigits: 1 })
  return (
    <details className="card stack">
      <summary>{t('Geleistete Dienste')}</summary>
      <label className="field">
        <span>{t('Jahr')}</span>
        <input
          type="number"
          min={2000}
          max={2100}
          value={year}
          onChange={(e) => setYear(Number(e.target.value) || new Date().getFullYear())}
        />
      </label>
      {done.error && <p role="alert">{done.error}</p>}
      {done.data && people.length === 0 ? (
        <p className="muted">{t('Noch keine geleisteten Dienste in diesem Jahr.')}</p>
      ) : (
        <table className="table">
          <thead>
            <tr>
              <th>{t('Name')}</th>
              <th>{t('Schichten')}</th>
              <th>{t('Stunden')}</th>
            </tr>
          </thead>
          <tbody>
            {people.map((p) => (
              <tr key={`${p.membership ?? 'x'}-${p.name}`}>
                <td>
                  {p.name}
                  {p.external && <span className="badge">{t('extern')}</span>}
                </td>
                <td>{p.shifts}</td>
                <td>{hours(p.minutes)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </details>
  )
}
