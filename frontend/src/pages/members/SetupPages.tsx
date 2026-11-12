// Mitglieder › Einrichtung: mitgliederbezogene Einstellungen der Organisation
// (Jubiläen und Dauer, Mitgliederbereich und Fotos). Gespeichert wird wie im
// Organisationsformular automatisch, aber nur mit den Feldern dieser Seite.
import type { ReactNode } from 'react'
import { orgApi, PERM } from '../../api/orgs.ts'
import type { CancellationEnd, MemberSettings } from '../../api/orgs.ts'
import { ListInput } from '../../components/ListField.tsx'
import { parseNumberList } from '../../components/lists.ts'
import { DATE_PRECISION_OPTIONS, useAutoSave, useForm, useLoad } from '../../components/forms.ts'
import type { DatePrecision } from '../../components/forms.ts'
import { Alert, Checkbox, SaveStatus, SelectField, Loading } from '../../components/ui.tsx'
import { useActiveOrg, useOrg } from '../../org/OrgContext.tsx'
import { useTerms } from '../../org/terms.ts'
import { t, tn } from '../../i18n/index.ts'

type Form = ReturnType<typeof useForm<MemberSettings>>

const DURATION_FIELDS: (keyof MemberSettings)[] = [
  'jubilee_years',
  'unit_jubilee_years',
  'date_precision',
  'federation_duration_rule',
]
const PORTAL_FIELDS: (keyof MemberSettings)[] = [
  'member_portal_enabled',
  'contact_changes_need_approval',
  'member_cancellation_enabled',
  'cancellation_notice_months',
  'cancellation_period_end',
  'photo_approval_required',
  'card_wallet_enabled',
]

/** Lädt die Organisation und zeigt ein automatisch speicherndes Teilformular. */
function OrgSettingsCard({
  fields,
  title,
  children,
}: {
  fields: (keyof MemberSettings)[]
  title: string
  children: (form: Form, detail: MemberSettings) => ReactNode
}) {
  const org = useActiveOrg()
  const { data, error, setData } = useLoad(() => orgApi.memberSettings(org.id), [org.id])
  if (error) return <Alert kind="error">{error}</Alert>
  if (!data) return <Loading />
  return (
    <SettingsForm key={data.id} detail={data} fields={fields} title={title} onSaved={setData}>
      {children}
    </SettingsForm>
  )
}

function SettingsForm({
  detail,
  fields,
  title,
  onSaved,
  children,
}: {
  detail: MemberSettings
  fields: (keyof MemberSettings)[]
  title: string
  onSaved: (d: MemberSettings) => void
  children: (form: Form, detail: MemberSettings) => ReactNode
}) {
  const { can, refresh } = useOrg()
  const editable = can(PERM.orgEdit)
  const form = useForm(detail)
  const auto = useAutoSave(
    form,
    (changes) => {
      const payload = Object.fromEntries(
        fields.filter((key) => key in changes).map((key) => [key, changes[key]]),
      ) as Partial<MemberSettings>
      return orgApi.updateMemberSettings(detail.id, payload)
    },
    {
      enabled: editable,
      onSaved: (saved) => {
        onSaved(saved as MemberSettings)
        void refresh()
      },
    },
  )
  return (
    <form className="card card-wide" onSubmit={(e) => e.preventDefault()}>
      {editable && <SaveStatus auto={auto} />}
      <h2>{title}</h2>
      <fieldset disabled={!editable}>{children(form, detail)}</fieldset>
      {!editable && (
        <p className="muted small">{t('Du kannst diese Angaben ansehen, aber nicht ändern.')}</p>
      )}
    </form>
  )
}

/** Jubiläumsstufen, Genauigkeit und (Dachverband) die Regel für die Dauer. */
export function MemberDurationSettings() {
  const tm = useTerms()
  return (
    <OrgSettingsCard fields={DURATION_FIELDS} title={t('Jubiläen und Mitgliedsdauer')}>
      {({ values: v, set, errors }, detail) => (
        <>
          <ListInput
            label={t('Jubiläumsstufen (Jahre, durch Komma getrennt)')}
            value={v.jubilee_years}
            parse={parseNumberList}
            error={errors.jubilee_years}
            onChange={(years) => set('jubilee_years', years)}
          />
          <ListInput
            label={t('Jubiläen {e_gen} und der {pl} (Jahre seit Gründung)', {
              e_gen: tm.e_gen,
              pl: tm.pl,
            })}
            value={v.unit_jubilee_years ?? []}
            parse={parseNumberList}
            error={errors.unit_jubilee_years}
            hint={t(
              'Gezählt wird ab dem Gründungsjahr, jahresgenau (z. B. 100 Jahre im ganzen Jahr).',
            )}
            onChange={(years) => set('unit_jubilee_years', years)}
          />
          <SelectField
            label={t('Genauigkeit für Mitgliedschaften und Jubiläen')}
            value={v.date_precision}
            error={errors.date_precision}
            hint={t(
              'Gilt für die Anzeige von Ein- und Austritt und für die Jubiläen. Gespeichert wird immer tagesgenau. Jahresgenau: Eintritt 2001 ergibt 25 Jahre im ganzen Jahr 2026.',
            )}
            onChange={(e) => set('date_precision', e.target.value as DatePrecision)}
          >
            {DATE_PRECISION_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </SelectField>
          {detail.type === 'federation' && (
            <SelectField
              label={t('Was zählt für die Dauer {e_im}?', { e_im: tm.e_im })}
              value={v.federation_duration_rule}
              error={errors.federation_duration_rule}
              onChange={(e) =>
                set(
                  'federation_duration_rule',
                  e.target.value as MemberSettings['federation_duration_rule'],
                )
              }
            >
              <option value="all_reported">{t('alle gemeldeten Zeiten')}</option>
              <option value="active_reported">{t('nur gemeldete aktive Zeiten')}</option>
            </SelectField>
          )}
        </>
      )}
    </OrgSettingsCard>
  )
}

const NOTICE_MONTHS = [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 18, 24]

function cancellationEnds(): { value: CancellationEnd; label: string }[] {
  return [
    { value: 'any', label: t('zu jedem Tag') },
    { value: 'month', label: t('zum Monatsende') },
    { value: 'quarter', label: t('zum Quartalsende') },
    { value: 'half_year', label: t('zum Halbjahresende') },
    { value: 'year', label: t('zum Ende des Geschäftsjahres') },
  ]
}

/** Mitgliederbereich (Anmeldung der Mitglieder), Datenänderungen, Kündigung und Fotos. */
export function MemberPortalSettings() {
  const tm = useTerms()
  return (
    <OrgSettingsCard fields={PORTAL_FIELDS} title={t('Mitgliederbereich und Fotos')}>
      {({ values: v, set }, detail) => (
        <>
          <h3>{t('Zugänge für Mitglieder')}</h3>
          <Checkbox
            label={t(
              'Mitgliederbereich: Mitglieder können sich anmelden, ihre Daten ansehen und Änderungen melden',
            )}
            checked={v.member_portal_enabled}
            onChange={(val) => set('member_portal_enabled', val)}
          />
          <Checkbox
            label={t(
              'Änderungen der Mitglieder an Kontaktdaten und Anschrift erst nach Bestätigung durch {e_akk} übernehmen (sonst gelten sie sofort)',
              { e_akk: tm.e_akk },
            )}
            checked={v.contact_changes_need_approval}
            onChange={(val) => set('contact_changes_need_approval', val)}
          />
          <h3>{t('Kündigung durch das Mitglied')}</h3>
          <Checkbox
            label={t(
              'Mitglieder können ihre Mitgliedschaft im Mitgliederbereich kündigen; {e_nom} bestätigt den Austritt',
              { e_nom: tm.e_nom },
            )}
            checked={v.member_cancellation_enabled}
            onChange={(val) => set('member_cancellation_enabled', val)}
          />
          {v.member_cancellation_enabled && (
            <div className="grid-2">
              <SelectField
                label={t('Kündigungsfrist')}
                value={String(v.cancellation_notice_months)}
                onChange={(e) => set('cancellation_notice_months', Number(e.target.value))}
              >
                {NOTICE_MONTHS.map((n) => (
                  <option key={n} value={n}>
                    {n === 0 ? t('keine Kündigungsfrist') : tn('{n} Monat', '{n} Monate', n)}
                  </option>
                ))}
              </SelectField>
              <SelectField
                label={t('Austritt wirksam')}
                value={v.cancellation_period_end}
                hint={t(
                  'Wie in der Satzung. Quartal, Halbjahr und Jahr zählen ab Beginn des Geschäftsjahres.',
                )}
                onChange={(e) => set('cancellation_period_end', e.target.value as CancellationEnd)}
              >
                {cancellationEnds().map((o) => (
                  <option key={o.value} value={o.value}>
                    {o.label}
                  </option>
                ))}
              </SelectField>
            </div>
          )}
          <h3>{t('Mitgliederfotos')}</h3>
          <Checkbox
            label={t(
              'Fotos, die Mitglieder über ihren Upload-Link hochladen, erst nach Freigabe durch den Vorstand anzeigen',
            )}
            checked={v.photo_approval_required}
            onChange={(val) => set('photo_approval_required', val)}
          />
          {detail.wallet_available && (
            <>
              <h3>{t('Mitgliedsausweis')}</h3>
              <Checkbox
                label={t(
                  'Mitglieder können ihren Ausweis in Apple Wallet oder Google Wallet speichern',
                )}
                checked={v.card_wallet_enabled}
                onChange={(val) => set('card_wallet_enabled', val)}
              />
              <p className="muted small">
                {t(
                  'Ausschalten macht gespeicherte Google-Wallet-Pässe ungültig. Apple-Pässe bleiben auf dem Telefon; der QR-Code darauf zeigt weiter den aktuellen Stand der Mitgliedschaft.',
                )}
              </p>
            </>
          )}
        </>
      )}
    </OrgSettingsCard>
  )
}
