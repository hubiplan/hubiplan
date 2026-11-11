import { useState } from 'react'
import { MaterialReferences } from '../../components/MaterialReferences.tsx'
import type { FormEvent, ReactNode } from 'react'
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { GENDERS, LEGAL_FORMS, memberApi, todayIso } from '../../api/members.ts'
import type { DepartmentMembership, DurationInfo, Gender, MemberDetail } from '../../api/members.ts'
import { orgApi, PERM, unitName } from '../../api/orgs.ts'
import type { OrgSummary } from '../../api/orgs.ts'
import {
  DATE_PRECISION_WORD,
  errorMessage,
  formatDate,
  formatDateTime,
  formatMemberDate,
  jubileeWhen,
  useAutoSave,
  useForm,
  useLoad,
} from '../../components/forms.ts'
import { confirmDiscard, useChangesGuard } from '../../components/leaveGuard.ts'
import {
  Alert,
  Checkbox,
  Field,
  SaveStatus,
  SelectField,
  LoadError,
  Loading,
} from '../../components/ui.tsx'
import { useActiveOrg } from '../../org/OrgContext.tsx'
import { orgTerms, useTerms } from '../../org/terms.ts'
import { MembershipActions } from './MembershipActions.tsx'
import { SuggestCorrection } from './FederationMembersPage.tsx'
import { FieldsTab } from './FieldsTab.tsx'
import { PhotoSection } from './PhotoSection.tsx'
import { ContactPersons } from './ContactPersons.tsx'
import { PublicationSection } from './PublicationSection.tsx'
import { HonoraryAwards } from './HonoraryAwards.tsx'
import { AssignRoleDialog } from '../../components/AssignRoleDialog.tsx'
import { MemberAccessSection } from '../../components/AccessPanel.tsx'
import { AuditUndo } from '../../components/AuditUndo.tsx'
import { firstOfSet } from '../../components/undo.ts'
import { CardPanel } from '../../components/CardPanel.tsx'
import { cardApi, cardBase } from '../../api/cards.ts'
import { confirmDialog } from '../../components/dialog.ts'
import { Term } from '../../learning/Aids.tsx'
import { t, tn } from '../../i18n/index.ts'
import { CompetitionsTab } from '../competitions/MemberTab.tsx'
import { FeesTab } from './FeesTab.tsx'
import { MusicTab } from './MusicTab.tsx'
import { AtAGlance } from './AtAGlance.tsx'
import { MemberHeader } from './MemberHeader.tsx'

type Tab =
  | 'stammdaten'
  | 'mitgliedschaft'
  | 'beitraege'
  | 'rollen'
  | 'wettbewerbe'
  | 'musik'
  | 'foto'
  | 'zusatzfelder'
  | 'verlauf'

/** Reiter in Arbeitsreihenfolge (Konzept Mitgliedsakte S-03) */
const TABS: { id: Tab; label: string }[] = [
  { id: 'stammdaten', label: t('Stammdaten') },
  { id: 'mitgliedschaft', label: t('Mitgliedschaft') },
  { id: 'beitraege', label: t('Beiträge') },
  { id: 'rollen', label: t('Rollen und Konto') },
  { id: 'wettbewerbe', label: t('Wettbewerbe') },
  { id: 'musik', label: t('Musik') },
  { id: 'foto', label: t('Foto & Webseite') },
  { id: 'zusatzfelder', label: t('Zusatzfelder') },
  { id: 'verlauf', label: t('Verlauf') },
]

export function MemberFilePage() {
  const org = useActiveOrg()
  const id = Number(useParams().id)
  const { data, error, setData, reload } = useLoad(() => memberApi.detail(org.id, id), [org.id, id])
  // Bereich steht in der Adresse: Zurück, Neuladen und Links öffnen ihn wieder (NMF-07)
  const [params] = useSearchParams()
  const navigate = useNavigate()
  // Reiter nur mit freigeschaltetem Modul (Menüprüfung 2, N-08); Musik zusätzlich mit Leserecht
  const tabs = TABS.filter(
    (tmx) =>
      (tmx.id !== 'wettbewerbe' || org.modules.includes('competitions')) &&
      (tmx.id !== 'beitraege' || org.modules.includes('billing')) &&
      (tmx.id !== 'musik' ||
        (org.modules.includes('music') && org.permissions.includes('music.view'))),
  )
  const tab: Tab = tabs.find((tmx) => tmx.id === params.get('bereich'))?.id ?? 'stammdaten'
  const canEdit = org.permissions.includes(PERM.membersEdit)
  const tabLink = (to: Tab) => (to === 'stammdaten' ? '.' : `?bereich=${to}`)

  if (error) return <LoadError message={error} onRetry={() => void reload()} />
  if (!data) return <Loading />

  return (
    <section>
      <MemberHeader org={org} member={data} canEdit={canEdit} tabs={tabs.map((tmx) => tmx.id)} />
      <AtAGlance org={org} member={data} tabs={tabs.map((tmx) => tmx.id)} />
      <nav className="tabs member-tabs" aria-label={t('Bereiche der Mitgliedsakte')}>
        {tabs.map((tmx) => (
          <Link
            key={tmx.id}
            to={tabLink(tmx.id)}
            className={`tab${tab === tmx.id ? ' active' : ''}`}
            aria-current={tab === tmx.id ? 'page' : undefined}
          >
            {tmx.label}
          </Link>
        ))}
      </nav>
      {/* Handy: alle Bereiche als Auswahlliste statt seitlich wischbarer Reiter */}
      <label className="member-tabs-select">
        <span>{t('Bereich')}</span>
        <select value={tab} onChange={(ev) => void navigate(tabLink(ev.target.value as Tab))}>
          {tabs.map((tmx) => (
            <option key={tmx.id} value={tmx.id}>
              {tmx.label}
            </option>
          ))}
        </select>
      </label>
      {tab === 'stammdaten' && (
        <div className="stack">
          <MasterData
            key={data.id}
            org={org}
            member={data}
            canEdit={canEdit && !data.managed_by}
            onSaved={setData}
          />
          {data.kind === 'organization' && (
            <ContactPersons
              key={`ansprechpartner-${data.id}`}
              orgId={org.id}
              memberId={data.id}
              contacts={data.contact_persons ?? []}
              canEdit={canEdit}
              onChange={() => void reload()}
            />
          )}
          {(data.contact_for ?? []).length > 0 && (
            <p className="muted">
              {t('Ansprechpartner für:')}{' '}
              {(data.contact_for ?? []).map((c, i) => (
                <span key={c.member_id}>
                  {i > 0 && ', '}
                  <Link to={`/mitglieder/${c.member_id}`}>{c.name}</Link>
                </span>
              ))}
            </p>
          )}
          {data.managed_by && (
            <SuggestCorrection
              orgId={org.id}
              member={data}
              owner={data.managed_by.name}
              intro={`Stammdaten und Kontakt pflegt ${data.managed_by.name} auf einer eigenen HUBIplan-Instanz (Verbund). Mitgliedschaft, Mitgliedsart und Beitrag bleiben hier. Hier lässt sich eine Korrektur vorschlagen.`}
            />
          )}
        </div>
      )}
      {tab === 'mitgliedschaft' && (
        <MembershipTab
          org={org}
          member={data}
          canEdit={canEdit}
          reload={reload}
          setData={setData}
        />
      )}
      {tab === 'beitraege' && (
        <FeesTab org={org} member={data} canEdit={canEdit} onSaved={setData} />
      )}
      {tab === 'rollen' && <RolesTab org={org} member={data} canEdit={canEdit} reload={reload} />}
      {tab === 'wettbewerbe' && <CompetitionsTab org={org.id} membership={data.id} />}
      {tab === 'musik' && <MusicTab orgId={org.id} memberId={data.id} />}
      {tab === 'foto' && (
        <div className="stack">
          <PhotoSection
            key={`foto-${data.id}`}
            orgId={org.id}
            memberId={data.id}
            initial={{
              photo: data.photo,
              photo_consent_at: data.photo_consent_at,
              photo_consent_source: data.photo_consent_source,
            }}
            canManage={org.permissions.includes(PERM.photosManage)}
            hasEmail={!!data.contact?.email}
            organization={data.kind === 'organization'}
            onChange={() => void reload()}
          />
          {org.modules.includes('website') && (
            <PublicationSection
              key={`veroeffentlichung-${data.id}`}
              orgId={org.id}
              memberId={data.id}
              canEdit={canEdit}
            />
          )}
          {org.permissions.includes(PERM.cardsView) && (
            <CardPanel
              key={`ausweis-${data.id}`}
              base={cardBase.org(org.id, data.id)}
              pdfUrl={cardApi.orgPdfUrl(org.id, { mitglied: data.id })}
              canEdit={org.permissions.includes(PERM.cardsManage)}
            />
          )}
        </div>
      )}
      {tab === 'zusatzfelder' && <FieldsTab orgId={org.id} memberId={data.id} canEdit={canEdit} />}
      {tab === 'verlauf' && <HistoryTab orgId={org.id} memberId={data.id} />}
    </section>
  )
}

function MasterData({
  org,
  member,
  canEdit,
  onSaved,
}: {
  org: OrgSummary
  member: MemberDetail
  canEdit: boolean
  onSaved: (m: MemberDetail) => void
}) {
  const tm = useTerms()
  const c = member.contact
  const o = member.organization
  const organization = member.kind === 'organization'
  const form = useForm({
    last_name: member.last_name,
    first_name: member.first_name,
    birth_date: member.birth_date ?? '',
    gender: member.gender ?? '',
    name_suffix: o?.name_suffix ?? '',
    legal_form: o?.legal_form ?? '',
    legal_form_other: o?.legal_form_other ?? '',
    register: o?.register ?? '',
    vat_id: o?.vat_id ?? '',
    website: o?.website ?? '',
    size: o?.size != null ? String(o.size) : '',
    club_number: member.club_number,
    email: c?.email ?? '',
    phone: c?.phone ?? '',
    street: c?.street ?? '',
    postal_code: c?.postal_code ?? '',
    city: c?.city ?? '',
    country: c?.country ?? 'Deutschland',
  })
  const v = form.values
  const e = form.errors
  const auto = useAutoSave(
    form,
    // Nur Geändertes senden: Der Server ergänzt neue Kontaktdaten selbst, und so
    // überschreibt ein veralteter Stand keine gleichzeitige Änderung anderer Felder.
    (changes) => memberApi.update(org.id, member.id, changes),
    { enabled: canEdit, onSaved: (saved) => onSaved(saved as MemberDetail) },
  )

  return (
    <form
      className="card card-wide"
      aria-labelledby="stammdaten-titel"
      onSubmit={(ev) => ev.preventDefault()}
    >
      <h2 id="stammdaten-titel">{t('Stammdaten')}</h2>
      {canEdit && <SaveStatus auto={auto} />}
      <fieldset disabled={!canEdit}>
        {organization ? (
          <>
            <div className="grid-2">
              <Field
                label={t('Name der Organisation')}
                required
                value={v.last_name}
                error={e.last_name}
                onChange={(ev) => form.set('last_name', ev.target.value)}
              />
              <Field
                label={t('Namenszusatz')}
                value={v.name_suffix}
                error={e.name_suffix}
                onChange={(ev) => form.set('name_suffix', ev.target.value)}
              />
            </div>
            <div className="grid-4">
              <SelectField
                label={t('Rechtsform')}
                value={v.legal_form}
                error={e.legal_form}
                onChange={(ev) => form.set('legal_form', ev.target.value)}
              >
                <option value="">{t('– keine Angabe –')}</option>
                {LEGAL_FORMS.map((f) => (
                  <option key={f.value} value={f.value}>
                    {f.label}
                  </option>
                ))}
              </SelectField>
              {v.legal_form === 'other' && (
                <Field
                  label={t('Rechtsform (Freitext)')}
                  value={v.legal_form_other}
                  error={e.legal_form_other}
                  onChange={(ev) => form.set('legal_form_other', ev.target.value)}
                />
              )}
              <Field
                label={t('Register (Gericht und Nummer)')}
                value={v.register}
                error={e.register}
                onChange={(ev) => form.set('register', ev.target.value)}
              />
              <Field
                label={t('USt-IdNr.')}
                value={v.vat_id}
                error={e.vat_id}
                onChange={(ev) => form.set('vat_id', ev.target.value)}
              />
            </div>
            <div className="grid-2">
              <Field
                label={t('Webseite')}
                value={v.website}
                error={e.website}
                onChange={(ev) => form.set('website', ev.target.value)}
              />
              <Field
                label={t('Größe')}
                hint={t('Für die Staffel nach Größe, zum Beispiel Mitarbeiter oder Einwohner')}
                type="number"
                min={0}
                value={v.size}
                error={e.size}
                onChange={(ev) => form.set('size', ev.target.value)}
              />
            </div>
          </>
        ) : (
          <div className="grid-4">
            <Field
              label={t('Name')}
              required
              value={v.last_name}
              error={e.last_name}
              onChange={(ev) => form.set('last_name', ev.target.value)}
            />
            <Field
              label={t('Vorname')}
              required
              value={v.first_name}
              error={e.first_name}
              onChange={(ev) => form.set('first_name', ev.target.value)}
            />
            {member.birth_year_only && member.birth_date && v.birth_date === member.birth_date ? (
              <Field
                label={t('Geburtsjahr')}
                value={member.birth_date.slice(0, 4)}
                hint={t('Nach der Löschfrist ist nur noch das Jahr gespeichert.')}
                readOnly
              />
            ) : (
              <Field
                label={t('Geburtsdatum')}
                type="date"
                value={v.birth_date}
                error={e.birth_date}
                onChange={(ev) => form.set('birth_date', ev.target.value)}
              />
            )}
            <SelectField
              label={t('Geschlecht')}
              value={v.gender}
              error={e.gender}
              onChange={(ev) => form.set('gender', ev.target.value as Gender)}
            >
              {GENDERS.map((g) => (
                <option key={g.value} value={g.value}>
                  {g.label}
                </option>
              ))}
            </SelectField>
          </div>
        )}
        <div className="grid-2">
          <Field
            label={t('E-Mail-Adresse (optional)')}
            type="email"
            value={v.email}
            error={e.email}
            onChange={(ev) => form.set('email', ev.target.value)}
          />
          <Field
            label={t('Telefon')}
            value={v.phone}
            error={e.phone}
            onChange={(ev) => form.set('phone', ev.target.value)}
          />
        </div>
        <Field
          label={t('Straße und Hausnummer')}
          required
          value={v.street}
          error={e.street}
          onChange={(ev) => form.set('street', ev.target.value)}
        />
        <div className="grid-3">
          <Field
            label={t('PLZ')}
            required
            value={v.postal_code}
            error={e.postal_code}
            onChange={(ev) => form.set('postal_code', ev.target.value)}
          />
          <Field
            label={t('Ort')}
            required
            value={v.city}
            error={e.city}
            onChange={(ev) => form.set('city', ev.target.value)}
          />
          <Field
            label={t('Land')}
            value={v.country}
            error={e.country}
            onChange={(ev) => form.set('country', ev.target.value)}
          />
        </div>
        <div className="grid-2">
          <Field
            label={t('Mitgliedsnummer {e_im}', { e_im: tm.e_im })}
            value={v.club_number}
            error={e.club_number}
            onChange={(ev) => form.set('club_number', ev.target.value)}
          />
        </div>
      </fieldset>
      <p className="muted small">
        {member.contact_shared
          ? t('Kontaktdaten werden für alle {e_pl} gemeinsam gepflegt.', { e_pl: tm.e_pl })
          : t('Kontaktdaten gelten nur für {name}.', { name: org.name })}
      </p>
    </form>
  )
}

function MembershipTab({
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
  const departments = useLoad(() => orgApi.departmentChoices(org.id), [org.id])
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

      <Section title={t('Mitgliedsdauer')}>
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
      </Section>

      <Section title={t('Zeiträume')}>
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
      </Section>

      <Section title={t('Mitgliedsarten')}>
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
      </Section>

      {member.federation && (
        <Section title={member.federation.name}>
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
        </Section>
      )}

      {member.other_memberships && member.other_memberships.length > 0 && (
        <Section title={t('Mitgliedschaften in anderen {e_pl_dat}', { e_pl_dat: tm.e_pl_dat })}>
          <ul className="plain-list">
            {member.other_memberships.map((m, i) => (
              <li key={i}>
                <strong>{m.club}</strong> · {formatMemberDate(m.entry_date, precision)} –{' '}
                {m.exit_date ? formatMemberDate(m.exit_date, precision) : t('heute')}
              </li>
            ))}
          </ul>
        </Section>
      )}

      <Section title={org.department_label_plural}>
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
      </Section>
      <MaterialReferences
        kind="member"
        id={member.id}
        sourceBase={`/api/orgs/${org.id}/`}
        level={2}
        title={t('Ausgegebenes Material')}
        wide
      />
      {/* Eigene Region, unabhängig von Untereinheiten (UX-Audit 31.10. W08) */}
      <Section title={t('Kommunikation & Zustellung')}>
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
      </Section>
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

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="card card-wide">
      <h2>{title}</h2>
      {children}
    </div>
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

function AddPeriod({
  org,
  member,
  onAdded,
}: {
  org: OrgSummary
  member: MemberDetail
  onAdded: () => Promise<void>
}) {
  const [open, setOpen] = useState(false)
  const types = useLoad(() => memberApi.types(org.id), [org.id])
  const empty = { entry_date: '', exit_date: '', exit_reason: 'exit', member_type: '' }
  const form = useForm(empty)
  // Nachtrag vor dem Speichern nicht unbemerkt verlieren (UX-Audit 31.10. W01)
  const { dirty } = useChangesGuard(form.values, open)
  if (!open) {
    return (
      <button type="button" className="button button-ghost" onClick={() => setOpen(true)}>
        {t('Früheren Zeitraum nachtragen')}
      </button>
    )
  }
  async function save(ev: FormEvent) {
    ev.preventDefault()
    const { member_type, ...rest } = form.values
    const ok = await form.submit(() =>
      memberApi.addPeriod(org.id, member.id, {
        ...rest,
        member_type: member_type ? Number(member_type) : null,
      }),
    )
    if (ok) {
      form.setValues(empty)
      setOpen(false)
      await onAdded()
    }
  }
  return (
    <form className="subcard" onSubmit={save}>
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
          required
          value={form.values.exit_date}
          error={form.errors.exit_date}
          onChange={(e) => form.set('exit_date', e.target.value)}
        />
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
      </div>
      <SelectField
        label={t('Mitgliedsart in diesem Zeitraum')}
        value={form.values.member_type}
        error={form.errors.member_type}
        onChange={(e) => form.set('member_type', e.target.value)}
      >
        <option value="">{t('– unbekannt –')}</option>
        {types.data?.map((tmx) => (
          <option key={tmx.id} value={tmx.id}>
            {tmx.name}
          </option>
        ))}
      </SelectField>
      {orgTerms(org).dv_has && (
        <p className="muted small">
          {t('Nur Zeiten mit einer gemeldeten Art zählen für {dv_akk}.', {
            dv_akk: orgTerms(org).dv_akk,
          })}
        </p>
      )}
      {form.message?.kind === 'error' && <Alert kind="error">{form.message.text}</Alert>}
      <div className="button-row">
        <button type="submit" className="button button-primary" disabled={form.busy}>
          {t('Speichern')}
        </button>
        <button
          type="button"
          className="button button-ghost"
          onClick={() =>
            void confirmDiscard(dirty).then((yes) => {
              if (!yes) return
              form.setValues(empty)
              setOpen(false)
            })
          }
        >
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

function AddWithDate({
  label,
  options,
  onAdd,
  withEnd = false,
}: {
  label: string
  options: { id: number; name: string; needsEnd?: boolean }[]
  onAdd: (id: number, date: string, until: string | null) => Promise<void>
  // Optionales Ende, damit sich frühere Zeiten in einem Schritt nachtragen lassen
  withEnd?: boolean
}) {
  const [id, setId] = useState('')
  const [date, setDate] = useState(todayIso)
  const [until, setUntil] = useState('')
  const needsEnd = options.some((o) => String(o.id) === id && o.needsEnd)
  return (
    <form
      className="inline-add"
      onSubmit={(e) => {
        e.preventDefault()
        if (id)
          void onAdd(Number(id), date, until || null).then(() => {
            setId('')
            setUntil('')
          })
      }}
    >
      <select aria-label={label} value={id} onChange={(e) => setId(e.target.value)}>
        <option value="">{label} …</option>
        {options.map((o) => (
          <option key={o.id} value={o.id}>
            {o.name}
          </option>
        ))}
      </select>
      <input
        type="date"
        aria-label={t('ab')}
        value={date}
        onChange={(e) => setDate(e.target.value)}
      />
      {withEnd && (
        <input
          type="date"
          aria-label={t('bis (leer = heute)')}
          title={t('bis (leer = heute)')}
          value={until}
          min={date}
          required={needsEnd}
          onChange={(e) => setUntil(e.target.value)}
        />
      )}
      <button type="submit" className="button button-ghost">
        {t('Hinzufügen')}
      </button>
    </form>
  )
}

function RolesTab({
  org,
  member,
  canEdit,
  reload,
}: {
  org: OrgSummary
  member: MemberDetail
  canEdit: boolean
  reload: () => Promise<void>
}) {
  const canEditRoles = org.permissions.includes(PERM.rolesManage)
  const departments = useLoad(() => orgApi.departmentChoices(org.id), [org.id])
  // Vorstandsrollen besetzen im selben Dialog wie unter Ämter (Rollen-Vorschlag R2)
  const [assigning, setAssigning] = useState(false)
  const roles = useLoad(
    () => (assigning ? orgApi.roles(org.id) : Promise.resolve(null)),
    [org.id, assigning],
  )
  const assignments = useLoad(
    () => (assigning ? orgApi.assignments(org.id) : Promise.resolve(null)),
    [org.id, assigning],
  )
  const [error, setError] = useState<string | null>(null)
  const roleOptions =
    departments.data?.flatMap((d) =>
      d.roles.map((r) => ({
        id: r.id,
        name: t('{name} ({name2})', { name: r.name, name2: d.name }),
      })),
    ) ?? []

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
      {member.status === 'active' &&
        org.permissions.includes(PERM.loginsView) &&
        member.kind === 'organization' && (
          <OrganizationAccess
            orgId={org.id}
            member={member}
            canManage={canEdit && org.permissions.includes(PERM.loginsEdit)}
          />
        )}
      {member.status === 'active' &&
        org.permissions.includes(PERM.loginsView) &&
        member.kind !== 'organization' && (
          <MemberAccessSection
            key={`zugang-${member.id}`}
            orgId={org.id}
            memberId={member.id}
            hasEmail={!!member.contact?.email}
            contactEmail={member.contact?.email}
            canManage={canEdit && org.permissions.includes(PERM.loginsEdit)}
          />
        )}
      <Section title={t('Vorstandsrollen')}>
        {member.board_roles.length === 0 ? (
          <p className="muted">{t('Keine.')}</p>
        ) : (
          <ul className="plain-list">
            {member.board_roles.map((r) => (
              <li key={r.id}>
                <strong>{r.role_name}</strong> · {formatDate(r.valid_from)} –{' '}
                {r.valid_until ? formatDate(r.valid_until) : t('heute')}
              </li>
            ))}
          </ul>
        )}
        {canEditRoles && member.status === 'active' && (
          <button type="button" className="button button-ghost" onClick={() => setAssigning(true)}>
            {t('Rolle besetzen')}
          </button>
        )}
      </Section>
      {assigning && roles.data && assignments.data && (
        <AssignRoleDialog
          orgId={org.id}
          roles={roles.data}
          assignments={assignments.data}
          member={{
            id: member.id,
            first_name: member.first_name,
            last_name: member.last_name,
            email: member.contact?.email ?? '',
          }}
          onClose={() => setAssigning(false)}
          onDone={reload}
        />
      )}
      <Section
        title={t('Rollen in {x}', {
          x: org.department_terms?.pl_dat ?? org.department_label_plural,
        })}
      >
        {member.department_roles.length === 0 ? (
          <p className="muted">{t('Keine.')}</p>
        ) : (
          <ul className="plain-list">
            {member.department_roles.map((r) => (
              <li key={r.id}>
                <strong>{r.role_name}</strong> ({r.department_name}) · {formatDate(r.valid_from)} –{' '}
                {r.valid_until ? formatDate(r.valid_until) : t('heute')}
                {canEditRoles && !r.valid_until && (
                  <button
                    type="button"
                    className="link-button spaced"
                    onClick={() =>
                      void run(() =>
                        memberApi.endDepartmentRole(org.id, member.id, r.id, todayIso()),
                      )
                    }
                  >
                    {t('beenden')}
                  </button>
                )}
              </li>
            ))}
          </ul>
        )}
        {canEditRoles && roleOptions.length > 0 && (
          <AddWithDate
            label={t('Rolle besetzen')}
            options={roleOptions}
            onAdd={(id, date) =>
              run(() =>
                memberApi.addDepartmentRole(org.id, member.id, { role: id, valid_from: date }),
              )
            }
          />
        )}
        {error && <Alert kind="error">{error}</Alert>}
      </Section>
    </div>
  )
}

function HistoryTab({ orgId, memberId }: { orgId: number; memberId: number }) {
  const { data, error } = useLoad(() => memberApi.history(orgId, memberId), [orgId, memberId])
  const first = firstOfSet(data ?? [])
  if (error) return <Alert kind="error">{error}</Alert>
  if (!data) return <Loading />
  return (
    <Section title={t('Verlauf')}>
      {data.length === 0 ? (
        <p className="muted">{t('Noch keine Einträge.')}</p>
      ) : (
        <ul className="audit-list">
          {data.map((entry) => (
            <li key={entry.id}>
              <div>
                <strong>{entry.object_type}</strong> {entry.action_label}
              </div>
              <div className="muted small">
                {formatDateTime(entry.timestamp)} · {entry.user_email || t('System')}
                {entry.via ? t(' · über {via}', { via: entry.via }) : ''}
              </div>
              {Object.keys(entry.changes).length > 0 && (
                <ul className="changes small">
                  {Object.entries(entry.changes).map(([field, [before, after]]) => (
                    <li key={field}>
                      {field}: {String(before ?? '–')} → {String(after ?? '–')}
                    </li>
                  ))}
                </ul>
              )}
              <AuditUndo entry={entry} orgId={orgId} showAction={first.has(entry.id)} />
            </li>
          ))}
        </ul>
      )}
    </Section>
  )
}

/** Organisationen: ein Zugang je Ansprechpartner statt eines Zugangs für das Mitglied. */
function OrganizationAccess({
  orgId,
  member,
  canManage,
}: {
  orgId: number
  member: MemberDetail
  canManage: boolean
}) {
  const contacts = member.contact_persons ?? []
  if (contacts.length === 0)
    return (
      <div className="card card-wide">
        <h2>{t('Konto und Mitgliederbereich')}</h2>
        <p className="muted">
          {t(
            'Organisationen kommen über ihre Ansprechpartner in den Mitgliederbereich. Bitte zuerst unter „Stammdaten“ einen Ansprechpartner eintragen.',
          )}
        </p>
      </div>
    )
  return (
    <>
      {contacts.map((c) => (
        <MemberAccessSection
          key={`zugang-${member.id}-${c.id}`}
          orgId={orgId}
          memberId={member.id}
          contactId={c.id}
          title={t('Mitgliederbereich für {name}', { name: c.display_name })}
          hasEmail={!!c.contact_email}
          contactEmail={c.contact_email}
          canManage={canManage}
        />
      ))}
    </>
  )
}
