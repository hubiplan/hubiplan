import { useState } from 'react'
import type {
  ApiAccessInput,
  ApiAccessList,
  ApiScope,
  LegalBasis,
  MemberFieldGroup,
} from '../../api/apiAccess.ts'
import { ApiError } from '../../api/client.ts'
import { errorMessage } from '../../components/forms.ts'
import { Alert, Checkbox, Field, SelectField } from '../../components/ui.tsx'
import { t } from '../../i18n/index.ts'
import { TextArea } from './TextArea.tsx'
import { basisLabel, inDays, type Draft } from './apiAccessHelpers.ts'

const REPORT = 'verbandsmeldung.lesen'
const MEMBERS = 'mitglieder.lesen'

function fieldLabel(group: MemberFieldGroup): string {
  if (group === 'contact') return t('Kontakt und Anschrift')
  if (group === 'membership') return t('Mitgliedschaft')
  return t('Untereinheiten')
}

function fieldHint(group: MemberFieldGroup): string {
  if (group === 'contact') return t('E-Mail, Telefon, Straße, PLZ, Ort')
  if (group === 'membership') return t('Eintritt, Austritt, Mitgliedsart, Verbandsnummer')
  return t('Züge, Abteilungen und Gruppen des Mitglieds')
}

function inputOf(d: Draft): ApiAccessInput {
  return {
    name: d.name.trim(),
    purpose: d.purpose.trim(),
    recipient: d.recipient.trim(),
    scopes: d.scopes,
    unit: d.unit ? Number(d.unit) : null,
    expires_at: d.expires,
    allowed_networks: d.networks
      .split(/[\n,;]+/)
      .map((line) => line.trim())
      .filter(Boolean),
    embeddable: d.embeddable,
    partner: d.partner ? Number(d.partner) : null,
    legal_basis: d.basis,
    legal_confirmed: d.confirmed,
    third_country: d.thirdCountry,
    member_fields: d.memberFields,
    only_active: d.onlyActive,
    adults_only: d.adultsOnly,
    report_level: d.reportLevel,
    webhook_url: d.hookUrl.trim(),
    webhook_events: d.hookEvents,
  }
}

export function AccessForm({
  list,
  initial,
  submitLabel,
  onSubmit,
  onCancel,
}: {
  list: ApiAccessList
  initial: Draft
  submitLabel: string
  onSubmit: (input: ApiAccessInput) => Promise<void>
  onCancel: () => void
}) {
  const [d, setD] = useState(initial)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [errors, setErrors] = useState<Record<string, string>>({})
  const set = <K extends keyof Draft>(key: K, value: Draft[K]) => setD({ ...d, [key]: value })
  const toggle = (scope: string, on: boolean) => {
    let scopes = on ? [...d.scopes, scope] : d.scopes.filter((s) => s !== scope)
    // Ein Bereich, der einen anderen voraussetzt, nimmt ihn mit bzw. fällt mit ihm weg
    const needs = list.scopes.find((s) => s.scope === scope)?.needs
    if (on && needs && !scopes.includes(needs)) scopes = [...scopes, needs]
    if (!on) scopes = scopes.filter((s) => list.scopes.find((x) => x.scope === s)?.needs !== scope)
    set('scopes', scopes)
  }
  const chooseUnit = (unit: string) => {
    const allowed = new Set(list.scopes.filter((s) => !unit || s.unit_ok).map((s) => s.scope))
    setD({ ...d, unit, scopes: d.scopes.filter((s) => allowed.has(s)) })
  }
  const personalScopes = new Set(list.scopes.filter((s) => s.personal).map((s) => s.scope))
  const withReport = d.scopes.includes(REPORT)
  const personal =
    d.scopes.some((s) => personalScopes.has(s)) || (withReport && d.reportLevel === 'b')
  const limits = d.scopes.some((s) => personalScopes.has(s))
  // Die Bestätigung gilt für genau diesen Empfänger und diese Rechtsgrundlage
  const choose = (change: Partial<Draft>) => setD({ ...d, ...change, confirmed: false })
  const hookEvents = list.webhook_events.filter((e) => d.scopes.includes(e.scope))
  const toggleIn = <T,>(items: T[], item: T, on: boolean) =>
    on ? [...items, item] : items.filter((x) => x !== item)
  const scopeRow = (s: ApiScope) => {
    const blocked = !!d.unit && !s.unit_ok
    return (
      <div key={s.scope}>
        <Checkbox
          label={s.label}
          checked={d.scopes.includes(s.scope)}
          disabled={blocked}
          hint={blocked ? t('nur für die ganze Einheit') : undefined}
          onChange={(on) => toggle(s.scope, on)}
        />
        <div className="muted small">
          {s.personal && <span className="badge badge-warn">{t('Personendaten')}</span>}{' '}
          {s.description}
        </div>
      </div>
    )
  }

  return (
    <form
      className="stack"
      onSubmit={async (e) => {
        e.preventDefault()
        setBusy(true)
        setError(null)
        setErrors({})
        try {
          await onSubmit(inputOf(d))
        } catch (err) {
          if (err instanceof ApiError) setErrors(err.fieldErrors)
          setError(errorMessage(err))
        } finally {
          setBusy(false)
        }
      }}
    >
      <div className="grid-2">
        <Field
          label={t('Name')}
          required
          maxLength={100}
          placeholder={t('z. B. Meldung an den Verband')}
          error={errors.name}
          value={d.name}
          onChange={(e) => set('name', e.target.value)}
        />
        <Field
          label={t('Empfänger')}
          maxLength={200}
          hint={t('Wer den Schlüssel bekommt, z. B. Firma oder Person')}
          error={errors.recipient}
          value={d.recipient}
          onChange={(e) => set('recipient', e.target.value)}
        />
      </div>
      <Field
        label={t('Zweck')}
        maxLength={300}
        hint={t('Wozu das andere Programm die Daten braucht')}
        error={errors.purpose}
        value={d.purpose}
        onChange={(e) => set('purpose', e.target.value)}
      />
      {list.units.length > 0 && (
        <SelectField
          label={t('Gilt für')}
          hint={t(
            'Ein Zugang für eine Untereinheit sieht nur deren Daten und die ihrer Untergruppen.',
          )}
          error={errors.unit}
          value={d.unit}
          onChange={(e) => chooseUnit(e.target.value)}
        >
          <option value="">{t('Ganze Einheit')}</option>
          {list.units.map((u) => (
            <option key={u.id} value={String(u.id)}>
              {u.name}
            </option>
          ))}
        </SelectField>
      )}
      <fieldset className="stack-sm">
        <legend>{t('Was der Zugang lesen darf')}</legend>
        {list.scopes.filter((s) => !s.write).map(scopeRow)}
        {errors.scopes && <small className="field-error">{errors.scopes}</small>}
      </fieldset>
      {list.scopes.some((s) => s.write) && (
        <fieldset className="stack-sm">
          <legend>{t('Was der Zugang schreiben darf')}</legend>
          <p className="muted small">
            {t(
              'Geschrieben wird nur Unkritisches oder ein Vorschlag bzw. Entwurf, den jemand in HUBIplan übernimmt. Nichts wird gelöscht oder versendet. Was der Zugang schreibt, steht im Änderungsprotokoll.',
            )}
          </p>
          {list.scopes.filter((s) => s.write).map(scopeRow)}
        </fieldset>
      )}
      {withReport && (
        <SelectField
          label={t('Verbandsmeldung')}
          hint={t(
            'Nur Zahlen: Anzahl nach aktiv, passiv und Geburtsmonat. Namentlich: dazu Name, Geburtsdatum, Verbandsnummer, Mitgliedsart und Eintritt.',
          )}
          error={errors.report_level}
          value={d.reportLevel}
          onChange={(e) => set('reportLevel', e.target.value === 'b' ? 'b' : 'a')}
        >
          <option value="a">{t('nur Zahlen')}</option>
          <option value="b">{t('namentlich')}</option>
        </SelectField>
      )}
      {d.scopes.includes(MEMBERS) && (
        <fieldset className="stack-sm">
          <legend>{t('Was zu jedem Mitglied dazukommt')}</legend>
          <p className="muted small">
            {t(
              'Immer dabei: Name, Titel, Geschlecht, Geburtsdatum und Mitgliedsnummer. Nie dabei: Bankdaten, Bemerkungen, Fotos und Zusatzfelder.',
            )}
          </p>
          {list.member_fields.map((group) => (
            <div key={group}>
              <Checkbox
                label={fieldLabel(group)}
                checked={d.memberFields.includes(group)}
                onChange={(on) => set('memberFields', toggleIn(d.memberFields, group, on))}
              />
              <div className="muted small">{fieldHint(group)}</div>
            </div>
          ))}
        </fieldset>
      )}
      {limits && (
        <fieldset className="stack-sm">
          <legend>{t('Welche Mitglieder')}</legend>
          <Checkbox
            label={t('Nur aktuelle Mitglieder')}
            checked={d.onlyActive}
            onChange={(value) => set('onlyActive', value)}
          />
          <Checkbox
            label={t('Nur Volljährige')}
            checked={d.adultsOnly}
            onChange={(value) => set('adultsOnly', value)}
          />
        </fieldset>
      )}
      {personal && (
        <fieldset className="stack-sm">
          <legend>{t('Empfänger und Rechtsgrundlage')}</legend>
          <p className="muted small">
            {t(
              'Dieser Zugang gibt Personendaten heraus. Dafür braucht es einen benannten Empfänger und eine Rechtsgrundlage. Jeder Abruf wird protokolliert.',
            )}
          </p>
          <SelectField
            label={t('Empfänger (Geschäftspartner)')}
            hint={
              list.partners.length === 0
                ? t('Lege den Empfänger zuerst unter Verwaltung › Geschäftspartner an.')
                : undefined
            }
            error={errors.partner}
            value={d.partner}
            onChange={(e) => choose({ partner: e.target.value })}
          >
            <option value="">{t('Bitte wählen')}</option>
            {list.partners.map((p) => (
              <option key={p.id} value={String(p.id)}>
                {p.name}
              </option>
            ))}
          </SelectField>
          <SelectField
            label={t('Rechtsgrundlage')}
            hint={t(
              'Auftragsverarbeitung: Der Empfänger arbeitet nur in eurem Auftrag, etwa ein Dienstleister. Übermittlung: Der Empfänger entscheidet selbst über die Daten, etwa der Dachverband nach seiner Satzung.',
            )}
            error={errors.legal_basis}
            value={d.basis}
            onChange={(e) => choose({ basis: e.target.value as LegalBasis })}
          >
            <option value="">{t('Bitte wählen')}</option>
            <option value="processing">{basisLabel('processing')}</option>
            <option value="transfer">{basisLabel('transfer')}</option>
          </SelectField>
          <Checkbox
            label={t('Empfänger außerhalb der EU')}
            checked={d.thirdCountry}
            onChange={(value) => set('thirdCountry', value)}
          />
          <Checkbox
            label={
              d.basis === 'processing'
                ? t(
                    'Ich bestätige: Mit dem Empfänger besteht ein Vertrag zur Auftragsverarbeitung.',
                  )
                : t(
                    'Ich bestätige: Für die Weitergabe an den Empfänger gibt es eine Rechtsgrundlage.',
                  )
            }
            checked={d.confirmed}
            onChange={(value) => set('confirmed', value)}
          />
          {errors.legal_confirmed && (
            <small className="field-error">{errors.legal_confirmed}</small>
          )}
        </fieldset>
      )}
      <div className="grid-2">
        <Field
          label={t('Gültig bis')}
          type="date"
          required
          min={inDays(1)}
          max={inDays(list.max_days)}
          hint={t('Höchstens {n} Tage. Danach legst du den Zugang neu an oder verlängerst ihn.', {
            n: list.max_days,
          })}
          error={errors.expires_at}
          value={d.expires}
          onChange={(e) => set('expires', e.target.value)}
        />
      </div>
      <TextArea
        label={t('Erlaubte Adressen (optional)')}
        hint={t(
          'Eine IP-Adresse oder ein Netz je Zeile, z. B. 203.0.113.7 oder 203.0.113.0/24. Leer: von überall.',
        )}
        error={errors.allowed_networks}
        value={d.networks}
        onChange={(value) => set('networks', value)}
      />
      <Checkbox
        label={t('Aus fremden Webseiten aufrufbar')}
        hint={t(
          'Nur für Daten, die ohnehin öffentlich sind: Der Schlüssel steht dann im Quelltext der Webseite.',
        )}
        checked={d.embeddable}
        onChange={(value) => set('embeddable', value)}
      />
      {errors.embeddable && <small className="field-error">{errors.embeddable}</small>}
      {hookEvents.length > 0 && (
        <fieldset className="stack-sm">
          <legend>{t('Benachrichtigen bei Änderungen (optional)')}</legend>
          <Field
            label={t('Adresse für Benachrichtigungen')}
            type="url"
            maxLength={500}
            placeholder="https://"
            hint={t(
              'HUBIplan meldet dorthin nur, dass sich etwas geändert hat, nie Inhalte. Das andere Programm holt die Daten danach mit seinem Schlüssel ab.',
            )}
            error={errors.webhook_url}
            value={d.hookUrl}
            onChange={(e) => set('hookUrl', e.target.value)}
          />
          {d.hookUrl.trim() !== '' &&
            hookEvents.map((e) => (
              <Checkbox
                key={e.event}
                label={e.label}
                checked={d.hookEvents.includes(e.event)}
                onChange={(on) => set('hookEvents', toggleIn(d.hookEvents, e.event, on))}
              />
            ))}
        </fieldset>
      )}
      {error && <Alert kind="error">{error}</Alert>}
      <div className="button-row">
        <button type="submit" className="button button-primary" disabled={busy}>
          {submitLabel}
        </button>
        <button type="button" className="button" onClick={onCancel}>
          {t('Abbrechen')}
        </button>
      </div>
    </form>
  )
}
