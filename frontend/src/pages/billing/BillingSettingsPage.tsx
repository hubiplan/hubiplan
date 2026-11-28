import { Link } from 'react-router-dom'
import { billingApi } from '../../api/billing.ts'
import type { BillingSettings, ProRataStep, Rhythm } from '../../api/billing.ts'
import { parseAmount } from '../../api/finance.ts'
import { useAutoSave, useForm } from '../../components/forms.ts'
import { Alert, Checkbox, Field, SaveStatus, SelectField, Loading } from '../../components/ui.tsx'
import { useOrg } from '../../org/OrgContext.tsx'
import { Why } from '../../learning/Aids.tsx'
import { t } from '../../i18n/index.ts'
import { useOrgBillingSettings } from './rulesHelpers.ts'

/** Abrechnungsrhythmus, Konto und Kategorie, Rechnungstexte, Umsatzsteuer, SEPA. */
export function BillingSettingsPage() {
  const { org, settings } = useOrgBillingSettings()
  const { refresh } = useOrg()
  if (settings.error) return <Alert kind="error">{settings.error}</Alert>
  if (!settings.data) return <Loading />
  const s = settings.data
  return (
    <SettingsCard
      key={org.id}
      orgId={org.id}
      settings={s}
      onSaved={(d) => {
        settings.setData(d)
        // Menü „Lastschriften“ ein- oder ausblenden
        if (d.sepa_enabled !== s.sepa_enabled) void refresh()
      }}
    />
  )
}

function SettingsCard({
  orgId,
  settings,
  onSaved,
}: {
  orgId: number
  settings: BillingSettings
  onSaved: (s: BillingSettings) => void
}) {
  const form = useForm({
    rhythm: settings.rhythm,
    due_days: String(settings.due_days),
    pro_rata_step: settings.pro_rata_step,
    account: settings.account ? String(settings.account) : '',
    category: settings.category ? String(settings.category) : '',
    intro_text: settings.intro_text,
    footer_text: settings.footer_text,
    qr_code: settings.qr_code,
    vat_enabled: settings.vat_enabled,
    vat_rate: settings.vat_rate.replace('.', ','),
    tax_number: settings.tax_number,
    sepa_enabled: settings.sepa_enabled,
    creditor_id: settings.creditor_id,
    prenotification_days: String(settings.prenotification_days),
    einvoice_members: settings.einvoice_members,
    einvoice_contact: settings.einvoice_contact,
    einvoice_phone: settings.einvoice_phone,
    einvoice_email: settings.einvoice_email,
    einvoice_identifier: settings.einvoice_identifier,
  })
  const v = form.values
  const canEdit = settings.can_edit

  const auto = useAutoSave(
    form,
    (_changes, values) =>
      billingApi.updateSettings(orgId, {
        ...values,
        due_days: Number(values.due_days) || 0,
        account: values.account ? Number(values.account) : null,
        category: values.category ? Number(values.category) : null,
        vat_rate: parseAmount(values.vat_rate) || '19',
        prenotification_days: Number(values.prenotification_days) || 14,
      }),
    { enabled: canEdit, onSaved: (result) => onSaved(result as BillingSettings) },
  )

  return (
    <form className="card card-wide" onSubmit={(e) => e.preventDefault()}>
      <h2>{t('Abrechnung und Rechnung')}</h2>
      {canEdit && <SaveStatus auto={auto} />}
      <div className="aid-row">
        <Why k="billing_cycle" />
        <Why k="due_days" />
        <Why k="pro_rata" />
        <Why k="giro_qr" />
      </div>
      <fieldset disabled={!canEdit}>
        <div className="grid-3">
          <SelectField
            label={t('Abrechnungsrhythmus')}
            value={v.rhythm}
            onChange={(e) => form.set('rhythm', e.target.value as Rhythm)}
          >
            {settings.rhythms.map((r) => (
              <option key={r.value} value={r.value}>
                {r.label}
              </option>
            ))}
          </SelectField>
          <Field
            label={t('Zahlungsziel (Tage)')}
            type="number"
            min={0}
            value={v.due_days}
            error={form.errors.due_days}
            onChange={(e) => form.set('due_days', e.target.value)}
          />
          <SelectField
            label={t('Beitrag bei Eintritt im laufenden Zeitraum')}
            value={v.pro_rata_step}
            hint={t('Angefangene Abschnitte zählen voll, gerechnet ab Beginn des Geschäftsjahres')}
            onChange={(e) => form.set('pro_rata_step', e.target.value as ProRataStep)}
          >
            <option value="off">{t('voller Beitrag (nicht anteilig)')}</option>
            <option value="month">{t('anteilig je angefangenem Monat')}</option>
            <option value="quarter">{t('anteilig je angefangenem Quartal')}</option>
            <option value="halfyear">{t('anteilig je angefangenem Halbjahr')}</option>
          </SelectField>
          <SelectField
            label={t('Konto für Überweisungen')}
            value={v.account}
            error={form.errors.account}
            hint={t('steht mit IBAN auf der Rechnung')}
            onChange={(e) => form.set('account', e.target.value)}
          >
            <option value="">{t('kein Konto')}</option>
            {settings.accounts
              .filter((a) => a.kind !== 'cash')
              .map((a) => (
                <option key={a.id} value={a.id}>
                  {a.name}
                  {a.has_iban ? '' : t(' (ohne IBAN)')}
                </option>
              ))}
          </SelectField>
          <SelectField
            label={t('Kategorie für Zahlungseingänge')}
            value={v.category}
            error={form.errors.category}
            hint={t('Zahlungen werden damit in der Kasse gebucht')}
            onChange={(e) => form.set('category', e.target.value)}
          >
            <option value="">{t('bitte wählen')}</option>
            {settings.categories.map((c) => (
              <option key={c.id} value={c.id}>
                {c.name}
              </option>
            ))}
          </SelectField>
          <div className="field">
            <span>&nbsp;</span>
            <Checkbox
              label={t('QR-Code für die Banking-App aufdrucken')}
              checked={v.qr_code}
              onChange={(val) => form.set('qr_code', val)}
            />
          </div>
        </div>
        {settings.accounts.length === 0 && (
          <p className="muted small">
            {t('Konten und Kategorien legst du hier an:')}{' '}
            <Link to="/finanzen/einrichtung/konten">{t('Einrichtung › Konten')}</Link>.
          </p>
        )}
        {/* Im Arbeitsbereich einer Untereinheit gibt es keine Lastschrift */}
        {settings.org_type !== 'unit' && (
          <>
            <h3>{t('SEPA-Lastschrift')}</h3>
            <div className="aid-row">
              <Why k="sepa_use" />
              {v.sepa_enabled && <Why k="prenotification" />}
            </div>
            <Checkbox
              label={t(
                'SEPA-Lastschrift nutzen (Mandate, Lastschriftläufe, Mandat im Mitgliederbereich)',
              )}
              checked={v.sepa_enabled}
              onChange={(val) => form.set('sepa_enabled', val)}
            />
            {v.sepa_enabled && (
              <div className="grid-3">
                <Field
                  label={t('Gläubiger-Identifikationsnummer')}
                  placeholder={t('z. B. DE98ZZZ09999999999')}
                  value={v.creditor_id}
                  error={form.errors.creditor_id}
                  hint={t('bei der Bundesbank beantragt')}
                  onChange={(e) => form.set('creditor_id', e.target.value)}
                />
                <Field
                  label={t('Vorabankündigung (Tage vor dem Einzug)')}
                  type="number"
                  min={1}
                  max={30}
                  value={v.prenotification_days}
                  error={form.errors.prenotification_days}
                  onChange={(e) => form.set('prenotification_days', e.target.value)}
                />
              </div>
            )}
            <p className="muted small">
              {v.sepa_enabled
                ? t(
                    'Eingezogen wird auf das Konto für Überweisungen oben. Ohne Gläubiger-ID ist keine Lastschrift möglich.',
                  )
                : t(
                    'Ausgeschaltet erscheinen Lastschriften und Mandate nirgends in der Oberfläche. Bereits erfasste Mandate bleiben gespeichert.',
                  )}
            </p>
          </>
        )}
        <h3>{t('Umsatzsteuer')}</h3>
        <Why k="vat_show" />
        <div className="grid-3">
          <div className="field">
            <span>&nbsp;</span>
            <Checkbox
              label={t('Umsatzsteuer auf Rechnungen ausweisen (nur für steuerpflichtige Posten)')}
              checked={v.vat_enabled}
              onChange={(val) => form.set('vat_enabled', val)}
            />
          </div>
          {v.vat_enabled && (
            <Field
              label={t('üblicher Steuersatz (%)')}
              inputMode="decimal"
              value={v.vat_rate}
              error={form.errors.vat_rate}
              onChange={(e) => form.set('vat_rate', e.target.value)}
            />
          )}
          {/* Auch ohne ausgewiesene Umsatzsteuer nötig: Leistungs- und E-Rechnungen nennen sie */}
          <Field
            label={t('Steuernummer oder USt-IdNr.')}
            value={v.tax_number}
            error={form.errors.tax_number}
            onChange={(e) => form.set('tax_number', e.target.value)}
          />
        </div>
        <p className="muted small">
          {t(
            'Mitgliedsbeiträge sind nicht steuerbar. Den Steuersatz wählst du je Posten, etwa für Verkäufe im wirtschaftlichen Geschäftsbetrieb. Die Beträge sind Bruttobeträge.',
          )}
        </p>
        {settings.org_type !== 'unit' && (
          <>
            <h3>{t('Angaben des Rechnungsstellers')}</h3>
            <p className="muted small">
              {t(
                'Leistungsrechnungen und E-Rechnungen brauchen eine Kontaktperson mit Telefon, eine Kennung und die Steuernummer. Hier hinterlegt, sind sie in jeder neuen Rechnung vorbelegt.',
              )}
            </p>
            <div className="grid-2">
              <Field
                label={t('Ansprechpartner für Rechnungsfragen')}
                value={v.einvoice_contact}
                error={form.errors.einvoice_contact}
                hint={t('leer: Kontakt des Vereins')}
                onChange={(e) => form.set('einvoice_contact', e.target.value)}
              />
              <Field
                label={t('Telefon für Rechnungsfragen')}
                value={v.einvoice_phone}
                error={form.errors.einvoice_phone}
                hint={t('leer: Kontakt des Vereins')}
                onChange={(e) => form.set('einvoice_phone', e.target.value)}
              />
              <Field
                label={t('E-Mail für Rechnungsfragen')}
                type="email"
                value={v.einvoice_email}
                error={form.errors.einvoice_email}
                hint={t('leer: Kontakt des Vereins')}
                onChange={(e) => form.set('einvoice_email', e.target.value)}
              />
              <Field
                label={t('Kennung des Rechnungsstellers')}
                value={v.einvoice_identifier}
                error={form.errors.einvoice_identifier}
                hint={t('z. B. Vereinsregisternummer; leer: aus dem Impressum')}
                onChange={(e) => form.set('einvoice_identifier', e.target.value)}
              />
            </div>
            <h3>{t('E-Rechnung für Behörden')}</h3>
            <Checkbox
              label={t('Rechnungen an Mitglieder mit Leitweg-ID als E-Rechnung (XRechnung)')}
              checked={v.einvoice_members}
              onChange={(val) => form.set('einvoice_members', val)}
            />
            <p className="muted small">
              {t(
                'Die Leitweg-ID steht in der Rechnungsanschrift des Mitglieds. Beim Festschreiben entsteht dann eine geprüfte XRechnung; die Rechnungsmail trägt sie als Anhang.',
              )}
            </p>
          </>
        )}
        <div className="grid-2">
          <label className="field">
            <span>{t('Text vor den Posten')}</span>
            <textarea
              rows={3}
              value={v.intro_text}
              onChange={(e) => form.set('intro_text', e.target.value)}
            />
          </label>
          <label className="field">
            <span>{t('Text unter der Rechnung')}</span>
            <textarea
              rows={3}
              placeholder={t('z. B. Vereinsregister, Steuernummer, Dank')}
              value={v.footer_text}
              onChange={(e) => form.set('footer_text', e.target.value)}
            />
          </label>
        </div>
      </fieldset>
    </form>
  )
}
