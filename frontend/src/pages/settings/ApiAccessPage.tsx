// Einstellungen › API-Zugänge: Schlüssel, mit denen andere Programme (etwa die Software
// eines Dachverbands oder eine eigene Webseite) Daten dieser Einheit lesen und, wenn eigens
// angekreuzt, schreiben (docs/api.md).
// Der Schlüssel steht genau einmal auf der Seite: nach dem Anlegen und nach dem Wechsel.
import { useState } from 'react'
import { apiAccessApi } from '../../api/apiAccess.ts'
import type {
  ApiAccess,
  ApiAccessInput,
  ApiAccessList,
  ApiAccessWithKey,
  ApiScope,
  LegalBasis,
  MemberFieldGroup,
} from '../../api/apiAccess.ts'
import { ApiError } from '../../api/client.ts'
import { confirmDialog } from '../../components/dialog.ts'
import { errorMessage, formatDate, formatDateTime, useLoad } from '../../components/forms.ts'
import { Alert, Checkbox, Field, LoadError, Loading, SelectField } from '../../components/ui.tsx'
import { useActiveOrg } from '../../org/OrgContext.tsx'
import { t } from '../../i18n/index.ts'
import { TextArea } from './TextArea.tsx'

interface Draft {
  name: string
  purpose: string
  recipient: string
  scopes: string[]
  unit: string
  expires: string
  networks: string
  embeddable: boolean
  partner: string
  basis: LegalBasis
  confirmed: boolean
  thirdCountry: boolean
  memberFields: MemberFieldGroup[]
  onlyActive: boolean
  adultsOnly: boolean
  reportLevel: 'a' | 'b'
  hookUrl: string
  hookEvents: string[]
}

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

function basisLabel(basis: LegalBasis): string {
  if (basis === 'processing') return t('Auftragsverarbeitung (Vertrag nach Art. 28 DSGVO)')
  if (basis === 'transfer') return t('Übermittlung an einen eigenen Verantwortlichen')
  return ''
}

function day(date: Date): string {
  const two = (n: number) => String(n).padStart(2, '0')
  return `${date.getFullYear()}-${two(date.getMonth() + 1)}-${two(date.getDate())}`
}

function inDays(days: number): string {
  const date = new Date()
  date.setDate(date.getDate() + days)
  return day(date)
}

function emptyDraft(list: ApiAccessList): Draft {
  return {
    name: '',
    purpose: '',
    recipient: '',
    scopes: [],
    unit: '',
    expires: inDays(Math.min(365, list.max_days)),
    networks: '',
    embeddable: false,
    partner: '',
    basis: '',
    confirmed: false,
    thirdCountry: false,
    memberFields: [],
    onlyActive: true,
    adultsOnly: false,
    reportLevel: 'a',
    hookUrl: '',
    hookEvents: [],
  }
}

function draftOf(a: ApiAccess): Draft {
  return {
    name: a.name,
    purpose: a.purpose,
    recipient: a.recipient,
    scopes: a.scopes,
    unit: a.unit ? String(a.unit.id) : '',
    expires: day(new Date(a.expires_at)),
    networks: a.allowed_networks.join('\n'),
    embeddable: a.embeddable,
    partner: a.partner ? String(a.partner.id) : '',
    basis: a.legal_basis,
    confirmed: !!a.legal_confirmed_at,
    thirdCountry: a.third_country,
    memberFields: a.member_fields,
    onlyActive: a.only_active,
    adultsOnly: a.adults_only,
    reportLevel: a.report_level,
    hookUrl: a.webhook_url,
    hookEvents: a.webhook_events,
  }
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

function AccessForm({
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

/** Der neue Schlüssel: nur jetzt sichtbar, zum Kopieren und Weitergeben. */
function NewKey({
  shown,
  overlapDays,
  onDone,
}: {
  shown: ApiAccessWithKey
  overlapDays: number
  onDone: () => void
}) {
  const [note, setNote] = useState('')
  async function copy() {
    try {
      await navigator.clipboard.writeText(shown.key)
      setNote(t('Schlüssel kopiert.'))
    } catch {
      setNote(t('Kopieren ging nicht. Bitte den Schlüssel markieren.'))
    }
  }
  return (
    <section className="card card-wide stack" aria-live="polite">
      <h3>{t('Schlüssel für „{name}“', { name: shown.name })}</h3>
      <Alert kind="info">
        {t(
          'Der Schlüssel steht nur jetzt hier. Kopiere ihn und gib ihn auf sicherem Weg weiter, nicht per unverschlüsselter E-Mail. HUBIplan speichert ihn nicht lesbar.',
        )}
      </Alert>
      <Field label={t('Schlüssel')} readOnly value={shown.key} onFocus={(e) => e.target.select()} />
      {shown.previous_until && (
        <p className="muted small">
          {t(
            'Der bisherige Schlüssel gilt noch {n} Tage, bis {date}. So lässt sich das andere Programm in Ruhe umstellen.',
            { n: overlapDays, date: formatDateTime(shown.previous_until) },
          )}
        </p>
      )}
      <div className="button-row">
        <button type="button" className="button button-primary" onClick={() => void copy()}>
          {t('Schlüssel kopieren')}
        </button>
        <button type="button" className="button" onClick={onDone}>
          {t('Fertig')}
        </button>
      </div>
      <p className="muted small" role="status">
        {note}
      </p>
    </section>
  )
}

/** Das Geheimnis für die Unterschrift der Benachrichtigungen: nur jetzt sichtbar. */
function NewSecret({ name, secret, onDone }: { name: string; secret: string; onDone: () => void }) {
  return (
    <section className="card card-wide stack" aria-live="polite">
      <h3>{t('Geheimnis der Benachrichtigungen für „{name}“', { name })}</h3>
      <Alert kind="info">
        {t(
          'Mit diesem Geheimnis prüft das andere Programm, dass eine Benachrichtigung wirklich von HUBIplan kommt. Es steht nur jetzt hier.',
        )}
      </Alert>
      <Field label={t('Geheimnis')} readOnly value={secret} onFocus={(e) => e.target.select()} />
      <div className="button-row">
        <button type="button" className="button" onClick={onDone}>
          {t('Fertig')}
        </button>
      </div>
    </section>
  )
}

function StateBadge({ access }: { access: ApiAccess }) {
  if (access.state === 'expired')
    return <span className="badge badge-cancelled">{t('abgelaufen')}</span>
  if (access.state === 'idle') return <span className="badge badge-warn">{t('ruht')}</span>
  return <span className="badge badge-yes">{t('aktiv')}</span>
}

export function ApiAccessPage() {
  const org = useActiveOrg()
  const { data, error, reload, setData } = useLoad(() => apiAccessApi.list(org.id), [org.id])
  const [adding, setAdding] = useState(false)
  const [editing, setEditing] = useState<number | null>(null)
  const [shown, setShown] = useState<ApiAccessWithKey | null>(null)
  const [secret, setSecret] = useState<{ id: number; name: string; secret: string } | null>(null)
  const [actionError, setActionError] = useState<string | null>(null)
  const [note, setNote] = useState('')
  if (error) return <LoadError message={error} onRetry={reload} />
  if (!data) return <Loading />
  const labels = new Map(data.scopes.map((s) => [s.scope, s.label]))
  const replace = (access: ApiAccess) =>
    setData({ ...data, accesses: data.accesses.map((a) => (a.id === access.id ? access : a)) })
  const showSecret = (access: ApiAccess) => {
    if (access.webhook_secret)
      setSecret({ id: access.id, name: access.name, secret: access.webhook_secret })
  }
  const act = async (run: () => Promise<void>) => {
    setActionError(null)
    setNote('')
    try {
      await run()
    } catch (err) {
      setActionError(errorMessage(err))
    }
  }
  const rotate = async (access: ApiAccess) => {
    const yes = await confirmDialog({
      final: false,
      message: t(
        'Neuen Schlüssel für „{name}“ erzeugen? Der bisherige gilt noch {n} Tage und wird dann ungültig.',
        { name: access.name, n: data.overlap_days },
      ),
      confirmLabel: t('Neuen Schlüssel erzeugen'),
    })
    if (!yes) return
    await act(async () => {
      const fresh = await apiAccessApi.rotate(org.id, access.id)
      replace(fresh)
      setShown(fresh)
    })
  }
  const remove = async (access: ApiAccess) => {
    const yes = await confirmDialog({
      final: true,
      message: t(
        'Zugang „{name}“ löschen? Der Schlüssel gilt sofort nicht mehr; das andere Programm bekommt keine Daten mehr.',
        { name: access.name },
      ),
      confirmLabel: t('Löschen'),
    })
    if (!yes) return
    await act(async () => {
      await apiAccessApi.remove(org.id, access.id)
      setData({ ...data, accesses: data.accesses.filter((a) => a.id !== access.id) })
      if (shown?.id === access.id) setShown(null)
      if (secret?.id === access.id) setSecret(null)
    })
  }
  const newSecret = async (access: ApiAccess) => {
    const yes = await confirmDialog({
      final: false,
      message: t(
        'Neues Geheimnis für die Benachrichtigungen von „{name}“ erzeugen? Das bisherige gilt sofort nicht mehr.',
        { name: access.name },
      ),
      confirmLabel: t('Neues Geheimnis erzeugen'),
    })
    if (!yes) return
    await act(async () => {
      const fresh = await apiAccessApi.webhookSecret(org.id, access.id)
      replace(fresh)
      showSecret(fresh)
    })
  }
  const testHook = (access: ApiAccess) =>
    act(async () => {
      const result = await apiAccessApi.webhookTest(org.id, access.id)
      if (result.ok)
        setNote(t('Die Probenachricht an „{name}“ ist angekommen.', { name: access.name }))
      else setActionError(t('Die Probenachricht kam nicht an: {error}', { error: result.error }))
    })
  const hookLine = (a: ApiAccess) => {
    if (a.webhook_state === 'paused')
      return t('Benachrichtigungen ruhen: Die Adresse war sieben Tage nicht erreichbar.')
    if (a.webhook_state === 'failing')
      return t('Benachrichtigungen kommen zurzeit nicht an: {error}', {
        error: a.webhook_last_error,
      })
    return t('Benachrichtigungen an {url}', { url: a.webhook_url })
  }
  const row = (a: ApiAccess) =>
    editing === a.id ? (
      <li key={a.id}>
        <AccessForm
          list={data}
          initial={draftOf(a)}
          submitLabel={t('Speichern')}
          onCancel={() => setEditing(null)}
          onSubmit={async (input) => {
            const fresh = await apiAccessApi.update(org.id, a.id, input)
            replace(fresh)
            showSecret(fresh)
            setEditing(null)
          }}
        />
      </li>
    ) : (
      <li key={a.id} className="item-row">
        <div className="item-row-info">
          <strong>{a.name}</strong> <StateBadge access={a} />
          <div className="muted small">
            {[a.recipient, a.unit ? a.unit.name : t('Ganze Einheit'), a.purpose]
              .filter(Boolean)
              .join(' · ')}
          </div>
          <div className="small">{a.scopes.map((s) => labels.get(s) ?? s).join(', ')}</div>
          <div className="muted small">
            {t('Schlüssel endet auf …{hint}', { hint: a.key_hint })} ·{' '}
            {t('gültig bis {date}', { date: formatDate(a.expires_at) })} ·{' '}
            {a.last_used_at
              ? t('zuletzt genutzt {date}, {n} Abrufe', {
                  date: formatDateTime(a.last_used_at),
                  n: a.request_count,
                })
              : t('noch nie genutzt')}
          </div>
          {a.personal && (
            <div className="small">
              <span className="badge badge-warn">{t('Personendaten')}</span>{' '}
              {[
                a.partner ? t('Empfänger: {name}', { name: a.partner.name }) : t('Empfänger fehlt'),
                basisLabel(a.legal_basis) || t('Rechtsgrundlage fehlt'),
                a.third_country ? t('außerhalb der EU') : '',
              ]
                .filter(Boolean)
                .join(' · ')}
            </div>
          )}
          {a.personal && (
            <div className="muted small">
              {a.records_read > 0
                ? t('{n} Datensätze mit Personendaten in den letzten {days} Tagen abgerufen', {
                    n: a.records_read,
                    days: data.log_days,
                  })
                : t('Noch keine Personendaten abgerufen')}
              {a.reads.length > 0 &&
                ` · ${t('zuletzt {date}', { date: formatDateTime(a.reads[0].at) })}`}
            </div>
          )}
          {a.writes && (
            <div className="muted small">
              {a.last_write_at
                ? t('Darf schreiben: {n} schreibende Anfragen, zuletzt {date}', {
                    n: a.write_count,
                    date: formatDateTime(a.last_write_at),
                  })
                : t('Darf schreiben, hat aber noch nichts geschrieben')}
            </div>
          )}
          {a.webhook_state !== 'off' && (
            <div className={a.webhook_state === 'ok' ? 'muted small' : 'small'}>{hookLine(a)}</div>
          )}
          {a.state === 'idle' && (
            <div className="small">
              {t('Seit {n} Tagen nicht genutzt und deshalb abgeschaltet.', { n: data.idle_days })}
            </div>
          )}
          {a.previous_until && (
            <div className="muted small">
              {t('Der vorige Schlüssel gilt noch bis {date}.', {
                date: formatDateTime(a.previous_until),
              })}
            </div>
          )}
        </div>
        <div className="button-row">
          {a.state === 'idle' && (
            <button
              type="button"
              className="button"
              onClick={() => void act(async () => replace(await apiAccessApi.resume(org.id, a.id)))}
            >
              {t('Wieder einschalten')}
            </button>
          )}
          {a.webhook_state === 'paused' && (
            <button
              type="button"
              className="button"
              onClick={() =>
                void act(async () =>
                  replace(await apiAccessApi.update(org.id, a.id, { webhook_resume: true })),
                )
              }
            >
              {t('Benachrichtigungen wieder einschalten')}
            </button>
          )}
          <button type="button" className="button" onClick={() => setEditing(a.id)}>
            {t('Bearbeiten')}
          </button>
          {a.webhook_state !== 'off' && (
            <button type="button" className="button" onClick={() => void testHook(a)}>
              {t('Probenachricht senden')}
            </button>
          )}
          {a.webhook_state !== 'off' && (
            <button type="button" className="button" onClick={() => void newSecret(a)}>
              {t('Neues Geheimnis erzeugen')}
            </button>
          )}
          <button type="button" className="button" onClick={() => void rotate(a)}>
            {t('Neuen Schlüssel erzeugen')}
          </button>
          <button type="button" className="button button-danger" onClick={() => void remove(a)}>
            {t('Löschen')}
          </button>
        </div>
      </li>
    )
  return (
    <div className="stack">
      <section className="card card-wide">
        <h2>{t('API-Zugänge')}</h2>
        <p className="muted small">
          {t(
            'Mit einem API-Zugang liest ein anderes Programm Daten dieser Einheit, etwa die Software des Dachverbands oder eine eigene Webseite. Jeder Zugang hat einen eigenen Schlüssel, darf nur das Angekreuzte lesen und läuft von selbst ab.',
          )}
        </p>
        <p className="muted small">
          {t(
            'Namen, Anschriften und andere Personendaten gibt ein Zugang nur heraus, wenn du den Empfänger benennst und die Rechtsgrundlage bestätigst. Ändern kann ein Zugang nichts.',
          )}
        </p>
        <dl className="small">
          <dt>{t('Adresse der Schnittstelle')}</dt>
          <dd>
            <code>{data.address}</code>
          </dd>
          <dt>{t('Beschreibung für Entwickler')}</dt>
          <dd>
            <a href={data.docs} target="_blank" rel="noreferrer">
              {t('OpenAPI-Beschreibung öffnen')}
            </a>
          </dd>
          <dt>{t('Grenze')}</dt>
          <dd>
            {t('{n} Abrufe je Stunde und Zugang, davon höchstens {w} schreibende', {
              n: data.requests_per_hour,
              w: data.writes_per_hour,
            })}
          </dd>
        </dl>
        {data.accesses.length === 0 ? (
          <p>{t('Noch keine API-Zugänge angelegt.')}</p>
        ) : (
          <ul className="item-list">{data.accesses.map(row)}</ul>
        )}
        {actionError && <Alert kind="error">{actionError}</Alert>}
        <p className="muted small" role="status">
          {note}
        </p>
      </section>
      {shown && (
        <NewKey shown={shown} overlapDays={data.overlap_days} onDone={() => setShown(null)} />
      )}
      {secret && (
        <NewSecret name={secret.name} secret={secret.secret} onDone={() => setSecret(null)} />
      )}
      <section className="card card-wide">
        <h3>{t('Neuer API-Zugang')}</h3>
        {adding ? (
          <AccessForm
            list={data}
            initial={emptyDraft(data)}
            submitLabel={t('Zugang anlegen')}
            onCancel={() => setAdding(false)}
            onSubmit={async (input) => {
              const fresh = await apiAccessApi.create(org.id, input)
              setData({ ...data, accesses: [...data.accesses, fresh] })
              setShown(fresh)
              showSecret(fresh)
              setAdding(false)
            }}
          />
        ) : (
          <button type="button" className="button button-primary" onClick={() => setAdding(true)}>
            {t('Zugang anlegen')}
          </button>
        )}
      </section>
    </div>
  )
}
