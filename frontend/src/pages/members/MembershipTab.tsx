import { useState } from 'react'
import { MaterialReferences } from '../../components/MaterialReferences.tsx'
import type { FormEvent } from 'react'
import { memberApi, todayIso } from '../../api/members.ts'
import type { DepartmentMembership, DurationInfo, MemberDetail } from '../../api/members.ts'
import { unitName } from '../../api/orgs.ts'
import type { OrgSummary } from '../../api/orgs.ts'
import {
  DATE_PRECISION_WORD,
  errorMessage,
  formatDate,
  formatMemberDate,
  jubileeWhen,
  useForm,
} from '../../components/forms.ts'
import { confirmDiscard, useChangesGuard } from '../../components/leaveGuard.ts'
import { Alert, Checkbox, Field, SelectField } from '../../components/ui.tsx'
import { orgTerms, useTerms } from '../../org/terms.ts'
import { MembershipActions } from './MembershipActions.tsx'
import { HonoraryAwards } from './HonoraryAwards.tsx'
import { QualificationsCard } from './QualificationsCard.tsx'
import { FeeProofsCard } from './FeeProofsCard.tsx'
import { confirmDialog } from '../../components/dialog.ts'
import { Term } from '../../learning/Aids.tsx'
import { t, tn } from '../../i18n/index.ts'
import { MemberBookings } from '../bookings/MemberBookings.tsx'
import { useDepartmentChoices } from '../../components/masterData.ts'
import { AddPeriod } from './AddPeriod.tsx'
import { MemberFileSection } from './MemberFileSection.tsx'
import { AddWithDate } from './AddWithDate.tsx'

export function MembershipTab({
  org,
  member,
  canEdit,
  reload,
  setData,
}: {
  org: OrgSummary
  member: MemberDetail
  canEdit: boolean
  reload: () => Promise<void>
  setData: (m: MemberDetail) => void
}) {
  const tm = useTerms()
  const [error, setError] = useState<string | null>(null)
  const departments = useDepartmentChoices(org.id)
  const precision = org.date_precision
  const [editingDepartment, setEditingDepartment] = useState<number | null>(null)
  const [correcting, setCorrecting] = useState<number | null>(null)
  const terms = orgTerms(org)

  async function run(action: () => Promise<unknown>) {
    setError(null)
    try {
      await action()
      await reload()
    } catch (err) {
      setError(errorMessage(err))
    }
  }

  return (
    <div className="stack">
      {canEdit && <MembershipActions org={org} member={member} onChanged={setData} />}
      {/* Ehrungen gehören zur Mitgliedschaft, sie können den Beitrag ändern (Rollen-Vorschlag F-3) */}
      {org.modules.includes('awards') && (
        <HonoraryAwards
          orgId={org.id}
          memberId={member.id}
          awards={member.honorary_titles?.own ?? []}
          otherAwards={member.honorary_titles?.federation}
          otherLabel={`Verliehen ${orgTerms(org).dv_vom}`}
          canEdit={canEdit}
          onChanged={reload}
        />
      )}
      {org.modules.includes('qualifications') && (
        <QualificationsCard orgId={org.id} memberId={member.id} canEdit={canEdit} />
      )}
      {org.modules.includes('billing') && member.kind !== 'organization' && (
        <FeeProofsCard orgId={org.id} memberId={member.id} canEdit={canEdit} />
      )}

      <MemberFileSection title={t('Mitgliedsdauer')}>
        <DurationLine label={tm.e_im} info={member.duration.club} />
        {member.duration.federation && (
          <DurationLine
            label={t('{dv_im} ({rule})', {
              dv_im: terms.dv_im,
              rule: member.duration.federation.rule,
            })}
            info={member.duration.federation}
          />
        )}
      </MemberFileSection>

      <MemberFileSection title={t('Zeiträume')}>
        <table className="table">
          <thead>
            <tr>
              <th>{t('Eintritt')}</th>
              <th>{t('Austritt')}</th>
              <th>{t('Grund')}</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {member.periods.map((p) => (
              <tr key={p.id}>
                <td>{formatMemberDate(p.entry_date, precision)}</td>
                <td>{p.exit_date ? formatMemberDate(p.exit_date, precision) : t('heute')}</td>
                <td>{p.exit_reason_label || '–'}</td>
                <td className="actions">
                  {canEdit && (
                    <button
                      type="button"
                      className="link-button"
                      onClick={() => setCorrecting(correcting === p.id ? null : p.id)}
                    >
                      {t('Ein-/Austritt korrigieren')}
                    </button>
                  )}{' '}
                  {canEdit && member.periods.length > 1 && (
                    <button
                      type="button"
                      className="link-button"
                      onClick={async () => {
                        if (
                          await confirmDialog({
                            final: false,
                            title: t('Diesen Zeitraum löschen?'),
                            confirmLabel: t('Löschen'),
                          })
                        ) {
                          void run(() => memberApi.deletePeriod(org.id, member.id, p.id))
                        }
                      }}
                    >
                      {t('Löschen')}
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {canEdit && correcting !== null && (
          <CorrectPeriod
            key={correcting}
            org={org}
            member={member}
            periodId={correcting}
            onDone={async () => {
              setCorrecting(null)
              await reload()
            }}
            onCancel={() => setCorrecting(null)}
          />
        )}
        {canEdit && <AddPeriod org={org} member={member} onAdded={reload} />}
      </MemberFileSection>

      <MemberFileSection title={t('Mitgliedsarten')}>
        <ul className="plain-list">
          {member.type_history.map((tmx) => (
            <li key={tmx.id}>
              <strong>{tmx.member_type_name}</strong> ·{' '}
              {formatMemberDate(tmx.valid_from, precision)} –{' '}
              {tmx.valid_until ? formatMemberDate(tmx.valid_until, precision) : t('heute')}
              <span className="muted small">
                {' '}
                ({tmx.active ? t('aktiv') : t('nicht aktiv')},{' '}
                {tmx.reported ? t('gemeldet') : t('nicht gemeldet')})
              </span>
            </li>
          ))}
        </ul>
      </MemberFileSection>

      {member.federation && (
        <MemberFileSection title={member.federation.name}>
          <p>
            {/* Die Verbandsnummer steht hier bewusst nicht (Ralf 2026-10-30). */}
            {member.federation.is_member ? t('Mitglied') : t('derzeit kein Mitglied')}
          </p>
          {member.federation.remote ? (
            <p className="muted small">
              {t('Der Dachverband führt sein Register auf einer eigenen Instanz (Verbund).')}
            </p>
          ) : (
            <p>
              {t('Eintritt:')}{' '}
              {formatMemberDate(
                member.federation.entry_date,
                member.duration.federation?.precision ?? precision,
              )}
              {member.federation.entry_date_manual
                ? t(' (von Hand eingetragen)')
                : t(' (berechnet)')}
            </p>
          )}
          {canEdit && !member.federation.remote && member.federation.member_number && (
            <FederationEntry org={org} member={member} onSaved={setData} />
          )}
        </MemberFileSection>
      )}

      {member.other_memberships && member.other_memberships.length > 0 && (
        <MemberFileSection
          title={t('Mitgliedschaften in anderen {e_pl_dat}', { e_pl_dat: tm.e_pl_dat })}
        >
          <ul className="plain-list">
            {member.other_memberships.map((m, i) => (
              <li key={i}>
                <strong>{m.club}</strong> · {formatMemberDate(m.entry_date, precision)} –{' '}
                {m.exit_date ? formatMemberDate(m.exit_date, precision) : t('heute')}
              </li>
            ))}
          </ul>
        </MemberFileSection>
      )}

      <MemberFileSection title={org.department_label_plural}>
        {member.departments.length === 0 ? (
          <p className="muted">{t('Keine Zuordnung.')}</p>
        ) : (
          <ul className="plain-list">
            {member.departments.map((d) => (
              <li key={d.id}>
                <strong>{d.department_name}</strong> · {formatMemberDate(d.valid_from, precision)} –{' '}
                {d.valid_until ? formatMemberDate(d.valid_until, precision) : t('heute')}
                {canEdit && editingDepartment !== d.id && (
                  <button
                    type="button"
                    className="link-button spaced"
                    aria-label={t('Mitgliedschaft in {name} bearbeiten', {
                      name: d.department_name,
                    })}
                    disabled={editingDepartment !== null}
                    onClick={() => setEditingDepartment(d.id)}
                  >
                    {t('Bearbeiten')}
                  </button>
                )}
                {canEdit && !d.valid_until && (
                  <button
                    type="button"
                    className="link-button spaced"
                    disabled={editingDepartment !== null}
                    onClick={() =>
                      void run(() => memberApi.endDepartment(org.id, member.id, d.id, todayIso()))
                    }
                  >
                    {t('beenden')}
                  </button>
                )}
                {canEdit && editingDepartment === d.id && (
                  <EditDepartmentMembership
                    orgId={org.id}
                    memberId={member.id}
                    membership={d}
                    reload={reload}
                    onClose={() => setEditingDepartment(null)}
                  />
                )}
              </li>
            ))}
          </ul>
        )}
        {canEdit && departments.data && departments.data.length > 0 && (
          <AddWithDate
            label={t('{department_label} hinzufügen', { department_label: org.department_label })}
            // Nicht mehr aktive Einheiten nur zum Nachtragen früherer Zeiten (mit Ende)
            options={[...departments.data]
              .sort((a, b) => Number(b.is_active) - Number(a.is_active))
              .map((d) => ({
                id: d.id,
                name: d.is_active ? unitName(d) : unitName(d) + t(' (inaktiv)'),
                needsEnd: !d.is_active,
              }))}
            withEnd
            onAdd={(id, date, until) =>
              run(() =>
                memberApi.addDepartment(org.id, member.id, {
                  department: id,
                  valid_from: date,
                  valid_until: until,
                }),
              )
            }
          />
        )}
        {org.modules.includes('billing') && member.departments.some((d) => !d.valid_until) && (
          <Checkbox
            label={t('zahlt den Beitrag selbst (nicht über die Sammelrechnung {x})', {
              x: org.department_terms?.gen ?? t('der {x0}', { x0: org.department_label }),
            })}
            checked={member.pays_fee_self}
            disabled={!canEdit}
            onChange={(val) =>
              void run(() => memberApi.update(org.id, member.id, { pays_fee_self: val }))
            }
          />
        )}
      </MemberFileSection>
      <MaterialReferences
        kind="member"
        id={member.id}
        sourceBase={`/api/orgs/${org.id}/`}
        level={2}
        title={t('Ausgegebenes Material')}
        wide
      />
      <MemberBookings org={org} memberId={member.id} />
      {/* Eigene Region, unabhängig von Untereinheiten (UX-Audit 31.10. W08) */}
      <MemberFileSection title={t('Kommunikation & Zustellung')}>
        <Checkbox
          label={t('Rundschreiben der Art „Information“ erwünscht')}
          checked={!member.info_opt_out_at}
          disabled={!canEdit}
          onChange={(val) =>
            void run(() => memberApi.update(org.id, member.id, { info_opt_out: !val }))
          }
        />
        <p className="small" role="status">
          {member.info_opt_out_at ? (
            <>
              {t('Seit {x} abbestellt (', { x: formatDate(member.info_opt_out_at) })}
              <Term k="opt_out">{t('Widerspruch')}</Term>
              {t('): keine Informationen per E-Mail oder Brief.')}
            </>
          ) : (
            t('Erhält Informationen.')
          )}
        </p>
        <p className="muted small">
          {t(
            'Vereinsmitteilungen, Kurzmitteilungen, Rechnungen und Post an Vorstände oder Rolleninhaber kommen unabhängig davon.',
          )}
        </p>
        {member.greetings_opt_out_at !== undefined && (
          <>
            <Checkbox
              label={t('Glückwünsche zu Geburtstag und Jubiläum erwünscht')}
              checked={!member.greetings_opt_out_at}
              disabled={!canEdit}
              onChange={(val) =>
                void run(() => memberApi.update(org.id, member.id, { greetings_opt_out: !val }))
              }
            />
            {member.greetings_opt_out_at && (
              <p className="small" role="status">
                {t('Hat am {x} Glückwünschen widersprochen.', {
                  x: formatDate(member.greetings_opt_out_at),
                })}
              </p>
            )}
          </>
        )}
      </MemberFileSection>
      {error && <Alert kind="error">{error}</Alert>}
    </div>
  )
}

function EditDepartmentMembership({
  orgId,
  memberId,
  membership,
  reload,
  onClose,
}: {
  orgId: number
  memberId: number
  membership: DepartmentMembership
  reload: () => Promise<void>
  onClose: () => void
}) {
  const form = useForm({
    valid_from: membership.valid_from,
    valid_until: membership.valid_until ?? '',
  })
  const { dirty, markSaved } = useChangesGuard(form.values)

  async function save(ev: FormEvent) {
    ev.preventDefault()
    const saved = await form.submit(async () => {
      const result = await memberApi.updateDepartment(orgId, memberId, membership.id, {
        valid_from: form.values.valid_from,
        valid_until: form.values.valid_until || null,
      })
      await reload()
      return result
    })
    if (saved) {
      markSaved()
      onClose()
    }
  }

  return (
    <form
      className="subcard"
      aria-label={t('Mitgliedschaft in {name} bearbeiten', { name: membership.department_name })}
      onSubmit={save}
    >
      <div className="grid-2">
        <Field
          label={t('Beginn')}
          type="date"
          required
          autoFocus
          disabled={form.busy}
          value={form.values.valid_from}
          error={form.errors.valid_from}
          onChange={(e) => form.set('valid_from', e.target.value)}
        />
        <Field
          label={t('Ende')}
          type="date"
          min={form.values.valid_from}
          disabled={form.busy}
          hint={t('Leer lassen, solange die Mitgliedschaft besteht.')}
          value={form.values.valid_until}
          error={form.errors.valid_until}
          onChange={(e) => form.set('valid_until', e.target.value)}
        />
      </div>
      {form.message?.kind === 'error' && <Alert kind="error">{form.message.text}</Alert>}
      <div className="button-row">
        <button type="submit" className="button button-primary" disabled={form.busy}>
          {t('Speichern')}
        </button>
        <button
          type="button"
          className="button button-ghost"
          disabled={form.busy}
          onClick={() => void confirmDiscard(dirty).then((yes) => yes && onClose())}
        >
          {t('Abbrechen')}
        </button>
      </div>
    </form>
  )
}

function DurationLine({ label, info }: { label: string; info: DurationInfo }) {
  return (
    <p>
      <strong>{tn('{n} Jahr', '{n} Jahre', info.years)}</strong> {label}
      <span className="muted small">
        {' '}
        (
        {info.precision === 'day' || !info.precision
          ? t('{days} Tage gezählt', { days: info.days })
          : DATE_PRECISION_WORD[info.precision] + t(' gezählt')}
        {info.next &&
          t(' · nächstes Jubiläum: {years} Jahre {x}', {
            years: info.next.years,
            x: jubileeWhen(info.next.date, info.precision),
          })}
        )
      </span>
    </p>
  )
}

/** Ein- oder Austrittsdatum berichtigen bzw. Austritt aufheben (Datenaudit 08.11. DA-01). */
function CorrectPeriod({
  org,
  member,
  periodId,
  onDone,
  onCancel,
}: {
  org: OrgSummary
  member: MemberDetail
  periodId: number
  onDone: () => Promise<void>
  onCancel: () => void
}) {
  const period = member.periods.find((x) => x.id === periodId)
  const form = useForm({
    entry_date: period?.entry_date ?? '',
    exit_date: period?.exit_date ?? '',
    exit_reason: period?.exit_reason || 'exit',
  })
  if (!period) return null
  async function save(ev: FormEvent) {
    ev.preventDefault()
    const exit = form.values.exit_date || null
    if (
      period?.exit_date &&
      !exit &&
      !(await confirmDialog({
        title: t('Austritt aufheben?'),
        message: t(
          'Die Mitgliedschaft läuft dann wieder offen. Mitgliedsart, {department_label_plural} und Ämter, die mit dem Austritt endeten, laufen ebenfalls weiter.',
          { department_label_plural: org.department_label_plural },
        ),
        confirmLabel: t('Austritt aufheben'),
        danger: false,
      }))
    )
      return
    const ok = await form.submit(() =>
      memberApi.correctPeriod(org.id, member.id, {
        period: periodId,
        entry_date: form.values.entry_date,
        exit_date: exit,
        exit_reason: exit ? form.values.exit_reason : '',
      }),
    )
    if (ok) await onDone()
  }
  return (
    <form className="subcard" onSubmit={save}>
      <h3>{t('Ein-/Austritt korrigieren')}</h3>
      <p className="muted small">
        {t(
          'Mitgliedsart, {department_label_plural} und Ämter, die am alten Datum begannen bzw. endeten, ziehen mit. Austrittsdatum leeren hebt den Austritt auf.',
          { department_label_plural: org.department_label_plural },
        )}
      </p>
      <div className="grid-3">
        <Field
          label={t('Eintritt')}
          type="date"
          required
          value={form.values.entry_date}
          error={form.errors.entry_date}
          onChange={(e) => form.set('entry_date', e.target.value)}
        />
        <Field
          label={t('Austritt')}
          type="date"
          value={form.values.exit_date}
          error={form.errors.exit_date}
          onChange={(e) => form.set('exit_date', e.target.value)}
        />
        {form.values.exit_date && (
          <SelectField
            label={t('Grund')}
            value={form.values.exit_reason}
            error={form.errors.exit_reason}
            onChange={(e) => form.set('exit_reason', e.target.value)}
          >
            {member.exit_reasons.map((r) => (
              <option key={r.value} value={r.value}>
                {r.label}
              </option>
            ))}
          </SelectField>
        )}
      </div>
      {form.message?.kind === 'error' && <Alert kind="error">{form.message.text}</Alert>}
      <div className="button-row">
        <button type="submit" className="button button-primary" disabled={form.busy}>
          {t('Speichern')}
        </button>
        <button type="button" className="button button-ghost" onClick={onCancel}>
          {t('Abbrechen')}
        </button>
      </div>
    </form>
  )
}

function FederationEntry({
  org,
  member,
  onSaved,
}: {
  org: OrgSummary
  member: MemberDetail
  onSaved: (m: MemberDetail) => void
}) {
  const form = useForm({
    date: member.federation?.entry_date_manual ? (member.federation.entry_date ?? '') : '',
  })
  async function save(ev: FormEvent) {
    ev.preventDefault()
    const saved = await form.submit(() =>
      memberApi.setFederationEntry(org.id, member.id, form.values.date || null),
    )
    if (saved) onSaved(saved as MemberDetail)
  }
  return (
    <form className="inline-add" onSubmit={save}>
      <input
        type="date"
        aria-label={t('Eintritt in {dv_akk} (Altdaten)', { dv_akk: orgTerms(org).dv_akk })}
        value={form.values.date}
        onChange={(e) => form.set('date', e.target.value)}
      />
      <button type="submit" className="button button-ghost" disabled={form.busy}>
        {form.values.date ? t('Eintritt von Hand setzen') : t('Berechnen lassen')}
      </button>
    </form>
  )
}
