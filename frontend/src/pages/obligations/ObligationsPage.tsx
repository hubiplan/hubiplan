// Fristenkalender: wiederkehrende Pflichten des Vereins (Freistellungsbescheid, Kassenprüfung,
// Transparenzregister …) mit Erinnerung, Verlauf und Vorschlägen für eingetragene Vereine.
// Nach einer Vorstandswahl legt HUBIplan die Aufgabe für das Registergericht an.
import { useEffect, useRef, useState } from 'react'
import { obligationApi } from '../../api/obligations.ts'
import type {
  Obligation,
  ObligationInput,
  ObligationList,
  ObligationSuggestion,
} from '../../api/obligations.ts'
import { PageHeader } from '../../components/PageHeader.tsx'
import { useDetailParam } from '../../components/detailParam.ts'
import { confirmDialog } from '../../components/dialog.ts'
import { errorMessage, formatDate, useLoad } from '../../components/forms.ts'
import { Alert, Field, LoadError, Loading, SelectField } from '../../components/ui.tsx'
import { t } from '../../i18n/index.ts'
import { useActiveOrg } from '../../org/OrgContext.tsx'
import { TextArea } from '../settings/TextArea.tsx'
import './obligations.css'

const INTERVALS = [1, 3, 6, 12, 24, 36, 48, 60]

function intervalLabel(months: number | null) {
  if (!months) return t('einmalig')
  if (months === 12) return t('jedes Jahr')
  if (months % 12 === 0) return t('alle {n} Jahre', { n: months / 12 })
  if (months === 1) return t('jeden Monat')
  return t('alle {n} Monate', { n: months })
}

function today() {
  const d = new Date()
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`
}

interface Draft {
  title: string
  note: string
  due_date: string
  interval: string
  remind_days: string
  days_after: string
  role: string
}

function draftOf(o: Obligation | ObligationSuggestion | null): Draft {
  return {
    title: o?.title ?? '',
    note: o?.note ?? '',
    due_date: o?.due_date ?? '',
    interval: o?.interval_months ? String(o.interval_months) : '',
    remind_days: String(o?.remind_days ?? 30),
    days_after: String(o && 'days_after' in o ? o.days_after : 14),
    role: o && 'role' in o && o.role ? String(o.role) : '',
  }
}

function ObligationForm({
  initial,
  election,
  roles,
  submitLabel,
  onSubmit,
  onCancel,
}: {
  initial: Draft
  election: boolean
  roles: ObligationList['roles']
  submitLabel: string
  onSubmit: (input: ObligationInput) => Promise<void>
  onCancel: () => void
}) {
  const [d, setD] = useState(initial)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const set = <K extends keyof Draft>(key: K, value: Draft[K]) => setD({ ...d, [key]: value })
  const intervals = INTERVALS.includes(Number(d.interval) || 12)
    ? INTERVALS
    : [...INTERVALS, Number(d.interval)].sort((a, b) => a - b)
  return (
    <form
      className="stack"
      onSubmit={async (e) => {
        e.preventDefault()
        setBusy(true)
        setError(null)
        try {
          await onSubmit({
            title: d.title.trim(),
            note: d.note.trim(),
            role: d.role ? Number(d.role) : null,
            ...(election
              ? { days_after: Number(d.days_after) || 0 }
              : {
                  due_date: d.due_date || null,
                  interval_months: d.interval ? Number(d.interval) : null,
                  remind_days: Number(d.remind_days) || 0,
                }),
          })
        } catch (err) {
          setError(errorMessage(err))
          setBusy(false)
        }
      }}
    >
      <Field
        label={t('Bezeichnung')}
        required
        maxLength={200}
        value={d.title}
        onChange={(e) => set('title', e.target.value)}
      />
      {election ? (
        <div className="grid-2">
          <Field
            label={t('Frist der Aufgabe (Tage nach der Versammlung)')}
            type="number"
            min={0}
            max={365}
            required
            value={d.days_after}
            onChange={(e) => set('days_after', e.target.value)}
          />
        </div>
      ) : (
        <div className="grid-2">
          <Field
            label={t('Nächste Frist')}
            type="date"
            required
            value={d.due_date}
            onChange={(e) => set('due_date', e.target.value)}
          />
          <SelectField
            label={t('Wiederholung')}
            value={d.interval}
            onChange={(e) => set('interval', e.target.value)}
          >
            <option value="">{t('einmalig')}</option>
            {intervals.map((m) => (
              <option key={m} value={m}>
                {intervalLabel(m)}
              </option>
            ))}
          </SelectField>
          <Field
            label={t('Erinnerung (Tage vor der Frist)')}
            type="number"
            min={0}
            max={365}
            required
            value={d.remind_days}
            onChange={(e) => set('remind_days', e.target.value)}
          />
        </div>
      )}
      <SelectField
        label={t('Zuständig')}
        hint={
          election
            ? t('Die Aufgabe wird mit den Inhabern dieser Rolle geteilt.')
            : t(
                'Die Inhaber dieser Rolle bekommen die Erinnerung. Ohne Auswahl: alle, die den Fristenkalender pflegen.',
              )
        }
        value={d.role}
        onChange={(e) => set('role', e.target.value)}
      >
        <option value="">{t('keine bestimmte Rolle')}</option>
        {roles.map((r) => (
          <option key={r.id} value={r.id}>
            {r.name}
          </option>
        ))}
      </SelectField>
      <TextArea
        label={t('Hinweis')}
        hint={t('z. B. Rechtsgrundlage, Ansprechpartner oder wo die Unterlagen liegen')}
        rows={4}
        value={d.note}
        onChange={(value) => set('note', value)}
      />
      {error && <Alert kind="error">{error}</Alert>}
      <div className="button-row">
        <button type="submit" className="button button-primary" disabled={busy}>
          {submitLabel}
        </button>
        <button type="button" className="button" onClick={onCancel}>
          {t('Abbrechen')}
        </button>
      </div>
    </form>
  )
}

function DoneForm({
  onSubmit,
  onCancel,
}: {
  onSubmit: (data: { done_on: string; note: string }) => Promise<void>
  onCancel: () => void
}) {
  const [doneOn, setDoneOn] = useState(today())
  const [note, setNote] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  return (
    <form
      className="stack obligation-done"
      onSubmit={async (e) => {
        e.preventDefault()
        setBusy(true)
        setError(null)
        try {
          await onSubmit({ done_on: doneOn, note: note.trim() })
        } catch (err) {
          setError(errorMessage(err))
          setBusy(false)
        }
      }}
    >
      <div className="grid-2">
        <Field
          label={t('Erledigt am')}
          type="date"
          required
          max={today()}
          value={doneOn}
          onChange={(e) => setDoneOn(e.target.value)}
        />
        <Field
          label={t('Vermerk')}
          maxLength={2000}
          placeholder={t('z. B. Bescheid vom 12.03. liegt im Ordner Finanzamt')}
          value={note}
          onChange={(e) => setNote(e.target.value)}
        />
      </div>
      {error && <Alert kind="error">{error}</Alert>}
      <div className="button-row">
        <button type="submit" className="button button-primary" disabled={busy}>
          {t('Als erledigt vermerken')}
        </button>
        <button type="button" className="button" onClick={onCancel}>
          {t('Abbrechen')}
        </button>
      </div>
    </form>
  )
}

function StatusBadge({ o }: { o: Obligation }) {
  if (o.status === 'overdue')
    return <span className="badge badge-cancelled">{t('überfällig')}</span>
  if (o.status === 'soon') return <span className="badge badge-open">{t('bald fällig')}</span>
  if (o.status === 'done') return <span className="badge badge-public">{t('erledigt')}</span>
  if (o.status === 'inactive') return <span className="badge">{t('abgeschaltet')}</span>
  return null
}

function History({ o }: { o: Obligation }) {
  if (o.history.length === 0) return null
  return (
    <details className="small">
      <summary>{t('Verlauf')}</summary>
      <ul className="obligation-history">
        {o.history.map((h) => (
          <li key={h.id}>
            {t('erledigt am {date}', { date: formatDate(h.done_on) })}
            {h.done_by && ` · ${h.done_by}`}
            {h.due_date && ` · ${t('Frist {date}', { date: formatDate(h.due_date) })}`}
            {h.note && <div className="muted">{h.note}</div>}
          </li>
        ))}
      </ul>
    </details>
  )
}

export function ObligationsPage() {
  const org = useActiveOrg()
  const base = `/api/orgs/${org.id}/obligations/`
  const { data, error, reload, setData } = useLoad(() => obligationApi.list(base), [base])
  const detail = useDetailParam('pflicht')
  const [editing, setEditing] = useState<number | 'new' | null>(null)
  const [adopting, setAdopting] = useState<ObligationSuggestion | null>(null)
  const [finishing, setFinishing] = useState<number | null>(null)
  const [actionError, setActionError] = useState<string | null>(null)
  const marked = useRef<HTMLLIElement | null>(null)
  const form = useRef<HTMLElement | null>(null)
  const focus = detail.value ? Number(detail.value) : null
  const loaded = !!data
  useEffect(() => {
    if (loaded && focus) marked.current?.scrollIntoView?.({ block: 'center' })
  }, [loaded, focus])
  const adoptKey = adopting?.key
  useEffect(() => {
    if (adoptKey) form.current?.scrollIntoView?.({ block: 'start' })
  }, [adoptKey])
  if (error) return <LoadError message={error} onRetry={reload} />
  if (!data) return <Loading />

  const canEdit = data.can_edit
  const replace = (o: Obligation) =>
    setData({ ...data, items: data.items.map((x) => (x.id === o.id ? o : x)) })
  const open = data.items
    .filter((o) => o.active && o.trigger === 'date')
    .sort((a, b) => (a.due_date ?? '').localeCompare(b.due_date ?? ''))
  const elections = data.items.filter((o) => o.trigger === 'election')
  const closed = data.items.filter((o) => !o.active && o.trigger === 'date')

  const remove = async (o: Obligation) => {
    const yes = await confirmDialog({
      message: t('Pflicht „{name}“ mit ihrem Verlauf löschen?', { name: o.title }),
      confirmLabel: t('Löschen'),
    })
    if (!yes) return
    setActionError(null)
    try {
      await obligationApi.remove(base, o.id)
      reload()
    } catch (err) {
      setActionError(errorMessage(err))
    }
  }
  const toggle = async (o: Obligation) => {
    setActionError(null)
    try {
      replace(await obligationApi.update(base, o.id, { version: o.version, active: !o.active }))
    } catch (err) {
      setActionError(errorMessage(err))
    }
  }

  const row = (o: Obligation) => {
    if (editing === o.id) {
      return (
        <li key={o.id}>
          <ObligationForm
            initial={draftOf(o)}
            election={o.trigger === 'election'}
            roles={data.roles}
            submitLabel={t('Speichern')}
            onCancel={() => setEditing(null)}
            onSubmit={async (input) => {
              replace(await obligationApi.update(base, o.id, { ...input, version: o.version }))
              setEditing(null)
            }}
          />
        </li>
      )
    }
    const election = o.trigger === 'election'
    return (
      <li
        key={o.id}
        ref={focus === o.id ? marked : undefined}
        className={focus === o.id ? 'obligation-marked' : undefined}
      >
        <div className="item-row">
          <div className="item-row-info">
            <div>
              <strong>{o.title}</strong>
              <StatusBadge o={o} />
            </div>
            <div className="muted small">
              {election
                ? t('Aufgabe mit Frist {n} Tage nach der Versammlung', { n: o.days_after })
                : [
                    o.due_date && t('Frist {date}', { date: formatDate(o.due_date) }),
                    intervalLabel(o.interval_months),
                    o.active && t('Erinnerung {n} Tage vorher', { n: o.remind_days }),
                  ]
                    .filter(Boolean)
                    .join(' · ')}
              {o.role_name && ` · ${t('zuständig: {role}', { role: o.role_name })}`}
            </div>
            {o.note && <p className="small obligation-note">{o.note}</p>}
            <History o={o} />
          </div>
          <div className="button-row">
            {o.active && !election && (
              <button
                type="button"
                className="button button-primary"
                onClick={() => setFinishing(finishing === o.id ? null : o.id)}
              >
                {t('Erledigt')}
              </button>
            )}
            {canEdit && election && (
              <button type="button" className="button" onClick={() => void toggle(o)}>
                {o.active ? t('Abschalten') : t('Einschalten')}
              </button>
            )}
            {canEdit && (o.active || election) && (
              <button type="button" className="button" onClick={() => setEditing(o.id)}>
                {t('Bearbeiten')}
              </button>
            )}
            {canEdit && (
              <button type="button" className="button button-danger" onClick={() => void remove(o)}>
                {t('Löschen')}
              </button>
            )}
          </div>
        </div>
        {finishing === o.id && (
          <DoneForm
            onCancel={() => setFinishing(null)}
            onSubmit={async (input) => {
              replace(await obligationApi.done(base, o.id, input))
              setFinishing(null)
            }}
          />
        )}
      </li>
    )
  }

  return (
    <div className="stack">
      <PageHeader
        subtitle={t(
          'Wiederkehrende Pflichten des Vereins mit Frist, Erinnerung und Nachweis, wann sie erledigt wurden.',
        )}
        primary={
          canEdit && editing !== 'new'
            ? {
                label: t('Neue Pflicht'),
                onClick: () => {
                  setAdopting(null)
                  setEditing('new')
                },
              }
            : null
        }
      />
      {editing === 'new' && (
        <section className="card card-wide" ref={form}>
          <h2>{adopting ? t('Vorschlag übernehmen') : t('Neue Pflicht')}</h2>
          <ObligationForm
            key={adopting?.key ?? 'neu'}
            initial={draftOf(adopting)}
            election={adopting?.trigger === 'election'}
            roles={data.roles}
            submitLabel={adopting ? t('Übernehmen') : t('Pflicht speichern')}
            onCancel={() => {
              setEditing(null)
              setAdopting(null)
            }}
            onSubmit={async (input) => {
              await obligationApi.create(base, adopting ? { ...input, key: adopting.key } : input)
              setEditing(null)
              setAdopting(null)
              reload()
            }}
          />
        </section>
      )}
      {actionError && <Alert kind="error">{actionError}</Alert>}
      <section className="card card-wide">
        <h2>{t('Fristen')}</h2>
        {open.length === 0 ? (
          <p>
            {canEdit
              ? t('Noch keine Pflichten. Übernimm einen Vorschlag oder lege eine eigene an.')
              : t('Noch keine Pflichten.')}
          </p>
        ) : (
          <ul className="item-list obligation-list">{open.map(row)}</ul>
        )}
      </section>
      {(elections.length > 0 || data.registered) && (
        <section className="card card-wide">
          <h2>{t('Nach einer Vorstandswahl')}</h2>
          {elections.length > 0 ? (
            <ul className="item-list obligation-list">{elections.map(row)}</ul>
          ) : (
            <p className="small">
              {t(
                'Der Verein ist laut Impressum im Register eingetragen. Wird ein Protokoll mit einer Wahl in ein Amt freigegeben, das den Verein vertritt, legt HUBIplan die Aufgabe „Vorstandsänderung beim Registergericht anmelden“ an, mit Frist 14 Tage nach der Versammlung. Übernimm den Vorschlag unten, um Frist und Zuständigkeit zu ändern oder die Aufgabe abzuschalten.',
              )}
            </p>
          )}
        </section>
      )}
      {canEdit && data.suggestions.length > 0 && (
        <section className="card card-wide">
          <h2>{t('Vorschläge')}</h2>
          <p className="muted small">
            {t(
              'Übliche Pflichten eingetragener, gemeinnütziger Vereine in Deutschland. Frist, Wiederholung und Zuständigkeit passt du beim Übernehmen an. Die Hinweise ersetzen keine Rechts- oder Steuerberatung.',
            )}
          </p>
          <ul className="item-list">
            {data.suggestions.map((s) => (
              <li key={s.key} className="item-row">
                <div className="item-row-info">
                  <strong>{s.title}</strong>
                  <div className="muted small">
                    {s.trigger === 'election'
                      ? t('nach jeder Vorstandswahl')
                      : intervalLabel(s.interval_months)}
                  </div>
                  <p className="small obligation-note">{s.note}</p>
                </div>
                <div className="button-row">
                  <button
                    type="button"
                    className="button"
                    onClick={() => {
                      setAdopting(s)
                      setEditing('new')
                    }}
                  >
                    {t('Übernehmen')}
                  </button>
                </div>
              </li>
            ))}
          </ul>
        </section>
      )}
      {closed.length > 0 && (
        <section className="card card-wide">
          <h2>{t('Abgeschlossen')}</h2>
          <ul className="item-list obligation-list">{closed.map(row)}</ul>
        </section>
      )}
    </div>
  )
}
