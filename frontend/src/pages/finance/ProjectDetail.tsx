import { useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { euro, financeApi } from '../../api/finance.ts'
import type { ProjectEvaluation, ProjectEvent } from '../../api/finance.ts'
import { PERM } from '../../api/orgs.ts'
import { errorMessage, formatDate, formatDateTime, useLoad } from '../../components/forms.ts'
import { Alert, Field, LoadError, Loading } from '../../components/ui.tsx'
import { useActiveOrg } from '../../org/OrgContext.tsx'
import { berlin } from '../../components/calendar/time.ts'
import { t } from '../../i18n/index.ts'
import { ProjectForm } from './ProjectForm.tsx'
import { period } from './projectsHelpers.ts'
import { AssignBookings } from './AssignBookings.tsx'
import { ProjectResult } from './ProjectResult.tsx'

export function ProjectDetail() {
  const org = useActiveOrg()
  const canEdit = org.permissions.includes(PERM.financeEdit)
  const navigate = useNavigate()
  const id = Number(useParams().id)
  const ev = useLoad(() => financeApi.projectEvaluation(org.id, id), [org.id, id])
  const series = useLoad(() => financeApi.series(org.id), [org.id])
  const project = useLoad(
    () => financeApi.projects(org.id).then((all) => all.find((p) => p.id === id) ?? null),
    [org.id, id],
  )
  const [editing, setEditing] = useState(false)
  const [error, setError] = useState<string | null>(null)

  if (ev.error) return <Alert kind="error">{ev.error}</Alert>
  if (!ev.data) return <Loading />
  const d = ev.data
  const reload = () => {
    void ev.reload()
    void project.reload()
  }

  // Ohne Rückfrage: Löschen lässt sich rückgängig machen (UX-Audit VW-23)
  async function remove() {
    try {
      await financeApi.deleteProject(org.id, d.id)
      navigate('/finanzen/veranstaltungen')
    } catch (err) {
      setError(errorMessage(err))
    }
  }

  async function unassign(bookingId: number) {
    try {
      await financeApi.unassignBookings(org.id, d.id, [bookingId])
      reload()
    } catch (err) {
      setError(errorMessage(err))
    }
  }

  const tm = d.totals
  return (
    <div className="stack">
      <p className="small">
        <Link to="/finanzen/veranstaltungen">{t('← alle Veranstaltungen')}</Link>
      </p>
      <div className="card card-wide">
        <div className="card-head">
          <div>
            <h2>{d.name}</h2>
            <p className="muted small">
              {[
                period(d.starts_on, d.ends_on),
                d.status_label,
                d.department_name,
                d.series_name ? t('Reihe {series_name}', { series_name: d.series_name }) : null,
              ]
                .filter(Boolean)
                .join(' · ')}
            </p>
          </div>
          <div className="button-row push-right">
            <a
              className="button button-ghost"
              href={financeApi.projectReportUrl(org.id, d.id, 'pdf')}
              target="_blank"
              rel="noreferrer"
            >
              PDF
            </a>
            <a
              className="button button-ghost"
              href={financeApi.projectReportUrl(org.id, d.id, 'xlsx')}
            >
              {t('Excel')}
            </a>
            {canEdit && (
              <button
                type="button"
                className="button button-ghost"
                onClick={() => setEditing(true)}
              >
                {t('Bearbeiten')}
              </button>
            )}
            {canEdit && (
              <button type="button" className="button button-danger" onClick={() => void remove()}>
                {t('Löschen')}
              </button>
            )}
          </div>
        </div>
        {d.description && <p>{d.description}</p>}
        {error && <Alert kind="error">{error}</Alert>}
      </div>

      {editing && project.data && (
        <ProjectForm
          project={project.data}
          series={series.data ?? []}
          onSeriesAdded={() => void series.reload()}
          onSaved={(_p, done) => {
            if (done) setEditing(false)
            reload()
          }}
          onClose={() => {
            setEditing(false)
            reload()
          }}
        />
      )}

      <div className="tiles tiles-figures">
        <div className="card tile">
          <h2>{t('Einnahmen')}</h2>
          <p className="amount-big amount-in">{euro(tm.income)}</p>
          {d.plan && (
            <span className="muted small">{t('Plan {x}', { x: euro(d.plan.income) })}</span>
          )}
        </div>
        <div className="card tile">
          <h2>{t('Ausgaben')}</h2>
          <p className="amount-big amount-out">{euro(tm.expense)}</p>
          {d.plan && (
            <span className="muted small">{t('Plan {x}', { x: euro(d.plan.expense) })}</span>
          )}
        </div>
        <div className="card tile">
          <h2>{Number(tm.result) < 0 ? t('Fehlbetrag') : t('Überschuss')}</h2>
          <p className={`amount-big ${Number(tm.result) < 0 ? 'amount-out' : 'amount-in'}`}>
            {euro(tm.result)}
          </p>
          <span className="muted small">
            {d.booking_count} {t('Buchungen')}
            {d.plan && <> · {t('Plan {x}', { x: euro(d.plan.result) })}</>}
          </span>
        </div>
      </div>
      {d.open_invoices.count > 0 && (
        <Alert kind="info">
          {t('Noch offen:')}{' '}
          {d.open_invoices.count === 1
            ? t('eine Rechnung')
            : t('{count} Rechnungen', { count: d.open_invoices.count })}{' '}
          {t('über {x}. Sie zählen erst mit dem Zahlungseingang.', {
            x: euro(d.open_invoices.outstanding),
          })}{' '}
          <Link to={`/finanzen/rechnungen?veranstaltung=${d.id}`}>{t('Ansehen')}</Link>
        </Alert>
      )}

      <div className="card card-wide">
        <h2>{t('Nach Kategorie')}</h2>
        {d.categories.length === 0 ? (
          <p className="muted">{t('Noch keine Einnahmen oder Ausgaben zugeordnet.')}</p>
        ) : (
          <table className="table">
            <thead>
              <tr>
                <th>{t('Kategorie')}</th>
                <th className="num">{t('Einnahmen')}</th>
                <th className="num">{t('Ausgaben')}</th>
                <th className="num">{t('Saldo')}</th>
              </tr>
            </thead>
            <tbody>
              {d.categories.map((c) => (
                <tr key={c.id ?? 0}>
                  <td>{c.name}</td>
                  <td className="num">{euro(c.income)}</td>
                  <td className="num">{euro(c.expense)}</td>
                  <td className="num">
                    <ProjectResult value={c.result} />
                  </td>
                </tr>
              ))}
            </tbody>
            <tfoot>
              <tr>
                <th>{t('Summe')}</th>
                <th className="num">{euro(tm.income)}</th>
                <th className="num">{euro(tm.expense)}</th>
                <th className="num">
                  <ProjectResult value={tm.result} />
                </th>
              </tr>
            </tfoot>
          </table>
        )}
      </div>

      {d.tax_areas_enabled && d.tax_areas.length > 0 && (
        <div className="card card-wide">
          <h2>{t('Nach steuerlichem Bereich')}</h2>
          <table className="table">
            <thead>
              <tr>
                <th>{t('Bereich')}</th>
                <th className="num">{t('Einnahmen')}</th>
                <th className="num">{t('Ausgaben')}</th>
                <th className="num">{t('Ergebnis')}</th>
              </tr>
            </thead>
            <tbody>
              {d.tax_areas.map((a) => (
                <tr key={a.area || 'ohne'}>
                  <td>{a.label}</td>
                  <td className="num">{euro(a.income)}</td>
                  <td className="num">{euro(a.expense)}</td>
                  <td className="num">
                    <ProjectResult value={a.result} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <div className="card card-wide">
        <div className="card-head">
          <h2>{t('Buchungen')}</h2>
          <Link
            className="small push-right"
            to={`/finanzen/kassenbuch?veranstaltung=${d.id}&jahr=alle`}
          >
            {t('im Kassenbuch ansehen')}
          </Link>
        </div>
        {d.bookings.length === 0 ? (
          <p className="muted small">
            {t(
              'Noch keine Buchung. Im Kassenbuch kannst du bei jeder Einnahme oder Ausgabe die Veranstaltung wählen, oder du ordnest hier vorhandene Buchungen zu.',
            )}
          </p>
        ) : (
          <div className="table-scroll">
            <table className="table">
              <thead>
                <tr>
                  <th>{t('Nr.')}</th>
                  <th>{t('Datum')}</th>
                  <th>{t('Text')}</th>
                  <th>{t('Kategorie')}</th>
                  <th className="num">{t('Betrag')}</th>
                  {canEdit && <th />}
                </tr>
              </thead>
              <tbody>
                {d.bookings.map((b) => (
                  <tr key={b.id}>
                    <td>{b.display_number}</td>
                    <td>{formatDate(b.date)}</td>
                    <td>
                      {b.text}
                      <div className="muted small">
                        {[
                          b.reference,
                          b.account_name,
                          b.receipt_count
                            ? t('📎 {receipt_count}', { receipt_count: b.receipt_count })
                            : '',
                        ]
                          .filter(Boolean)
                          .join(' · ')}
                      </div>
                    </td>
                    <td>{b.category_name}</td>
                    <td className={`num ${b.kind === 'expense' ? 'amount-out' : 'amount-in'}`}>
                      {euro(b.kind === 'expense' ? -Number(b.amount) : Number(b.amount))}
                    </td>
                    {canEdit && (
                      <td>
                        <button
                          type="button"
                          className="link-button"
                          onClick={() => void unassign(b.id)}
                        >
                          {t('Zuordnung lösen')}
                        </button>
                      </td>
                    )}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {canEdit && <AssignBookings project={d} onDone={reload} />}
      </div>

      <EventsCard project={d} canEdit={canEdit} onChange={(data) => ev.setData(data)} />
    </div>
  )
}

function eventWhen(e: ProjectEvent): string {
  const when = e.all_day ? formatDate(e.starts_at) : formatDateTime(e.starts_at)
  return e.is_series ? t('{when} (Serie)', { when }) : when
}

/** Termine im Kalender, die zur Veranstaltung gehören. */
function EventsCard({
  project,
  canEdit,
  onChange,
}: {
  project: ProjectEvaluation
  canEdit: boolean
  onChange: (data: ProjectEvaluation) => void
}) {
  const org = useActiveOrg()
  const calendar = org.modules.includes('events')
  const [open, setOpen] = useState(false)
  const [suche, setSuche] = useState('')
  const [error, setError] = useState<string | null>(null)
  const candidates = useLoad(
    () => (open ? financeApi.eventCandidates(org.id, project.id, suche) : Promise.resolve(null)),
    [org.id, project.id, open, suche],
  )
  if (!calendar && project.events.length === 0) return null

  async function change(data: { events?: number[]; unlink?: number[] }) {
    try {
      onChange(await financeApi.linkEvents(org.id, project.id, data))
      void candidates.reload()
    } catch (err) {
      setError(errorMessage(err))
    }
  }

  const free = (candidates.data ?? []).filter((e) => !e.linked)
  return (
    <div className="card card-wide">
      <h2>{t('Termine im Kalender')}</h2>
      {project.events.length === 0 ? (
        <p className="muted small">
          {t(
            'Kein Termin verknüpft. Die Veranstaltung erscheint nur im Kalender, wenn du Termine verknüpfst.',
          )}
        </p>
      ) : (
        <ul className="plain-list">
          {project.events.map((e) => (
            <li key={e.id}>
              <Link to={`/termine?termin=${e.id}&datum=${berlin(e.starts_at).date}`}>
                {e.title}
              </Link>{' '}
              <span className="muted small">
                {eventWhen(e)}
                {e.is_cancelled ? t(' · abgesagt') : ''}
              </span>
              {canEdit && (
                <button
                  type="button"
                  className="link-button"
                  onClick={() => void change({ unlink: [e.id] })}
                >
                  {t('lösen')}
                </button>
              )}
            </li>
          ))}
        </ul>
      )}
      {error && <Alert kind="error">{error}</Alert>}
      {canEdit && calendar && !open && (
        <div className="button-row">
          <button type="button" className="button button-ghost" onClick={() => setOpen(true)}>
            {t('Termin verknüpfen')}
          </button>
        </div>
      )}
      {canEdit && open && (
        <div className="subcard">
          <h3>{t('Termin verknüpfen')}</h3>
          <Field
            label={t('Suche')}
            type="search"
            value={suche}
            placeholder={t('Titel des Termins (ohne Suche: Termine rund um den Zeitraum)')}
            onChange={(e) => setSuche(e.target.value)}
          />
          {candidates.error ? (
            <LoadError message={candidates.error} onRetry={() => void candidates.reload()} />
          ) : !candidates.data ? (
            <Loading />
          ) : free.length === 0 ? (
            <p className="muted small">
              {t('Keine passenden Termine. Neue Termine legst du hier an:')}{' '}
              <Link to="/termine">{t('Kalender')}</Link>.
            </p>
          ) : (
            <ul className="plain-list">
              {free.map((e) => (
                <li key={e.id}>
                  {e.title} <span className="muted small">{eventWhen(e)}</span>{' '}
                  <button
                    type="button"
                    className="link-button"
                    onClick={() => void change({ events: [e.id] })}
                  >
                    {t('verknüpfen')}
                  </button>
                </li>
              ))}
            </ul>
          )}
          <div className="button-row">
            <button type="button" className="button button-ghost" onClick={() => setOpen(false)}>
              {t('Schließen')}
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
