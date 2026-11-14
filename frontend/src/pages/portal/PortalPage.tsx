// Mitgliederbereich nach Aufgaben: Ausweis, Rechnungen, Rundschreiben, eigene Daten.
import { PortalCirculars } from './PortalCirculars.tsx'
import { PortalTodos } from './PortalTodos.tsx'
import { PortalBookings } from './PortalBookings.tsx'
import { PortalHelpers } from './PortalHelpers.tsx'
import { PortalMeetings } from './PortalMeetings.tsx'
import { PortalMeetingLive } from './PortalMeetingLive.tsx'
import { PortalCompany } from './PortalCompany.tsx'
import { PortalCancellation } from './PortalCancellation.tsx'
import { OwnMusic } from '../music/OwnMusic.tsx'
import { useEffect, useState } from 'react'
import type { FormEvent, ReactNode } from 'react'
import {
  Link,
  Navigate,
  Route,
  Routes,
  useLocation,
  useParams,
  useSearchParams,
} from 'react-router-dom'
import { FIELD_LABELS, portalApi } from '../../api/portal.ts'
import type { ChangeRequest, PortalDetail, PortalEntry } from '../../api/portal.ts'
import {
  formatDate,
  formatDateTime,
  formatMemberDate,
  useForm,
  useLoad,
} from '../../components/forms.ts'
import { Alert, Field, SelectField, Loading } from '../../components/ui.tsx'
import { TitleField } from '../../components/TitleField.tsx'
import { confirmDiscard, useChangesGuard } from '../../components/leaveGuard.ts'
import { GENDERS } from '../../api/members.ts'
import { OwnCardPanel } from '../../components/CardPanel.tsx'
import { useOrg } from '../../org/OrgContext.tsx'
import { PortalInvoices, PortalMandate } from '../billing/MyInvoices.tsx'
import { PortalEntries } from './PortalEntries.tsx'
import { PortalResults } from './PortalResults.tsx'
import { useTerms } from '../../org/terms.ts'
import { NotFoundPage } from '../NoticePages.tsx'
import { t } from '../../i18n/index.ts'
import { portalSections } from './sections.ts'

const FIELDS = [
  'last_name',
  'first_name',
  'birth_date',
  'gender',
  'title',
  'email',
  'phone',
  'street',
  'postal_code',
  'city',
  'country',
] as const
type FieldKey = (typeof FIELDS)[number]
/** Organisationen haben keinen Vornamen, kein Geburtsdatum, kein Geschlecht und keinen Titel. */
const ORG_FIELDS = FIELDS.filter(
  (f) => !['first_name', 'birth_date', 'gender', 'title'].includes(f),
)

function fieldsFor(d: PortalDetail): readonly FieldKey[] {
  return d.kind === 'organization' ? ORG_FIELDS : FIELDS
}

function fieldLabel(key: FieldKey, organization: boolean): string {
  return organization && key === 'last_name' ? t('Name der Organisation') : FIELD_LABELS[key]
}

/** Zweck der eigenen Angaben für Browser und Hilfsmittel (WCAG 1.3.5). */
const AUTOCOMPLETE: Record<FieldKey, string> = {
  last_name: 'family-name',
  first_name: 'given-name',
  birth_date: 'bday',
  gender: 'sex',
  title: 'honorific-prefix',
  email: 'email',
  phone: 'tel',
  street: 'street-address',
  postal_code: 'postal-code',
  city: 'address-level2',
  country: 'country-name',
}

function currentValues(d: PortalDetail): Record<FieldKey, string> {
  return {
    last_name: d.last_name,
    first_name: d.first_name,
    birth_date: d.birth_date ?? '',
    gender: d.gender ?? '',
    title: d.title ?? '',
    email: d.contact?.email ?? '',
    phone: d.contact?.phone ?? '',
    street: d.contact?.street ?? '',
    postal_code: d.contact?.postal_code ?? '',
    city: d.contact?.city ?? '',
    country: d.contact?.country ?? '',
  }
}

/** QR-Code der Leitung (V7): passenden Zugang für den Verein wählen, dann anmelden. */
function MeetingScanRoute({ meeting }: { meeting: string }) {
  const { activePortal, portal, select } = useOrg()
  const [params] = useSearchParams()
  const club = Number(params.get('v'))
  const code = params.get('c') ?? ''
  const fitting =
    portal.find((a) => a.club_id === club && a.member_kind !== 'organization') ??
    portal.find((a) => a.club_id === club)
  useEffect(() => {
    if (fitting && activePortal?.id !== fitting.id) select(`p:${fitting.id}`)
  }, [fitting, activePortal?.id, select])
  if (!fitting)
    return (
      <Alert kind="error">
        {t('Für diesen Verein hast du keinen Mitgliederzugang.')}{' '}
        <Link to="/mein-bereich">{t('Zu meinem Bereich')}</Link>
      </Alert>
    )
  if (activePortal?.id !== fitting.id)
    return <p role="status">{t('Mitgliederzugang wird geöffnet …')}</p>
  return (
    <PortalSection title={t('Versammlung')}>
      <PortalMeetingLive accessId={fitting.id} meetingId={Number(meeting)} code={code} />
    </PortalSection>
  )
}

function MeetingLiveRoute({ accessId }: { accessId: number }) {
  const { meeting } = useParams()
  return <PortalMeetingLive accessId={accessId} meetingId={Number(meeting)} />
}

export function PortalPage() {
  const { pathname } = useLocation()
  const scan = /\/versammlungen\/da\/(\d+)\/?$/.exec(pathname)
  if (scan) return <MeetingScanRoute meeting={scan[1]} />
  return <PortalRoutes />
}

function PortalRoutes() {
  const { activePortal, portal, select } = useOrg()
  const [params] = useSearchParams()
  const target = params.get('zugang')
  const knownTarget = portal.some((access) => String(access.id) === target)
  useEffect(() => {
    if (target && knownTarget && String(activePortal?.id) !== target) select(`p:${target}`)
  }, [target, knownTarget, activePortal?.id, select])
  if (target && !knownTarget)
    return (
      <Alert kind="error">
        {t('Dieser Mitgliederzugang steht deinem Konto nicht zur Verfügung.')}{' '}
        <Link to="/mein-bereich">{t('Zu meinem Bereich')}</Link>
      </Alert>
    )
  if (target && String(activePortal?.id) !== target)
    return <p role="status">{t('Mitgliederzugang wird geöffnet …')}</p>
  if (!activePortal) return <Alert kind="info">{t('Kein Mitgliederbereich ausgewählt.')}</Alert>
  return (
    <Routes>
      <Route
        path="aufgaben"
        element={
          <PortalSection title={t('Aufgaben')}>
            <PortalTodos key={activePortal.id} accessId={activePortal.id} />
          </PortalSection>
        }
      />
      <Route
        path="belegung"
        element={
          <PortalSection title={t('Belegung')}>
            <PortalBookings key={activePortal.id} accessId={activePortal.id} />
          </PortalSection>
        }
      />
      <Route
        path="helferdienste"
        element={
          <PortalSection title={t('Helferdienste')}>
            <PortalHelpers key={activePortal.id} accessId={activePortal.id} />
          </PortalSection>
        }
      />
      <Route
        path="versammlungen"
        element={
          <PortalSection title={t('Versammlungen')}>
            <PortalMeetings key={activePortal.id} accessId={activePortal.id} />
          </PortalSection>
        }
      />
      <Route
        path="versammlungen/live/:meeting"
        element={
          <PortalSection title={t('Versammlung')}>
            <MeetingLiveRoute key={activePortal.id} accessId={activePortal.id} />
          </PortalSection>
        }
      />
      {activePortal.company && (
        <Route
          path="firma"
          element={
            <PortalSection title={t('Mitarbeiter')}>
              <PortalCompany key={activePortal.id} accessId={activePortal.id} />
            </PortalSection>
          }
        />
      )}
      <Route index element={<PortalOverview key={activePortal.id} entry={activePortal} />} />
      <Route
        path="ausweis"
        element={
          <PortalSection title={t('Mein Ausweis')}>
            <OwnCardPanel
              key={activePortal.id}
              accessId={activePortal.id}
              empty={
                <Alert kind="info">
                  {t(
                    'Für dich gibt es zurzeit keinen Mitgliedsausweis, zum Beispiel weil deine Mitgliedschaft beendet ist.',
                  )}
                </Alert>
              }
            />
          </PortalSection>
        }
      />
      <Route
        path="rechnungen"
        element={
          <PortalSection title={t('Rechnungen und Zahlung')}>
            <PortalInvoices
              key={activePortal.id}
              accessId={activePortal.id}
              empty={<p className="muted">{t('Für dich liegen keine Rechnungen vor.')}</p>}
            />
            <PortalMandate key={`m${activePortal.id}`} accessId={activePortal.id} />
          </PortalSection>
        }
      />
      <Route
        path="rundschreiben"
        element={
          <PortalSection title={t('Mitteilungen')}>
            <PortalCirculars key={activePortal.id} accessId={activePortal.id} />
          </PortalSection>
        }
      />
      <Route
        path="wettbewerbe"
        element={
          <PortalSection title={t('Wettbewerbe')}>
            {activePortal.entries_enabled && (
              <>
                <h2>{t('Wofür bin ich gemeldet?')}</h2>
                <PortalEntries key={activePortal.id} accessId={activePortal.id} />
              </>
            )}
            {activePortal.competitions_enabled && (
              <>
                <h2>{t('Meine Ergebnisse')}</h2>
                <PortalResults key={`r${activePortal.id}`} accessId={activePortal.id} />
              </>
            )}
          </PortalSection>
        }
      />
      {/* Frühere Adressen (Menüprüfung 2, N-09) */}
      <Route path="gemeldet" element={<Navigate to="/mein-bereich/wettbewerbe" replace />} />
      <Route path="ergebnisse" element={<Navigate to="/mein-bereich/wettbewerbe" replace />} />
      <Route
        path="musik"
        element={
          <PortalSection title={t('Musik')}>
            <OwnMusic key={activePortal.id} accessId={activePortal.id} />
          </PortalSection>
        }
      />
      <Route path="daten" element={<PortalData key={activePortal.id} entry={activePortal} />} />
      <Route path="*" element={<NotFoundPage />} />
    </Routes>
  )
}

function PortalSection({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section>
      <p className="small">
        <Link to="/mein-bereich">{t('← Mein Bereich')}</Link>
      </p>
      <h1>{title}</h1>
      <div className="stack">{children}</div>
    </section>
  )
}

/** Aufgaben im Mitgliederbereich als Kacheln (Startseite und Übersicht). */
export function PortalTasks({
  entry,
  skip = [],
  limit,
  prefer = [],
}: {
  entry: PortalEntry
  skip?: string[]
  /** höchstens so viele Kacheln (Startseite, W-07) */
  limit?: number
  /** diese Kacheln zuerst (Startseite S-04: das Wichtigste vorn) */
  prefer?: string[]
}) {
  const rank = (to: string) => {
    const i = prefer.indexOf(to)
    return i < 0 ? prefer.length : i
  }
  const tasks = portalSections(entry)
    .flatMap((s) => (s.tile ? [{ to: s.to, title: s.tile.title, text: s.tile.text }] : []))
    .map((tile, i) => ({ tile, i }))
    .sort((a, b) => rank(a.tile.to) - rank(b.tile.to) || a.i - b.i)
    .map(({ tile }) => tile)
  return (
    <ul className="task-tiles">
      {tasks
        .filter((tmx) => !skip.includes(tmx.to))
        .slice(0, limit)
        .map((tmx) => (
          <li key={tmx.to}>
            <Link to={tmx.to} className="task-tile">
              <strong>{tmx.title}</strong>
              <span className="muted small">{tmx.text}</span>
            </Link>
          </li>
        ))}
    </ul>
  )
}

function PortalOverview({ entry }: { entry: PortalEntry }) {
  const { data, error } = useLoad(() => portalApi.portal(entry.id), [entry.id])
  const pending = data?.change_requests.find((c) => c.status === 'pending')
  return (
    <section>
      <h1>{t('Mein Bereich')}</h1>
      <p className="muted">
        {entry.club_display_name ?? entry.club_name}
        {data?.status === 'former' && t(' · ehemaliges Mitglied')}
      </p>
      <PortalTasks entry={entry} />
      <OwnMusic accessId={entry.id} />
      {pending && (
        <Alert kind="info">
          {t('Deine Datenänderung vom {x} wird noch geprüft.', {
            x: formatDateTime(pending.created_at),
          })}{' '}
          <Link to="/mein-bereich/daten">{t('Ansehen')}</Link>
        </Alert>
      )}
      {error && <Alert kind="error">{error}</Alert>}
      {data && <ClubContact club={data.club} />}
    </section>
  )
}

function PortalData({ entry }: { entry: PortalEntry }) {
  const tm = useTerms()
  const { data, error, reload } = useLoad(() => portalApi.portal(entry.id), [entry.id])
  const [editing, setEditing] = useState(false)
  const [notice, setNotice] = useState<string | null>(null)
  if (error) return <Alert kind="error">{error}</Alert>
  if (!data) return <Loading />

  const values = currentValues(data)
  const fields = fieldsFor(data)
  const organization = data.kind === 'organization'
  const pending = data.change_requests.find((c) => c.status === 'pending')

  return (
    <PortalSection title={t('Meine Daten')}>
      <div className="card card-wide">
        <div className="card-head">
          <h2>{organization ? data.display_name : `${data.first_name} ${data.last_name}`}</h2>
          {!editing && (
            <button
              type="button"
              className="button button-ghost push-right"
              onClick={() => setEditing(true)}
            >
              {t('Daten ändern')}
            </button>
          )}
        </div>
        <p className="muted small">
          {data.club.name}
          {data.status === 'former' && t(' · ehemaliges Mitglied')}
          {' · '}
          {data.member_type ?? t('ohne Mitgliedsart')}
          {data.entry_date &&
            t(' · Mitglied seit {x}', {
              x: formatMemberDate(data.entry_date, entry.date_precision),
            })}
          {data.club_number &&
            t(' · Mitgliedsnummer {club_number}', { club_number: data.club_number })}
          {data.departments.length > 0 && t(' · {x}', { x: data.departments.join(', ') })}
        </p>
        {editing ? (
          <ChangeForm
            accessId={entry.id}
            initial={values}
            fields={fields}
            organization={organization}
            needsApproval={data.contact_changes_need_approval}
            hasPending={!!pending}
            onDone={async (text) => {
              setEditing(false)
              setNotice(text)
              await reload()
            }}
            onCancel={() => setEditing(false)}
          />
        ) : (
          <dl className="facts">
            {fields.map((key) => (
              <div key={key}>
                <dt>{fieldLabel(key, organization)}</dt>
                <dd>{key === 'birth_date' ? formatDate(values[key]) : values[key] || '–'}</dd>
              </div>
            ))}
          </dl>
        )}
        {notice && !editing && <Alert kind="success">{notice}</Alert>}
        {pending && !editing && (
          <Alert kind="info">
            {t('Deine Datenänderung vom {x} wartet auf {e_akk}.', {
              x: formatDateTime(pending.created_at),
              e_akk: tm.e_akk,
            })}
          </Alert>
        )}
      </div>

      {data.change_requests.length > 0 && (
        <div className="card card-wide">
          <h2>{t('Meine Datenänderungen')}</h2>
          <ul className="audit-list">
            {data.change_requests.map((c) => (
              <ChangeRequestItem key={c.id} request={c} />
            ))}
          </ul>
        </div>
      )}
      {data.cancellation && (
        <PortalCancellation accessId={entry.id} info={data.cancellation} onChanged={reload} />
      )}
    </PortalSection>
  )
}

function ClubContact({ club }: { club: PortalDetail['club'] }) {
  const tm = useTerms()
  return (
    <div className="card card-wide">
      <h2>
        {t('Kontakt')} {tm.e_zum}
      </h2>
      <p>
        {club.name}
        <br />
        {club.address_extra && (
          <>
            {club.address_extra}
            <br />
          </>
        )}
        {club.street && (
          <>
            {club.street}
            <br />
          </>
        )}
        {club.postal_code} {club.city}
      </p>
      {club.email && (
        <p>
          <a href={`mailto:${club.email}`}>{club.email}</a>
        </p>
      )}
      {club.phone && <p>{club.phone}</p>}
      {club.website && (
        <p>
          <a href={club.website} target="_blank" rel="noreferrer">
            {club.website}
          </a>
        </p>
      )}
    </div>
  )
}

const DIRECT: FieldKey[] = ['email', 'phone', 'street', 'postal_code', 'city', 'country']

function ChangeForm({
  accessId,
  initial,
  fields,
  organization,
  needsApproval,
  hasPending,
  onDone,
  onCancel,
}: {
  accessId: number
  initial: Record<FieldKey, string>
  fields: readonly FieldKey[]
  organization: boolean
  needsApproval: boolean
  hasPending: boolean
  onDone: (text: string) => void
  onCancel: () => void
}) {
  const tm = useTerms()
  const form = useForm({ ...initial, message: '' })
  const { values: v, errors, set } = form
  // Noch nicht gesendete Änderungen nicht unbemerkt verlieren (UX-Audit 31.10. W01)
  const [sent, setSent] = useState(false)
  const { dirty } = useChangesGuard(v, !sent)

  async function send(e: FormEvent) {
    e.preventDefault()
    const changed: Record<string, string> = {}
    for (const key of fields) if (v[key] !== initial[key]) changed[key] = v[key]
    if (Object.keys(changed).length === 0) {
      form.setMessage({ kind: 'error', text: t('Du hast nichts geändert.') })
      return
    }
    const result = (await form.submit(() =>
      portalApi.requestChange(accessId, { ...changed, message: v.message }),
    )) as Awaited<ReturnType<typeof portalApi.requestChange>> | undefined
    if (!result) return
    setSent(true)
    const applied = Object.keys(result.applied).length > 0
    onDone(
      applied && result.request
        ? t('Kontaktdaten gespeichert. Die übrigen Änderungen bestätigt {e_nom}.', {
            e_nom: tm.e_nom,
          })
        : applied
          ? t('Gespeichert.')
          : t('Meldung gesendet. {e_Nom} prüft und übernimmt sie.', { e_Nom: tm.e_Nom }),
    )
  }

  return (
    <form onSubmit={send}>
      <p className="muted small">
        {t('Ändere die Angaben, die nicht mehr stimmen.')}{' '}
        {needsApproval
          ? t('{e_Nom} prüft alle Änderungen und übernimmt sie.', { e_Nom: tm.e_Nom })
          : t(
              'Kontaktdaten (E-Mail, Telefon, Anschrift) gelten sofort. Änderungen an Name, Geburtsdatum oder Geschlecht prüft {e_nom}.',
              { e_nom: tm.e_nom },
            )}
      </p>
      {hasPending && (
        <Alert kind="info">
          {t('Es wartet noch eine frühere Meldung auf {e_akk}.', { e_akk: tm.e_akk })}{' '}
          {needsApproval
            ? t('Bis dahin sind die Felder gesperrt.')
            : t(
                'Bis dahin sind Name, Geburtsdatum und Geschlecht gesperrt; Kontaktdaten kannst du weiter ändern.',
              )}
        </Alert>
      )}
      <div className="grid-3">
        {fields.map((key) =>
          key === 'gender' ? (
            <SelectField
              key={key}
              label={FIELD_LABELS[key]}
              value={v[key]}
              error={errors[key]}
              disabled={hasPending && (needsApproval || !DIRECT.includes(key))}
              hint={!needsApproval && !DIRECT.includes(key) ? t('mit Bestätigung') : undefined}
              autoComplete={AUTOCOMPLETE[key]}
              onChange={(e) => set(key, e.target.value)}
            >
              {GENDERS.map((g) => (
                <option key={g.value} value={g.value}>
                  {g.label}
                </option>
              ))}
            </SelectField>
          ) : key === 'title' ? (
            <TitleField
              key={key}
              value={v[key]}
              error={errors[key]}
              disabled={hasPending && (needsApproval || !DIRECT.includes(key))}
              hint={!needsApproval && !DIRECT.includes(key) ? t('mit Bestätigung') : undefined}
              onChange={(value) => set(key, value)}
            />
          ) : (
            <Field
              key={key}
              label={fieldLabel(key, organization)}
              type={
                key === 'birth_date'
                  ? 'date'
                  : key === 'email'
                    ? 'email'
                    : key === 'phone'
                      ? 'tel'
                      : 'text'
              }
              autoComplete={AUTOCOMPLETE[key]}
              value={v[key]}
              error={errors[key]}
              disabled={hasPending && (needsApproval || !DIRECT.includes(key))}
              hint={!needsApproval && !DIRECT.includes(key) ? t('mit Bestätigung') : undefined}
              onChange={(e) => set(key, e.target.value)}
            />
          ),
        )}
      </div>
      <Field
        label={t('Nachricht an {e_akk} (optional)', { e_akk: tm.e_akk })}
        value={v.message}
        maxLength={500}
        onChange={(e) => set('message', e.target.value)}
      />
      {form.message?.kind === 'error' && <Alert kind="error">{form.message.text}</Alert>}
      <div className="button-row">
        <button type="submit" className="button button-primary" disabled={form.busy}>
          {needsApproval ? t('Änderung zur Prüfung senden') : t('Speichern')}
        </button>
        <button
          type="button"
          className="button button-ghost"
          onClick={() => void confirmDiscard(dirty).then((ok) => ok && onCancel())}
        >
          {t('Abbrechen')}
        </button>
      </div>
    </form>
  )
}

export function ChangeRequestItem({ request: c }: { request: ChangeRequest }) {
  const tm = useTerms()
  return (
    <li>
      <strong>{c.status_label}</strong>{' '}
      <span className="muted small">
        {t('gemeldet')} {formatDateTime(c.created_at)}
      </span>
      <ChangeTable request={c} />
      {c.response && (
        <p className="small">
          {t('Antwort {e_gen}:', { e_gen: tm.e_gen })} {c.response}
        </p>
      )}
    </li>
  )
}

export function ChangeTable({ request: c }: { request: ChangeRequest }) {
  const show = (key: string, value: string | null | undefined) =>
    key === 'birth_date' ? formatDate(value ?? null) : value || '–'
  return (
    <table className="table change-table">
      <tbody>
        {Object.entries(c.data).map(([key, value]) => (
          <tr key={key}>
            <td>{FIELD_LABELS[key] ?? key}</td>
            <td>
              <span className="change-old">{show(key, c.previous[key])}</span> →{' '}
              <strong>{show(key, value)}</strong>
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}
