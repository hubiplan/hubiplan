import { useRowSort } from '../RowSort.tsx'
import { useState } from 'react'
import type { CalendarBase, EventDetail } from '../../api/events.ts'
import { registrationApi } from '../../api/registrations.ts'
import type { Participant, Offer, Registration } from '../../api/registrations.ts'
import { euro } from '../../api/finance.ts'
import { useLoad } from '../forms.ts'
import { Alert, Loading } from '../ui.tsx'
import { useRowSearch } from '../RowSearch.tsx'
import { CancelPanel, SubstitutePanel } from './RegistrationCancel.tsx'
import { answerText, asksHealth, bookingText } from './extras.ts'
import { berlin } from './time.ts'
import { PaidBadge } from './PaidBadge.tsx'
import { CheckInPanel } from './CheckIn.tsx'
import { QualificationPanel } from './AfterEvent.tsx'
import { ScanLinksPanel } from './ScanLinks.tsx'
import { MaterialPanel, PrintLoader } from './Material.tsx'
import { ClubRegistrationCard } from './ClubRegistration.tsx'
import { Modal } from '../Modal.tsx'
import { t, tc } from '../../i18n/index.ts'
import { SetupForm } from './SetupForm.tsx'
import { BoardAddForm } from './BoardAddForm.tsx'
import { MemberRegistrationCard } from './MemberRegistrationCard.tsx'
import { RegistrationCard } from './RegistrationCard.tsx'
import { when } from './registrationHelpers.ts'
import { PriceList } from './PriceList.tsx'

/** Link zum öffentlichen Formular mit „Link kopieren“ (A4) */
function PublicLink({ url }: { url: string }) {
  const [note, setNote] = useState('')
  async function copy() {
    try {
      await navigator.clipboard.writeText(url)
      setNote(t('Link kopiert.'))
    } catch {
      setNote(t('Kopieren ging nicht. Bitte den Link markieren.'))
    }
  }
  return (
    <p className="small">
      {t('Öffentliches Formular:')}{' '}
      <a href={url} target="_blank" rel="noreferrer">
        {url}
      </a>{' '}
      <button type="button" className="button button-ghost small" onClick={() => void copy()}>
        {t('Link kopieren')}
      </button>
      {note && <span className="muted"> {note}</span>}
    </p>
  )
}

export function RegistrationPanel({ base, event }: { base: CalendarBase; event: EventDetail }) {
  const info = event.registration
  if (!info) return null
  if (info.club_register && info.enabled) return <ClubRegistrationCard base={base} event={event} />
  if (info.can_register && info.enabled) return <MemberRegistrationCard base={base} event={event} />
  if (info.can_setup || info.can_view_list)
    return <BoardRegistrationCard base={base} event={event} />
  return null
}

function RegistrationTable({
  rows,
  offer,
  canEdit,
  onCancel,
  onSubstitute,
  ticketsUrl,
}: {
  rows: Registration[]
  offer: Offer
  canEdit: boolean
  ticketsUrl: (reg: Registration) => string
  onCancel: (reg: Registration) => void
  onSubstitute: (reg: Registration, p: Participant) => void
}) {
  const search = useRowSearch(
    rows,
    (r) => [r.number, r.name, r.email ?? '', ...r.participants.map((p) => p.name)].join(' '),
    t('Anmeldungen'),
  )
  const sorting = useRowSort(search.shown, {
    number: (r) => r.number,
    people: (r) => r.participants.filter((p) => p.status === 'active').length,
    total: (r) => Number(r.total),
    paid: (r) => r.paid_state,
  })
  return (
    <>
      {search.field}
      <div className="table-wrap">
        <table className="table">
          <thead>
            <tr>
              {sorting.head('number', t('Anmeldung'))}
              {sorting.head('people', t('Personen'))}
              {sorting.head('total', t('Betrag'))}
              {sorting.head('paid', t('Stand'))}
              <th>
                <span className="sr-only">{t('Aktionen')}</span>
              </th>
            </tr>
          </thead>
          <tbody>
            {sorting.rows.map((reg) => (
              <tr key={reg.id}>
                <td>
                  {reg.number}
                  <div className="muted small">
                    {reg.name}
                    {reg.source_label ? ` · ${reg.source_label}` : ''}
                  </div>
                </td>
                <td>
                  {reg.participants.map((p) => (
                    <div key={p.id}>
                      {p.status === 'cancelled' ? <s>{p.name}</s> : p.name}{' '}
                      <span className="muted small">{p.price_name}</span>
                      {p.bookings?.length ? (
                        <div className="muted small">{bookingText(p.bookings)}</div>
                      ) : null}
                      {answerText(offer, p.answers) && (
                        <div className="muted small">{answerText(offer, p.answers)}</div>
                      )}
                      {p.health && (
                        <div className="muted small">
                          {t('Allergien: {text}', { text: p.health })}
                        </div>
                      )}
                      {p.guardians?.map((g, k) => (
                        <div key={k} className="muted small">
                          {t('Erziehungsberechtigt: {who}', {
                            who: [g.name, g.phone, g.email].filter(Boolean).join(', '),
                          })}
                        </div>
                      ))}
                      {canEdit && reg.status !== 'cancelled' && p.status === 'active' && (
                        <button
                          type="button"
                          className="button button-ghost small"
                          aria-label={t('Ersatzperson für {name}', { name: p.name })}
                          onClick={() => onSubstitute(reg, p)}
                        >
                          {t('Ersatzperson')}
                        </button>
                      )}
                    </div>
                  ))}
                  {reg.bookings?.length ? (
                    <div className="muted small">{bookingText(reg.bookings)}</div>
                  ) : null}
                  {answerText(offer, reg.answers) && (
                    <div className="muted small">{answerText(offer, reg.answers)}</div>
                  )}
                  {reg.note && <div className="muted small">{reg.note}</div>}
                </td>
                <td>
                  {euro(reg.total)}
                  {reg.invoice && <div className="muted small">{reg.invoice.number}</div>}
                  {Number(reg.cancel_fee) > 0 && (
                    <div className="muted small">
                      {t('Stornogebühr {fee}', { fee: euro(reg.cancel_fee) })}
                      {reg.fee_invoice ? ` · ${reg.fee_invoice.number}` : ''}
                    </div>
                  )}
                </td>
                <td>
                  <PaidBadge state={reg.paid_state} />
                  {reg.waitlist_position !== null && (
                    <div className="muted small">
                      {t('Platz {n}', { n: reg.waitlist_position })}
                    </div>
                  )}
                  {reg.moved_up_at && (
                    <div className="muted small">
                      {t('nachgerückt am {when}', { when: when(reg.moved_up_at) })}
                    </div>
                  )}
                </td>
                <td>
                  {reg.has_tickets && (
                    <a
                      className="button button-ghost"
                      href={ticketsUrl(reg)}
                      aria-label={t('Eintrittskarten von {number}', { number: reg.number })}
                    >
                      {t('Eintrittskarten')}
                    </a>
                  )}
                  {canEdit && reg.status !== 'cancelled' && (
                    <button
                      type="button"
                      className="button button-ghost"
                      onClick={() => onCancel(reg)}
                    >
                      {tc('anmeldung', 'Abmelden')}
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  )
}

// --- Mitglied ---

function BoardRegistrationCard({ base, event }: { base: CalendarBase; event: EventDetail }) {
  const { data, error, setData, reload } = useLoad(
    () => registrationApi.board(base, event.id),
    [base, event.id],
  )
  const [editing, setEditing] = useState(false)
  const [adding, setAdding] = useState(false)
  const [cancelling, setCancelling] = useState<Registration | null>(null)
  const [replacing, setReplacing] = useState<{ reg: Registration; p: Participant } | null>(null)
  const [checkIn, setCheckIn] = useState(false)
  const [qualifying, setQualifying] = useState(false)
  const [scanLinks, setScanLinks] = useState(false)
  const [printing, setPrinting] = useState(false)
  const [material, setMaterial] = useState(false)
  if (error) return <Alert kind="error">{error}</Alert>
  if (!data) return <Loading small />
  const offer = data.offer
  if (editing || (!offer && editing))
    return (
      <RegistrationCard title={t('Anmeldung einrichten')}>
        <SetupForm
          base={base}
          event={event}
          data={data}
          onCancel={() => setEditing(false)}
          onSaved={(next) => {
            setData(next)
            setEditing(false)
          }}
        />
      </RegistrationCard>
    )
  if (!offer)
    return data.can_edit ? (
      <RegistrationCard title={t('Anmeldung')}>
        {event.rsvp.enabled ? (
          <p className="muted small">
            {t(
              'Der Termin hat Zu- und Absagen. Für eine verbindliche Anmeldung mit Teilnahmegebühr diese bitte zuerst ausschalten.',
            )}
          </p>
        ) : (
          <>
            <p className="muted small">
              {t(
                'Verbindliche Anmeldung mit Tarifen, Preisstufen (z. B. Early Bird), Platzgrenze, Rechnung und Bestätigungen per E-Mail.',
              )}
            </p>
            <div className="button-row">
              <button type="button" className="button" onClick={() => setEditing(true)}>
                {t('Verbindliche Anmeldung einrichten')}
              </button>
            </div>
          </>
        )}
      </RegistrationCard>
    ) : null

  const orgId = Number(/\/api\/orgs\/(\d+)\//.exec(base)?.[1] ?? 0)

  const s = data.summary
  const hasRegistered = data.registrations.some((r) => r.status === 'registered')
  return (
    <RegistrationCard title={t('Anmeldungen')}>
      <p>
        {offer.state_text}{' '}
        {offer.capacity !== null &&
          t('{taken} von {capacity} Plätzen belegt.', {
            taken: offer.taken,
            capacity: offer.capacity,
          })}
      </p>
      <PriceList prices={offer.prices.filter((p) => p.is_active)} />
      {offer.public_url && <PublicLink url={offer.public_url} />}
      {s && (
        <p className="muted small">
          {t('{r} Anmeldungen, {p} Personen · Summe {total}, bezahlt {paid}, offen {open}', {
            r: s.registrations,
            p: s.persons,
            total: euro(s.total),
            paid: euro(s.paid),
            open: euro(s.open),
          })}
          {s.waiting > 0 && ` · ${t('{n} auf der Warteliste', { n: s.waiting })}`}
          {Number(s.fees) > 0 && ` · ${t('Stornogebühren {fees}', { fees: euro(s.fees) })}`}
          {Number(s.refund) > 0 && ` · ${t('zu erstatten {refund}', { refund: euro(s.refund) })}`}
        </p>
      )}
      <div className="button-row">
        {data.can_edit && (
          <>
            <button type="button" className="button" onClick={() => setAdding(!adding)}>
              <span aria-hidden="true">+</span> {t('Anmeldung erfassen')}
            </button>
            <button type="button" className="button button-ghost" onClick={() => setEditing(true)}>
              {t('Einstellungen')}
            </button>
          </>
        )}
        {hasRegistered && (
          <button type="button" className="button button-ghost" onClick={() => setCheckIn(true)}>
            {t('Einlass')}
          </button>
        )}
        {hasRegistered && data.can_edit && (
          <button type="button" className="button button-ghost" onClick={() => setScanLinks(true)}>
            {t('Scan-Links für Personal')}
          </button>
        )}
        {hasRegistered && (
          <button type="button" className="button button-ghost" onClick={() => setPrinting(true)}>
            {t('Namensschilder und Aufkleber')}
          </button>
        )}
        {hasRegistered && (
          <button type="button" className="button button-ghost" onClick={() => setMaterial(true)}>
            {t('Material')}
          </button>
        )}
        {hasRegistered && data.can_edit && (
          <a
            className="button button-ghost"
            href={registrationApi.certificatesUrl(base, event.id)}
            target="_blank"
            rel="noopener"
          >
            {t('Teilnahmebescheinigungen (PDF)')}
          </a>
        )}
        {hasRegistered && (data.qualification_kinds?.length ?? 0) > 0 && (
          <button type="button" className="button button-ghost" onClick={() => setQualifying(true)}>
            {t('Qualifikation eintragen')}
          </button>
        )}
        {data.registrations.length > 0 && (
          <a className="button button-ghost" href={registrationApi.exportUrl(base, event.id)}>
            {t('Teilnehmerliste (Excel)')}
          </a>
        )}
        {data.registrations.length > 0 && asksHealth(offer) && (
          <a className="button button-ghost" href={registrationApi.exportUrl(base, event.id, true)}>
            {t('Liste mit Allergien (Excel)')}
          </a>
        )}
      </div>
      {checkIn && (
        <Modal
          title={t('Einlass: {title}', { title: event.title })}
          guard={false}
          onClose={() => {
            setCheckIn(false)
            void reload()
          }}
        >
          <CheckInPanel base={base} eventId={event.id} />
        </Modal>
      )}
      {printing && (
        <Modal
          title={t('Namensschilder und Aufkleber: {title}', { title: event.title })}
          guard={false}
          onClose={() => setPrinting(false)}
        >
          <PrintLoader base={base} eventId={event.id} />
        </Modal>
      )}
      {material && (
        <Modal
          title={t('Material: {title}', { title: event.title })}
          guard={false}
          onClose={() => setMaterial(false)}
        >
          <MaterialPanel base={base} eventId={event.id} />
        </Modal>
      )}
      {scanLinks && (
        <Modal
          title={t('Scan-Links für Personal: {title}', { title: event.title })}
          guard={false}
          onClose={() => setScanLinks(false)}
        >
          <ScanLinksPanel base={base} eventId={event.id} />
        </Modal>
      )}
      {qualifying && (
        <Modal
          title={t('Qualifikation eintragen: {title}', { title: event.title })}
          guard={false}
          onClose={() => setQualifying(false)}
        >
          <QualificationPanel
            base={base}
            eventId={event.id}
            kinds={data.qualification_kinds ?? []}
            lastDay={berlin(event.ends_at ?? event.starts_at).date}
          />
        </Modal>
      )}
      {adding && (
        <BoardAddForm
          base={base}
          event={event}
          offer={offer}
          onDone={(next) => {
            setData(next)
            setAdding(false)
          }}
        />
      )}
      {cancelling && (
        <CancelPanel
          key={cancelling.id}
          reg={cancelling}
          offer={offer}
          board
          quote={(ids) => registrationApi.quote(base, event.id, cancelling.id, ids)}
          onConfirm={async (choice) => {
            setData(await registrationApi.cancel(base, event.id, cancelling.id, choice))
            setCancelling(null)
          }}
          onClose={() => setCancelling(null)}
        />
      )}
      {replacing && (
        <SubstitutePanel
          key={replacing.p.id}
          participant={replacing.p}
          offer={offer}
          orgId={orgId}
          onConfirm={async (choice) => {
            setData(
              await registrationApi.substitute(
                base,
                event.id,
                replacing.reg.id,
                replacing.p.id,
                choice,
              ),
            )
            setReplacing(null)
          }}
          onClose={() => setReplacing(null)}
        />
      )}
      {data.registrations.length > 0 && (
        <RegistrationTable
          rows={data.registrations}
          offer={offer}
          canEdit={data.can_edit}
          ticketsUrl={(reg) => registrationApi.ticketsUrl(base, event.id, reg.id)}
          onCancel={(reg) => {
            setReplacing(null)
            setCancelling(reg)
          }}
          onSubstitute={(reg, p) => {
            setCancelling(null)
            setReplacing({ reg, p })
          }}
        />
      )}
      {!data.registrations.length && <p className="muted small">{t('Noch keine Anmeldungen.')}</p>}
      <button type="button" className="button button-ghost small" onClick={() => void reload()}>
        {t('Aktualisieren')}
      </button>
    </RegistrationCard>
  )
}
