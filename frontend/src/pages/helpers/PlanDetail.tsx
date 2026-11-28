import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { berlin } from '../../components/calendar/time.ts'
import { saveBlob } from '../../api/client.ts'
import { helperApi } from '../../api/helpers.ts'
import type { HelperPlan, PlanStatus } from '../../api/helpers.ts'
import { confirmDialog } from '../../components/dialog.ts'
import { errorMessage, useLoad } from '../../components/forms.ts'
import { Why } from '../../learning/Aids.tsx'
import { t } from '../../i18n/index.ts'
import { PageHeader } from '../../components/PageHeader.tsx'
import { Loading } from '../../components/ui.tsx'
import './helpers.css'
import { PlaceField } from '../../components/PlaceField.tsx'
import { ZONE, dayText, statusLabel } from './helpersHelpers.ts'
import { EventSelect } from './EventSelect.tsx'
import { QualificationSelect } from './QualificationSelect.tsx'
import { DutyCard } from './DutyCard.tsx'

export function PlanDetail({
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
                final: true,
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
            placeholder={t('z. B. Getränkestand')}
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
