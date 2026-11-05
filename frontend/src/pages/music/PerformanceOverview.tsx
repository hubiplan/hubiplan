import { useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../../api/client.ts'
import { todayIso } from '../../api/members.ts'
import { formatDateTime, useLoad } from '../../components/forms.ts'
import { Alert, Field } from '../../components/ui.tsx'
import { t } from '../../i18n/index.ts'
import { useActiveOrg } from '../../org/OrgContext.tsx'
import { MusicEmptyState, MusicHeader } from './MusicLayout.tsx'

type Issue = {
  code: string
  count: number
  area: 'staffing' | 'program' | 'settlement'
  level: string
}
type Row = {
  id: number
  title: string
  starts_at: string
  ends_at: string
  location: string
  status: string
  required: number
  accepted: number
  pending: number
  issues: Issue[]
}
type Page = {
  count: number
  next: string | null
  previous: string | null
  results: Row[]
  finance_visible: boolean
}

function day(offset: number) {
  const date = new Date(`${todayIso()}T12:00:00Z`)
  date.setUTCDate(date.getUTCDate() + offset)
  return date.toISOString().slice(0, 10)
}

function issueText(issue: Issue) {
  const n = issue.count
  switch (issue.code) {
    case 'positions':
      return t('Sollbesetzung festlegen')
    case 'missing_players':
      return t('Fehlende Zusagen für Sollplätze: {n}', { n })
    case 'pending':
      return t('Ausstehende Rückmeldungen: {n}', { n })
    case 'conflicts':
      return t('Einteilungen mit Konflikten: {n}', { n })
    case 'program':
      return t('Programm oder Stimmenangaben vervollständigen')
    case 'missing_scores':
      return t('Fehlende Notenexemplare: {n}', { n })
    case 'score_players':
      return t('Unbesetzte Stimmen in Programmstücken: {n}', { n })
    case 'agreement':
      return t('Auftrittsvereinbarung erfassen')
    case 'invoice':
      return t('Veranstalterrechnung fertigstellen')
    case 'overdue':
      return t('Überfälligen Zahlungseingang prüfen')
    case 'claim_drafts':
      return t('Vergütungsentwürfe prüfen: {n}', { n })
    case 'payouts':
      return t('Noch auszuzahlende Vergütungen: {n}', { n })
    default:
      return t('Weitere Hinweise prüfen')
  }
}

export function PerformanceOverview() {
  const org = useActiveOrg()
  const [range, setRange] = useState(() => ({ start: day(-90), end: day(180) }))
  const [filter, setFilter] = useState(range)
  const [page, setPage] = useState(1)
  const load = useLoad(
    () =>
      api.get<Page>(
        `/api/orgs/${org.id}/music/performances/overview/?start=${filter.start}&end=${filter.end}&page=${page}`,
      ),
    [org.id, filter.start, filter.end, page],
  )
  const labels: Record<string, string> = {
    critical: t('Handlungsbedarf'),
    attention: t('Noch offen'),
    ready: t('Vorbereitet'),
    cancelled: t('Abgesagt'),
  }
  const href = (row: Row, area: Issue['area']) =>
    `/musik?${area === 'staffing' ? 'besetzung' : area === 'program' ? 'programm' : 'abrechnung'}=${row.id}`
  return (
    <section className="stack music-page">
      <MusicHeader
        title={t('Auftrittsübersicht')}
        description={t(
          'Besetzung, Rückmeldungen, Konflikte, Noten und Abrechnung auf einen Blick. Hinweise führen direkt zum nächsten Arbeitsschritt.',
        )}
      />
      <form
        className="card music-toolbar"
        onSubmit={(event) => {
          event.preventDefault()
          setPage(1)
          setFilter({ ...range })
        }}
      >
        <Field
          label={t('Zeitraum von')}
          type="date"
          required
          value={range.start}
          onChange={(event) => setRange({ ...range, start: event.target.value })}
        />
        <Field
          label={t('Zeitraum bis')}
          type="date"
          required
          min={range.start}
          value={range.end}
          onChange={(event) => setRange({ ...range, end: event.target.value })}
        />
        <button className="button button-primary">{t('Übersicht aktualisieren')}</button>
      </form>
      <p className="muted small">
        {t(
          'Die Ampeln zeigen den aktuellen Vorbereitungsstand, keine automatische Zusage. Ungeplante Angaben bleiben offen. Finanzhinweise erscheinen nur mit Kassenleserecht.',
        )}
      </p>
      {load.error && <Alert kind="error">{load.error}</Alert>}
      {!load.data && !load.error && <p>{t('Lädt …')}</p>}
      {load.data?.count === 0 && (
        <MusicEmptyState>{t('Keine sichtbaren Auftritte im gewählten Zeitraum.')}</MusicEmptyState>
      )}
      <div className="music-overview-grid">
        {load.data?.results.map((row) => (
          <article className="card stack music-overview-card" key={row.id}>
            <div className="music-toolbar">
              <h2>{row.title}</h2>
              <span className={`music-readiness music-readiness-${row.status}`}>
                {labels[row.status] ?? t('Noch offen')}
              </span>
            </div>
            <p>
              {formatDateTime(row.starts_at)}
              {row.location && <> · {row.location}</>}
            </p>
            <p className="muted">
              {t(
                'Besetzung: {accepted} Zusagen bei {required} Sollplätzen; {pending} Antworten offen.',
                { accepted: row.accepted, required: row.required, pending: row.pending },
              )}
            </p>
            {row.issues.length > 0 ? (
              <ul className="music-readiness-issues">
                {row.issues.map((issue) => (
                  <li key={issue.code}>
                    <Link to={href(row, issue.area)}>{issueText(issue)}</Link>
                  </li>
                ))}
              </ul>
            ) : (
              row.status !== 'cancelled' && (
                <p>{t('Nach den sichtbaren Angaben ist der Auftritt vorbereitet.')}</p>
              )
            )}
            <div className="music-actions">
              <Link to={href(row, 'staffing')}>{t('Besetzung planen')}</Link>
              <Link to={href(row, 'program')}>{t('Musikalisches Programm')}</Link>
              {load.data?.finance_visible && (
                <Link to={href(row, 'settlement')}>{t('Auftrittsabrechnung')}</Link>
              )}
            </div>
          </article>
        ))}
      </div>
      {load.data && load.data.count > 0 && (
        <div className="music-toolbar">
          <button
            className="button button-ghost"
            disabled={!load.data.previous}
            onClick={() => setPage(page - 1)}
          >
            {t('Zurück')}
          </button>
          <span>{t('Seite {page} · {count} Auftritte', { page, count: load.data.count })}</span>
          <button
            className="button button-ghost"
            disabled={!load.data.next}
            onClick={() => setPage(page + 1)}
          >
            {t('Weiter')}
          </button>
        </div>
      )}
    </section>
  )
}
