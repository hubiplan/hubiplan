// Mitglieder › Anträge: eingegangene Online-Anträge prüfen, zustimmen, aufnehmen
// (konzepte/online-beitrittsformular.md B1–B5).
import { useState } from 'react'
import { Link, Route, Routes, useNavigate, useParams } from 'react-router-dom'
import { admissionApi } from '../../api/admission.ts'
import type { ApplicationDetail, ApplicationRow } from '../../api/admission.ts'
import { PERM } from '../../api/orgs.ts'
import { confirmDialog } from '../../components/dialog.ts'
import { errorMessage, formatDate, formatDateTime, useLoad } from '../../components/forms.ts'
import { PageHeader } from '../../components/PageHeader.tsx'
import { Alert, Checkbox, EmptyState, Field, LoadError, Loading } from '../../components/ui.tsx'
import { useActiveOrg } from '../../org/OrgContext.tsx'
import { t } from '../../i18n/index.ts'

const FILTERS = [
  { value: 'offen', label: () => t('offen') },
  { value: 'unsigned', label: () => t('Unterschrift fehlt') },
  { value: 'query', label: () => t('Rückfrage') },
  { value: 'accepted', label: () => t('aufgenommen') },
  { value: 'rejected', label: () => t('abgelehnt') },
  { value: 'withdrawn', label: () => t('zurückgezogen') },
  { value: 'alle', label: () => t('alle') },
]

function eventLabel(kind: string): string {
  const labels: Record<string, string> = {
    confirmed: t('per E-Mail bestätigt'),
    signed: t('unterschrieben'),
    paper_signed: t('unterschriebenes Papier eingegangen'),
    query: t('Rückfrage gestellt'),
    resumed: t('Rückfrage erledigt'),
    corrected: t('Angaben korrigiert'),
    approvals_reset: t('Zustimmungen zurückgesetzt'),
    approved: t('zugestimmt'),
    objected: t('Einwand erhoben'),
    accepted: t('aufgenommen'),
    rejected: t('abgelehnt'),
    withdrawn: t('zurückgezogen'),
  }
  return labels[kind] ?? kind
}

export function ApplicationsPage() {
  return (
    <section>
      <PageHeader />
      <Routes>
        <Route index element={<ApplicationList />} />
        <Route path=":id" element={<ApplicationView />} />
      </Routes>
    </section>
  )
}

function ApplicationList() {
  const org = useActiveOrg()
  const [status, setStatus] = useState('offen')
  const [chosen, setChosen] = useState<number[]>([])
  const [busy, setBusy] = useState(false)
  const [notice, setNotice] = useState<{ kind: 'success' | 'error'; text: string } | null>(null)
  const loaded = useLoad(
    () => admissionApi.list(org.id, status).then((d) => ({ status, d })),
    [org.id, status],
  )
  const data = loaded.data?.status === status ? loaded.data.d : null
  const canEdit = org.permissions.includes(PERM.membersEdit)
  const ready = (r: ApplicationRow) =>
    r.status === 'open' && r.approvals_met !== false && !r.disputed
  const bulk = canEdit && data?.rule.mode !== 'assembly'

  async function acceptChosen() {
    const ok = await confirmDialog({
      title: t('Anträge aufnehmen?'),
      message: t(
        '{n} Antragsteller werden Mitglied, mit dem eingestellten Eintrittsdatum. Sie bekommen die Begrüßungsmail.',
        { n: chosen.length },
      ),
      confirmLabel: t('Aufnehmen'),
      danger: false,
    })
    if (!ok) return
    setBusy(true)
    setNotice(null)
    try {
      const res = await admissionApi.bulkAccept(org.id, chosen, '', false)
      const failed = res.failed.map((f) => `${f.number}: ${f.detail}`).join(' · ')
      setNotice(
        failed
          ? {
              kind: 'error',
              text: t('Aufgenommen: {n}. Nicht möglich: {x}', {
                n: res.accepted.length,
                x: failed,
              }),
            }
          : { kind: 'success', text: t('Aufgenommen: {n}.', { n: res.accepted.length }) },
      )
      setChosen([])
      void loaded.reload()
    } catch (err) {
      setNotice({ kind: 'error', text: errorMessage(err) })
    } finally {
      setBusy(false)
    }
  }

  return (
    <>
      <div className="card card-wide filters">
        <select aria-label={t('Status')} value={status} onChange={(e) => setStatus(e.target.value)}>
          {FILTERS.map((f) => (
            <option key={f.value} value={f.value}>
              {f.label()}
              {data?.counts[f.value] ? ` (${data.counts[f.value]})` : ''}
            </option>
          ))}
        </select>
        {data?.rule_text && <span className="muted small">{data.rule_text}</span>}
        {canEdit && (
          <Link className="button button-ghost push-right" to="/mitglieder/einrichtung/antrag">
            {t('Formular einrichten')}
          </Link>
        )}
      </div>
      {loaded.error && (
        <LoadError
          message={t('Die Anträge konnten nicht geladen werden. {error}', { error: loaded.error })}
          onRetry={() => void loaded.reload()}
        />
      )}
      {notice && <Alert kind={notice.kind}>{notice.text}</Alert>}
      {!data ? (
        !loaded.error && <Loading />
      ) : !data.enabled && data.results.length === 0 ? (
        <EmptyState title={t('Noch kein Online-Antrag')}>
          {t(
            'Unter Einrichtung › Online-Antrag stellst du das Formular ein. Den Link kannst du auf der Webseite, in Mails oder als QR-Code verteilen.',
          )}
        </EmptyState>
      ) : data.results.length === 0 ? (
        <div className="card empty-state">
          <p>{t('Keine Anträge.')}</p>
        </div>
      ) : (
        <div className="card card-wide">
          <table className="table">
            <thead>
              <tr>
                {bulk && <th aria-label={t('Auswahl')} />}
                <th>{t('Antrag')}</th>
                <th>{t('Name')}</th>
                <th>{t('Mitgliedsart')}</th>
                <th>{t('Eingang')}</th>
                <th>{t('Status')}</th>
              </tr>
            </thead>
            <tbody>
              {data.results.map((r) => (
                <tr key={r.id}>
                  {bulk && (
                    <td>
                      {ready(r) && (
                        <input
                          type="checkbox"
                          aria-label={t('{x} auswählen', { x: r.name })}
                          checked={chosen.includes(r.id)}
                          onChange={(e) =>
                            setChosen((c) =>
                              e.target.checked ? [...c, r.id] : c.filter((x) => x !== r.id),
                            )
                          }
                        />
                      )}
                    </td>
                  )}
                  <td>
                    <Link to={`/mitglieder/antraege/${r.id}`}>{r.number}</Link>
                    {r.source === 'kiosk' && (
                      <span className="muted small"> · {t('am Stand')}</span>
                    )}
                  </td>
                  <td>
                    {r.name}
                    {r.minor && <span className="muted small"> · {t('minderjährig')}</span>}
                    {r.unit && <span className="muted small"> · {r.unit}</span>}
                  </td>
                  <td>{r.member_type || '–'}</td>
                  <td>{formatDate(r.created_at.slice(0, 10))}</td>
                  <td>
                    {r.status_label}
                    {r.disputed && <span className="field-error small"> · {t('Einwand')}</span>}
                    {r.missing.length > 0 && (
                      <span className="muted small">
                        {' '}
                        · {t('fehlt: {x}', { x: r.missing.join(', ') })}
                      </span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {bulk && chosen.length > 0 && (
            <div className="button-row">
              <button
                type="button"
                className="button button-primary"
                disabled={busy}
                onClick={() => void acceptChosen()}
              >
                {t('{n} aufnehmen', { n: chosen.length })}
              </button>
            </div>
          )}
        </div>
      )}
    </>
  )
}

function ApplicationView() {
  const org = useActiveOrg()
  const id = Number(useParams().id)
  const { data, error, reload, setData } = useLoad(() => admissionApi.get(org.id, id), [org.id, id])
  if (error) return <LoadError message={error} onRetry={() => void reload()} />
  if (!data) return <Loading />
  return <Detail key={data.id} app={data} onChange={setData} />
}

function Detail({
  app,
  onChange,
}: {
  app: ApplicationDetail
  onChange: (a: ApplicationDetail) => void
}) {
  const org = useActiveOrg()
  const navigate = useNavigate()
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState('')
  const [note, setNote] = useState('')
  const [person, setPerson] = useState<number | null>(null)
  const [entry, setEntry] = useState(app.entry_date ?? '')
  const [number, setNumber] = useState('')
  const [welcome, setWelcome] = useState(true)
  const [invite, setInvite] = useState(false)
  const [question, setQuestion] = useState('')
  const [rejectMail, setRejectMail] = useState(false)
  const [mode, setMode] = useState<'' | 'accept' | 'reject' | 'ask' | 'object'>('')
  const open = ['unsigned', 'open', 'query'].includes(app.status)

  async function act(action: string, body: Record<string, unknown>, done: string) {
    setBusy(true)
    setError(null)
    setNotice('')
    try {
      const next = await admissionApi.action(org.id, app.id, action, body)
      onChange(next)
      setNotice(done)
      setMode('')
      if (action === 'accept' && next.membership_id) navigate(`/mitglieder/${next.membership_id}`)
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setBusy(false)
    }
  }

  const here = app.matches.persons.filter((p) => p.here && !p.former)
  return (
    <div className="stack">
      <div className="card card-wide stack-sm">
        <div className="card-head">
          <h2>
            {t('Antrag {number}', { number: app.number })} · {app.name}
          </h2>
          <span className="muted small push-right">
            {app.status_label} · {formatDateTime(app.created_at)}
            {app.source === 'kiosk' && ` · ${t('am Stand')}`}
          </span>
        </div>
        <ul className="small">
          {app.summary.map((line) => (
            <li key={line}>{line}</li>
          ))}
        </ul>
        {app.guardians.length > 0 && (
          <p className="small">
            {t('Erziehungsberechtigte: {x}', {
              x: app.guardians.map((g) => `${g.first_name} ${g.last_name} (${g.email})`).join(', '),
            })}
          </p>
        )}
        {app.mandate && (
          <p className="small">
            {t('SEPA-Mandat: {holder}, {iban}', {
              holder: app.mandate.holder,
              iban: app.mandate.iban,
            })}
          </p>
        )}
        {app.consents.length > 0 && (
          <ul className="small">
            {app.consents.map((c) => (
              <li key={c.key}>
                ✓ {c.label}
                {c.version ? ` (${t('Fassung {x}', { x: c.version })})` : ''}
              </li>
            ))}
          </ul>
        )}
        <p className="small">
          {app.signed
            ? t('Unterschrieben am {x}.', {
                x: app.signed_at ? formatDateTime(app.signed_at) : '–',
              })
            : t('Nicht unterschrieben.')}
        </p>
        <div className="button-row">
          <a
            className="button button-ghost"
            href={admissionApi.pdfUrl(org.id, app.id)}
            target="_blank"
            rel="noreferrer"
          >
            {t('Antrag als PDF')}
          </a>
          <Link className="button button-ghost" to="/mitglieder/antraege">
            {t('Zur Liste')}
          </Link>
        </div>
      </div>

      {open && app.matches.persons.length > 0 && (
        <div className="card card-wide stack-sm">
          <h2>{t('Mögliche Treffer')}</h2>
          {here.length > 0 && (
            <Alert kind="info">
              {t('Diese Person ist schon Mitglied. Bitte prüfen, ob der Antrag doppelt ist.')}
            </Alert>
          )}
          <ul className="item-list">
            {app.matches.persons.map((p) => (
              <li key={p.person_id} className="item-row">
                <div className="item-row-info">
                  <strong>{p.name}</strong>
                  {p.birth_date && ` · ${formatDate(p.birth_date)}`}
                  <span className="muted small">
                    {p.here && !p.former && ` · ${t('aktives Mitglied hier')}`}
                    {p.former && ` · ${t('früheres Mitglied')}`}
                    {p.active_elsewhere && ` · ${t('aktiv in {x}', { x: p.active_elsewhere })}`}
                  </span>
                  {p.active_elsewhere && (
                    <p className="small muted">
                      {t('Bei einem Wechsel besser eine Wechselanfrage stellen:')}{' '}
                      <Link to="/mitglieder/anfragen">{t('Änderungen und Wechsel')}</Link>
                    </p>
                  )}
                </div>
                <div className="button-row">
                  {p.member_id && (
                    <Link className="button button-ghost" to={`/mitglieder/${p.member_id}`}>
                      {t('Akte')}
                    </Link>
                  )}
                  {app.may_decide && !(p.here && !p.former) && (
                    <Checkbox
                      label={t('Diese Person aufnehmen')}
                      checked={person === p.person_id}
                      onChange={(on) => setPerson(on ? p.person_id : null)}
                    />
                  )}
                </div>
              </li>
            ))}
          </ul>
        </div>
      )}

      {open && app.rule.mode === 'rule' && (
        <div className="card card-wide stack-sm">
          <h2>{t('Zustimmungen')}</h2>
          <p className="muted small">{app.rule_text}</p>
          {app.approvals.length === 0 ? (
            <p className="muted">{t('Noch keine Zustimmung.')}</p>
          ) : (
            <ul className="small">
              {app.approvals.map((a) => (
                <li key={a.id}>
                  {a.decision === 'approve' ? '✓' : '✗'} {a.user_name}
                  {a.for_unit
                    ? ` · ${t('für die Untereinheit')}`
                    : a.roles
                      ? ` (${a.roles})`
                      : ''}{' '}
                  · {formatDateTime(a.created_at)}
                  {a.note && ` · ${a.note}`}
                </li>
              ))}
            </ul>
          )}
          {app.missing.length > 0 && (
            <p className="small">{t('Es fehlt noch: {x}', { x: app.missing.join(', ') })}</p>
          )}
          {app.approvals_met && !app.disputed && (
            <Alert kind="success">{t('Die Regel ist erfüllt.')}</Alert>
          )}
          {app.disputed && (
            <Alert kind="error">
              {t('Es gibt einen Einwand. Aufnehmen geht erst, wenn er zurückgenommen ist.')}
            </Alert>
          )}
          {app.status === 'open' && (
            <div className="button-row">
              {app.may_approve && (
                <>
                  <button
                    type="button"
                    className="button button-primary"
                    disabled={busy || app.own_decision === 'approve'}
                    onClick={() =>
                      void act(
                        'approve',
                        { decision: 'approve' },
                        t('Deine Zustimmung ist gespeichert.'),
                      )
                    }
                  >
                    {app.own_decision === 'approve' ? t('Du hast zugestimmt') : t('Zustimmen')}
                  </button>
                  <button
                    type="button"
                    className="button button-ghost"
                    disabled={busy}
                    onClick={() => setMode('object')}
                  >
                    {app.own_decision === 'reject' ? t('Einwand ändern') : t('Einwand erheben')}
                  </button>
                </>
              )}
              {app.rule.unit && app.unit_id && app.may_decide && (
                <button
                  type="button"
                  className="button button-ghost"
                  disabled={busy}
                  onClick={() =>
                    void act(
                      'approve',
                      { decision: 'approve', for_unit: true },
                      t('Die Zustimmung der Untereinheit ist eingetragen.'),
                    )
                  }
                >
                  {t('Zustimmung von {x} eintragen', { x: app.unit })}
                </button>
              )}
            </div>
          )}
          {mode === 'object' && (
            <div className="stack-sm">
              <Field
                label={t('Begründung')}
                value={note}
                maxLength={500}
                onChange={(e) => setNote(e.target.value)}
              />
              <div className="button-row">
                <button
                  type="button"
                  className="button button-danger"
                  disabled={busy}
                  onClick={() =>
                    void act(
                      'approve',
                      { decision: 'reject', note },
                      t('Dein Einwand ist gespeichert.'),
                    )
                  }
                >
                  {t('Einwand speichern')}
                </button>
                <button type="button" className="button button-ghost" onClick={() => setMode('')}>
                  {t('Abbrechen')}
                </button>
              </div>
            </div>
          )}
        </div>
      )}

      {open && app.may_decide && (
        <div className="card card-wide stack-sm">
          <h2>{t('Entscheidung')}</h2>
          {app.rule.mode === 'assembly' && (
            <p className="muted small">
              {t('Die Versammlung beschließt. Trage das Ergebnis mit Datum der Versammlung ein.')}
            </p>
          )}
          <div className="button-row">
            {app.status === 'unsigned' && (
              <button
                type="button"
                className="button"
                disabled={busy}
                onClick={() =>
                  void act('signed', {}, t('Vermerkt: Das unterschriebene Papier ist da.'))
                }
              >
                {t('Unterschriebenes Papier ist da')}
              </button>
            )}
            {app.status === 'query' && (
              <button
                type="button"
                className="button"
                disabled={busy}
                onClick={() => void act('resume', {}, t('Die Rückfrage ist erledigt.'))}
              >
                {t('Rückfrage erledigt')}
              </button>
            )}
            {app.status !== 'unsigned' && (
              <button
                type="button"
                className="button button-primary"
                onClick={() => setMode('accept')}
              >
                {t('Aufnehmen …')}
              </button>
            )}
            {app.status !== 'query' && (
              <button type="button" className="button button-ghost" onClick={() => setMode('ask')}>
                {t('Rückfrage …')}
              </button>
            )}
            <button type="button" className="button button-ghost" onClick={() => setMode('reject')}>
              {t('Ablehnen …')}
            </button>
          </div>
          {mode === 'accept' && (
            <div className="stack-sm">
              <Field
                label={
                  app.rule.mode === 'assembly'
                    ? t('Eintritt (Tag des Beschlusses oder später)')
                    : t('Eintritt')
                }
                type="date"
                value={entry}
                onChange={(e) => setEntry(e.target.value)}
              />
              <Field
                label={t('Mitgliedsnummer (leer = automatisch oder ohne)')}
                value={number}
                maxLength={30}
                onChange={(e) => setNumber(e.target.value)}
              />
              <Field
                label={
                  app.rule.mode === 'assembly'
                    ? t('Beschluss der Versammlung (Datum und Ergebnis)')
                    : t('Vermerk (freiwillig)')
                }
                value={note}
                maxLength={500}
                onChange={(e) => setNote(e.target.value)}
              />
              {person && (
                <p className="small">
                  {t(
                    'Aufgenommen wird die gewählte vorhandene Person; ihre Daten werden nicht überschrieben.',
                  )}
                </p>
              )}
              <Checkbox
                label={t('Begrüßungsmail schicken')}
                checked={welcome}
                onChange={setWelcome}
              />
              {app.portal_available && (
                <Checkbox
                  label={t('Zum Mitgliederbereich einladen')}
                  checked={invite}
                  onChange={setInvite}
                />
              )}
              <div className="button-row">
                <button
                  type="button"
                  className="button button-primary"
                  disabled={busy}
                  onClick={() =>
                    void act(
                      'accept',
                      {
                        entry_date: entry || null,
                        club_number: number,
                        note,
                        welcome,
                        invite,
                        person,
                      },
                      t('Aufgenommen.'),
                    )
                  }
                >
                  {t('Jetzt aufnehmen')}
                </button>
                <button type="button" className="button button-ghost" onClick={() => setMode('')}>
                  {t('Abbrechen')}
                </button>
              </div>
            </div>
          )}
          {mode === 'ask' && (
            <div className="stack-sm">
              <div className="field">
                <label className="field-label" htmlFor="antrag-frage">
                  {t('Deine Frage (geht per E-Mail, Antworten kommen an dich)')}
                </label>
                <textarea
                  id="antrag-frage"
                  rows={4}
                  maxLength={2000}
                  value={question}
                  onChange={(e) => setQuestion(e.target.value)}
                />
              </div>
              <div className="button-row">
                <button
                  type="button"
                  className="button button-primary"
                  disabled={busy}
                  onClick={() =>
                    void act('ask', { text: question }, t('Die Rückfrage ist verschickt.'))
                  }
                >
                  {t('Rückfrage senden')}
                </button>
                <button type="button" className="button button-ghost" onClick={() => setMode('')}>
                  {t('Abbrechen')}
                </button>
              </div>
            </div>
          )}
          {mode === 'reject' && (
            <div className="stack-sm">
              <Field
                label={t('Vermerk (nur intern)')}
                value={note}
                maxLength={500}
                onChange={(e) => setNote(e.target.value)}
              />
              <Checkbox
                label={t('Absage per E-Mail schicken (Text aus der Einrichtung)')}
                checked={rejectMail}
                onChange={setRejectMail}
              />
              <div className="button-row">
                <button
                  type="button"
                  className="button button-danger"
                  disabled={busy}
                  onClick={() =>
                    void act(
                      'reject',
                      { note, send_mail: rejectMail },
                      t('Der Antrag ist abgelehnt.'),
                    )
                  }
                >
                  {t('Ablehnen')}
                </button>
                <button type="button" className="button button-ghost" onClick={() => setMode('')}>
                  {t('Abbrechen')}
                </button>
              </div>
            </div>
          )}
        </div>
      )}

      {!open && (app.decided_at || app.membership_id) && (
        <div className="card card-wide">
          <p>
            {app.decided_at &&
              t('Entschieden am {x} von {y}.', {
                x: formatDateTime(app.decided_at),
                y: app.decided_by || '–',
              })}{' '}
            {app.decision_note}
          </p>
          {app.data_purged && (
            <p className="muted">
              {t(
                'Die Angaben dieses Antrags wurden nach der Aufbewahrungsfrist entfernt. Der Antrag bleibt als PDF erhalten.',
              )}
            </p>
          )}
          {app.membership_id && (
            <Link to={`/mitglieder/${app.membership_id}`}>{t('Zur Mitgliederakte')}</Link>
          )}
        </div>
      )}

      {notice && <Alert kind="success">{notice}</Alert>}
      {error && <Alert kind="error">{error}</Alert>}

      <div className="card card-wide">
        <h2>{t('Verlauf')}</h2>
        <ul className="small">
          {app.events.map((e, i) => (
            <li key={i}>
              {formatDateTime(e.created_at)} · {eventLabel(e.kind)}
              {e.user && ` · ${e.user}`}
              {e.note && ` · ${e.note}`}
            </li>
          ))}
        </ul>
      </div>
    </div>
  )
}
