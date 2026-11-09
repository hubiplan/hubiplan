import { useState } from 'react'
import { GuestAccessPanel } from './GuestAccessPanel.tsx'
import { Link, useSearchParams } from 'react-router-dom'
import { api, newRequestKey } from '../../api/client.ts'
import { errorMessage, formatDateTime, useLoad } from '../../components/forms.ts'
import { confirmLeave } from '../../components/leaveGuard.ts'
import { confirmDialog } from '../../components/dialog.ts'
import { Alert } from '../../components/ui.tsx'
import { useActiveOrg } from '../../org/OrgContext.tsx'
import { LeadersPanel } from './LeadersPanel.tsx'
import { t } from '../../i18n/index.ts'
import { ScoreForm } from './ScoresPage.tsx'
import { RehearsalProgramEditor } from './RehearsalProgramEditor.tsx'
import { AvailabilityHint } from './AvailabilityPage.tsx'
import { PageHeader } from '../../components/PageHeader.tsx'
import { MusicHeader, MusicEmptyState, MusicStatus } from './MusicLayout.tsx'

type Row = { id: number; [key: string]: string | number | boolean | null }
type Loan = {
  id: number
  part: number
  musician: number
  quantity: number
  returned: number
  due_on: string
  overdue: boolean
  title: string
  instrument: string
  register: string
  returns: { quantity: number; created_at: string }[]
}
type Occurrence = {
  rehearsal: number
  event: number
  title: string
  original_start: string
  starts_at: string
  cancelled: boolean
  focus: string
  items: { arrangement: number; title: string; focus: string }[]
  overridden: boolean
  members: {
    invitation: number
    name: string
    status: string
    guest?: boolean
    availability?: string[]
  }[]
}

export function PracticePage() {
  const [query] = useSearchParams()
  const org = useActiveOrg(),
    base = `/api/orgs/${org.id}/music/`
  const load = useLoad(async () => {
    const [
      rehearsals,
      items,
      invitations,
      musicians,
      arrangements,
      parts,
      loans,
      overview,
      events,
    ] = await Promise.all([
      api.get<Row[]>(base + 'rehearsals/'),
      api.get<Row[]>(base + 'rehearsal-items/'),
      api.get<Row[]>(base + 'rehearsal-invitations/'),
      api.get<Row[]>(base + 'musicians/'),
      api.get<Row[]>(base + 'arrangements/'),
      api.get<Row[]>(base + 'parts/'),
      api.get<Loan[]>(base + 'loans/'),
      api.get<Occurrence[]>(base + 'practice/'),
      api.get<Row[]>(base + 'rehearsals/choices/'),
    ])
    return {
      rehearsals,
      items,
      invitations,
      musicians,
      arrangements,
      parts,
      loans,
      overview,
      events,
    }
  }, [org.id])
  const [tab, setTab] = useState(query.has('notenausgabe') ? 'loans' : 'overview'),
    [selected, setSelected] = useState<Row | 'new' | null>(null),
    [program, setProgram] = useState<Occurrence | null>(null),
    [error, setError] = useState(''),
    [key, setKey] = useState(newRequestKey)
  const [guest, setGuest] = useState<{ invitation: number; name: string; original: string } | null>(
    null,
  )
  if (load.error)
    return (
      <>
        <PageHeader />
        <Alert kind="error">{load.error}</Alert>
      </>
    )
  if (!load.data)
    return (
      <>
        <PageHeader />
        <p>{t('Lädt …')}</p>
      </>
    )
  const d = load.data,
    canEdit = org.permissions.includes('music.edit'),
    opts = (rows: Row[], field: string): [string, string][] =>
      rows.map((r) => [String(r.id), String(r[field])])
  const fields = {
    rehearsals: [
      { key: 'event', label: t('Termin oder Terminserie'), options: opts(d.events, 'title') },
      { key: 'focus', label: t('Probenschwerpunkt'), type: 'textarea', optional: true },
      { key: 'remind_days', label: t('Erinnerung Tage vorher (0 = aus)'), type: 'number' },
    ],
    items: [
      { key: 'rehearsal', label: t('Probe'), options: opts(d.rehearsals, 'title') },
      { key: 'arrangement', label: t('Arrangement'), options: opts(d.arrangements, 'name') },
      { key: 'focus', label: t('Probenschwerpunkt'), optional: true },
    ],
    invitations: [
      { key: 'rehearsal', label: t('Probe'), options: opts(d.rehearsals, 'title') },
      { key: 'musician', label: t('Musiker'), options: opts(d.musicians, 'display_name') },
      { key: 'active', label: t('Aktiv'), type: 'checkbox' },
    ],
    loans: [
      {
        key: 'part',
        label: t('Einzelstimme'),
        options: d.parts.map(
          (p) =>
            [
              String(p.id),
              `${d.arrangements.find((a) => a.id === p.arrangement)?.name} · ${p.instrument} ${p.register} · ${t('Freie Exemplare')}: ${Number(p.copies) - d.loans.filter((l) => l.part === p.id).reduce((sum, l) => sum + l.quantity - l.returned, 0)}`,
            ] as [string, string],
        ),
      },
      {
        key: 'musician',
        label: t('Musiker'),
        options: opts(
          d.musicians.filter((m) => m.active),
          'display_name',
        ),
      },
      { key: 'quantity', label: t('Anzahl'), type: 'number' },
      { key: 'due_on', label: t('Rückgabe bis'), type: 'date' },
    ],
  }
  const names = {
    overview: t('Nächste Proben'),
    rehearsals: t('Probenplanung'),
    items: t('Probenstücke'),
    invitations: t('Probeneinteilung'),
    loans: t('Notenausgabe'),
  }
  const rows = (
    tab === 'overview' ? [] : d[tab as 'rehearsals' | 'items' | 'invitations' | 'loans']
  ).filter(
    (row) =>
      tab !== 'loans' || !query.has('notenausgabe') || String(row.id) === query.get('notenausgabe'),
  )
  return (
    <section className="stack music-page">
      {query.has('notenausgabe') && (
        <Link to="/musik/proben">{t('Alle Notenausgaben anzeigen')}</Link>
      )}
      {guest && (
        <GuestAccessPanel
          key={`${guest.invitation}-${guest.original}`}
          assignment={guest.invitation}
          original={guest.original}
          name={guest.name}
          onClose={() => setGuest(null)}
        />
      )}
      <MusicHeader
        title={t('Proben und Notenausgabe')}
        description={t(
          'Proben vorbereiten, Rückmeldungen verfolgen und ausgegebene Noten im Blick behalten.',
        )}
      />
      <nav className="tabs" aria-label={t('Ansichten')}>
        {Object.entries(names).map(([id, label]) => (
          <button
            className={`tab${id === tab ? ' active' : ''}`}
            aria-current={id === tab ? 'page' : undefined}
            key={id}
            onClick={async () => {
              if (await confirmLeave()) {
                setSelected(null)
                setProgram(null)
                setTab(id)
              }
            }}
          >
            {label}
          </button>
        ))}
      </nav>
      {error && <Alert kind="error">{error}</Alert>}
      <p>
        {t(
          'Proben verwenden Kalendertermine und Terminserien. Programme und Schwerpunkte können je Einzeltermin abweichen. Rückmeldungen gelten für den jeweiligen Einzeltermin.',
        )}
      </p>
      {canEdit && program && tab === 'overview' && (
        <RehearsalProgramEditor
          key={`${program.rehearsal}-${program.original_start}`}
          url={`${base}rehearsals/${program.rehearsal}/program/`}
          originalStart={program.original_start}
          startsAt={program.starts_at}
          title={program.title}
          arrangements={d.arrangements.map((a) => ({ id: a.id, name: String(a.name) }))}
          onClose={() => setProgram(null)}
          onSaved={() => load.reload()}
        />
      )}
      {canEdit && tab !== 'overview' && (
        <button
          className="button button-primary"
          onClick={async () => {
            if (await confirmLeave()) {
              setKey(newRequestKey())
              setSelected('new')
            }
          }}
        >
          {t('Anlegen')}
        </button>
      )}
      {canEdit && selected && tab !== 'overview' && (
        <ScoreForm
          key={`${tab}-${selected === 'new' ? key : selected.id}`}
          initial={selected === 'new' ? undefined : selected}
          fields={fields[tab as keyof typeof fields]}
          onClose={() => setSelected(null)}
          onSave={async (values) => {
            const endpoint =
              tab === 'items'
                ? 'rehearsal-items'
                : tab === 'invitations'
                  ? 'rehearsal-invitations'
                  : tab
            if (tab === 'loans')
              await api.post(base + 'loans/', { action: 'issue', ...values }, key)
            else if (selected === 'new') await api.post(base + endpoint + '/', values)
            else await api.patch(`${base}${endpoint}/${selected.id}/`, values)
            setSelected(null)
            await load.reload()
          }}
        />
      )}
      {!(tab === 'overview' ? d.overview : rows).length && <MusicEmptyState />}
      {tab === 'overview' &&
        d.overview.map((o) => (
          <article className="card stack music-record" key={`${o.rehearsal}-${o.original_start}`}>
            <strong>
              {o.title} · {formatDateTime(o.starts_at)}
            </strong>
            <p>
              {o.focus} {o.cancelled ? t('Abgesagt') : ''}
            </p>
            <p>
              {o.overridden
                ? t('Eigenes Programm für diesen Termin')
                : t('Programm aus der Serienvorlage')}
            </p>
            {o.items.map((item, i) => (
              <p key={i}>
                {item.title} · {item.focus}
              </p>
            ))}
            {canEdit && (
              <button
                className="button button-ghost"
                onClick={async () => {
                  if (await confirmLeave()) setProgram(o)
                }}
              >
                {t('Probenprogramm bearbeiten')}
              </button>
            )}
            <Link to={`/aufgaben?termin=${o.event}`}>{t('Aufgaben für Notenvorbereitung')}</Link>
            <p>
              {t('Fehlende Rückmeldungen')}:{' '}
              {o.members.filter((m) => m.status === 'pending').length}
            </p>
            {o.members.map((m) => (
              <div className="music-row stack" key={m.invitation}>
                <div className="music-actions">
                  <strong>{m.name}</strong>
                  <MusicStatus status={m.status} />
                  {canEdit && m.guest && (
                    <button
                      className="button button-ghost"
                      onClick={() =>
                        setGuest({
                          invitation: m.invitation,
                          name: m.name,
                          original: o.original_start,
                        })
                      }
                    >
                      {t('Gasteinladung')}
                    </button>
                  )}
                  <AvailabilityHint reasons={m.availability} />
                </div>
                {canEdit && !o.cancelled && (
                  <span className="actions">
                    {[
                      ['accepted', t('Zusagen')],
                      ['declined', t('Absagen')],
                    ].map(([status, label]) => (
                      <button
                        key={status}
                        className="button button-ghost"
                        disabled={status === 'accepted' && !!m.availability?.length}
                        onClick={async () => {
                          try {
                            await api.post(base + 'practice/', {
                              invitation: m.invitation,
                              original_start: o.original_start,
                              status,
                            })
                            await load.reload()
                          } catch (e) {
                            setError(errorMessage(e))
                          }
                        }}
                      >
                        {label}
                      </button>
                    ))}
                  </span>
                )}
              </div>
            ))}
          </article>
        ))}
      {rows.map((r) => (
        <article className="card stack music-record" key={r.id}>
          <strong>
            {tab === 'rehearsals'
              ? String((r as Row).title)
              : tab === 'loans'
                ? (r as Loan).title
                : String(d.rehearsals.find((a) => a.id === (r as Row).rehearsal)?.title)}
          </strong>
          {tab === 'rehearsals' && (
            <details>
              <summary>{t('Leitung in der App')}</summary>
              <LeadersPanel
                heading={false}
                base={base}
                target={{ rehearsal: r.id }}
                canEdit={canEdit}
              />
            </details>
          )}
          {tab === 'items' && (
            <p>
              {d.arrangements.find((a) => a.id === (r as Row).arrangement)?.name} ·{' '}
              {(r as Row).focus}
            </p>
          )}
          {tab === 'invitations' && (
            <p>
              {d.musicians.find((m) => m.id === (r as Row).musician)?.display_name} ·{' '}
              {(r as Row).active ? t('Aktiv') : t('Inaktiv')}
            </p>
          )}
          {tab === 'rehearsals' && (
            <>
              <p>{(r as Row).focus}</p>
              <Link to={`/aufgaben?termin=${(r as Row).event}`}>
                {t('Aufgaben für Notenvorbereitung')}
              </Link>
            </>
          )}
          {tab === 'loans' ? (
            <>
              <p>
                {d.musicians.find((m) => m.id === (r as Loan).musician)?.display_name} ·{' '}
                {(r as Loan).instrument} {(r as Loan).register} · {t('Ausgegeben')}:{' '}
                {(r as Loan).quantity} · {t('Zurückgegeben')}: {(r as Loan).returned} ·{' '}
                {t('Rückgabe bis')}: {(r as Loan).due_on}
              </p>
              {(r as Loan).overdue && <Alert kind="error">{t('Rückgabe überfällig')}</Alert>}
              {(r as Loan).returns.map((ret, i) => (
                <p key={i}>
                  {t('Notenrückgabe')}: {ret.quantity} · {formatDateTime(ret.created_at)}
                </p>
              ))}
              {canEdit && (r as Loan).returned < (r as Loan).quantity && (
                <ReturnForm
                  key={`${r.id}-${(r as Loan).returned}`}
                  loan={r as Loan}
                  onSaved={() => load.reload()}
                />
              )}
            </>
          ) : (
            canEdit && (
              <button
                className="button button-ghost"
                onClick={async () => {
                  if (await confirmLeave()) setSelected(r as Row)
                }}
              >
                {t('Bearbeiten')}
              </button>
            )
          )}
          {canEdit && tab === 'items' && (
            <button
              className="button button-ghost"
              onClick={async () => {
                if (!(await confirmLeave()) || !(await confirmDialog(t('Eintrag entfernen?'))))
                  return
                try {
                  await api.del(`${base}rehearsal-items/${r.id}/`)
                  setSelected(null)
                  await load.reload()
                } catch (e) {
                  setError(errorMessage(e))
                }
              }}
            >
              {t('Entfernen')}
            </button>
          )}
        </article>
      ))}
    </section>
  )
}

function ReturnForm({ loan, onSaved }: { loan: Loan; onSaved: () => Promise<unknown> }) {
  const org = useActiveOrg(),
    [key] = useState(newRequestKey)
  return (
    <ScoreForm
      initial={{ id: loan.id, quantity: loan.quantity - loan.returned }}
      fields={[{ key: 'quantity', label: t('Rückgabemenge'), type: 'number' }]}
      onSave={async (values) => {
        await api.post(
          `/api/orgs/${org.id}/music/loans/`,
          { action: 'return', loan: loan.id, quantity: values.quantity },
          key,
        )
        await onSaved()
      }}
    />
  )
}
