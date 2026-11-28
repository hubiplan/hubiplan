import { useRowSort } from '../../components/RowSort.tsx'
import { useEffect, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { helperApi } from '../../api/helpers.ts'
import type { HelperPlan, UnitQuota } from '../../api/helpers.ts'
import { useDetailParam } from '../../components/detailParam.ts'
import { errorMessage, useLoad } from '../../components/forms.ts'
import { locale, t } from '../../i18n/index.ts'
import { PageHeader } from '../../components/PageHeader.tsx'
import './helpers.css'
import { EmptyList } from '../../components/EmptyList.tsx'
import { dayText, statusLabel, timeText } from './helpersHelpers.ts'
import { EventSelect } from './EventSelect.tsx'
import { PlanDetail } from './PlanDetail.tsx'
import { AssignForm } from './AssignForm.tsx'

export function Plans({ base, orgId, canEdit }: { base: string; orgId: number; canEdit: boolean }) {
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
  const sorting = useRowSort(list.data ?? [], {
    title: (p) => p.title,
    event: (p) => p.event_starts_at,
    open: (p) => p.open,
    status: (p) => p.status,
  })
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
  const rows = sorting.rows
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
        !creating && (
          <EmptyList
            title={t('Noch kein Dienstplan.')}
            canAdd={canEdit}
            action={{ label: t('Neuer Dienstplan'), onClick: () => setCreating(true) }}
          >
            {t(
              'Ein Dienstplan sammelt die Dienste eines Festes oder Termins; Mitglieder tragen sich dort ein.',
            )}
          </EmptyList>
        )
      ) : (
        <table className="table">
          <thead>
            <tr>
              {sorting.head('title', t('Dienstplan'))}
              {sorting.head('event', t('Termin'))}
              {sorting.head('open', t('Offene Plätze'))}
              {sorting.head('status', t('Stand'))}
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
          placeholder={t('z. B. Sommerfest')}
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

function DoneCard({ base }: { base: string }) {
  const [year, setYear] = useState(() => new Date().getFullYear())
  const done = useLoad(() => helperApi.done(base, year), [base, year])
  const doneSort = useRowSort(done.data?.people ?? [], {
    name: (p) => p.name,
    shifts: (p) => p.shifts,
    minutes: (p) => p.minutes,
  })
  const people = doneSort.rows
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
              {doneSort.head('name', t('Name'))}
              {doneSort.head('shifts', t('Schichten'))}
              {doneSort.head('minutes', t('Stunden'))}
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
