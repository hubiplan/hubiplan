import { useState } from 'react'
import type { FormEvent } from 'react'
import { donationApi } from '../../api/donations.ts'
import type { DonationSettings } from '../../api/donations.ts'
import { errorMessage, formatDate, useLoad } from '../../components/forms.ts'
import { Alert, Checkbox, Field, LoadError, SelectField, Loading } from '../../components/ui.tsx'
import { useChangesGuard } from '../../components/leaveGuard.ts'
import { useActiveOrg } from '../../org/OrgContext.tsx'
import { Term, Why } from '../../learning/Aids.tsx'
import { t } from '../../i18n/index.ts'
import { fieldErrors } from './donationsHelpers.ts'

export function DonationSettingsForm({ canEdit }: { canEdit: boolean }) {
  const org = useActiveOrg()
  const load = useLoad(() => donationApi.settings(org.id), [org.id])
  if (load.error) return <LoadError message={load.error} onRetry={() => void load.reload()} />
  if (!load.data) return <Loading />
  return (
    <>
      <SettingsEditor key={org.id} initial={load.data} canEdit={canEdit} />
      {load.data.problems.length === 0 && <SimplifiedProof />}
    </>
  )
}

// Vereinfachter Zuwendungsnachweis für Zuwendungen bis 300 € (§ 50 Abs. 4 Satz 1 Nr. 2 EStDV):
// Beleg als PDF zum Auslegen und als Text für die Webseite (Konzept vereinskasse-steuern, S8)
function SimplifiedProof() {
  const org = useActiveOrg()
  const [open, setOpen] = useState(false)
  const load = useLoad(
    () => (open ? donationApi.simplified(org.id) : Promise.resolve(null)),
    [org.id, open],
  )
  return (
    <div className="card card-wide" data-testid="simplified-proof">
      <h2>{t('Spenden bis 300 €')}</h2>
      <p className="muted small">
        {t(
          'Bei Zuwendungen bis 300 € genügt dem Finanzamt der Kontoauszug zusammen mit einem Beleg des Vereins über die Steuerbegünstigung. Den Beleg könnt ihr auf der Webseite veröffentlichen, auslegen oder mitschicken; eine Zuwendungsbestätigung ist dafür nicht nötig.',
        )}
      </p>
      <div className="button-row">
        <a className="button button-ghost" href={donationApi.simplifiedPdfUrl(org.id)}>
          {t('Beleg als PDF')}
        </a>
        {!open && (
          <button type="button" className="button button-ghost" onClick={() => setOpen(true)}>
            {t('Text für die Webseite')}
          </button>
        )}
      </div>
      {load.error && <Alert kind="error">{load.error}</Alert>}
      {load.data && (
        <label className="field">
          <span>{t('Text für die Webseite')}</span>
          <textarea rows={10} readOnly value={load.data.text} />
        </label>
      )}
    </div>
  )
}

function SettingsEditor({ initial, canEdit }: { initial: DonationSettings; canEdit: boolean }) {
  const org = useActiveOrg()
  const [v, setV] = useState(initial)
  const [errors, setErrors] = useState<Record<string, string>>({})
  const [message, setMessage] = useState<{ kind: 'success' | 'error'; text: string } | null>(null)
  const [busy, setBusy] = useState(false)
  const set = <K extends keyof DonationSettings>(k: K, value: DonationSettings[K]) =>
    setV((old) => ({ ...old, [k]: value }))
  const exemption = v.notice === 'exemption'
  // Ungespeicherte Angaben schützen (UX-Audit 31.10. W01)
  const guard = useChangesGuard(v, canEdit)

  async function submit(e: FormEvent) {
    e.preventDefault()
    setBusy(true)
    setErrors({})
    setMessage(null)
    try {
      const saved = await donationApi.saveSettings(org.id, {
        purposes: v.purposes,
        notice: v.notice,
        tax_office: v.tax_office,
        tax_number: v.tax_number,
        notice_date: v.notice_date || null,
        assessment_period: v.assessment_period,
        fees_allowed: v.fees_allowed,
        place: v.place,
      })
      setV(saved)
      guard.markSaved()
      setMessage({ kind: 'success', text: t('Gespeichert.') })
    } catch (err) {
      setErrors(fieldErrors(err))
      setMessage({ kind: 'error', text: errorMessage(err) })
    } finally {
      setBusy(false)
    }
  }

  return (
    <form className="card card-wide" onSubmit={submit}>
      <h2>{t('Angaben zur Steuerbegünstigung')}</h2>
      <p className="muted small">
        {t(
          'Diese Angaben stehen auf jeder Bestätigung. Sie stammen aus dem letzten Bescheid des Finanzamts. Ein',
        )}{' '}
        <Term k="exemption_notice">{t('Freistellungsbescheid')}</Term> {t('reicht 5 Jahre, eine')}{' '}
        <Term k="statute_notice">{t('Feststellung nach § 60a AO')}</Term>{' '}
        {t('3 Jahre (§ 63 Abs. 5 AO); danach stellt HUBIplan keine Bestätigungen mehr aus.')}
      </p>
      <Why k="donation_notice" />
      {v.problems.length > 0 ? (
        <Alert kind="info">{v.problems.join(' ')}</Alert>
      ) : (
        v.valid_until && (
          <Alert kind="success">
            {t('Bestätigungen möglich bis {x} (danach neuen Bescheid eintragen).', {
              x: formatDate(v.valid_until),
            })}
          </Alert>
        )
      )}
      <fieldset disabled={!canEdit}>
        <Checkbox
          label={t('Steuerbegünstigt mit eigenem Bescheid des Finanzamts')}
          hint={t(
            'gilt auch für nicht eingetragene Vereine; unselbständige Untereinheiten haben meist keinen eigenen Bescheid',
          )}
          checked={v.enabled}
          onChange={(on) => set('enabled', on)}
        />
        <Why k="donation_enabled" />
        <SelectField
          label={t('Art des Bescheids')}
          value={v.notice}
          onChange={(e) => set('notice', e.target.value as DonationSettings['notice'])}
        >
          <option value="exemption">
            {t('Freistellungsbescheid bzw. Anlage zum Körperschaftsteuerbescheid')}
          </option>
          <option value="statute">
            {t('Feststellung der Satzungsmäßigkeit nach § 60a AO (neu gegründet)')}
          </option>
        </SelectField>
        <label className={`field${errors.purposes ? ' field-invalid' : ''}`}>
          <span>{t('Begünstigte Zwecke (wie im Bescheid)')}</span>
          <textarea
            rows={2}
            value={v.purposes}
            maxLength={1000}
            placeholder={t('z. B. des Sports oder des traditionellen Brauchtums')}
            onChange={(e) => set('purposes', e.target.value)}
          />
          <small className="muted">
            {t(
              'Steht im Satz „Wir sind wegen Förderung … befreit“ und „nur zur Förderung … verwendet“.',
            )}
          </small>
        </label>
        <div className="grid-3">
          <Field
            label={t('Finanzamt')}
            value={v.tax_office}
            onChange={(e) => set('tax_office', e.target.value)}
            error={errors.tax_office}
            maxLength={200}
          />
          <Field
            label={t('Steuernummer')}
            value={v.tax_number}
            onChange={(e) => set('tax_number', e.target.value)}
            error={errors.tax_number}
            maxLength={50}
          />
          <Field
            label={t('Datum des Bescheids')}
            type="date"
            value={v.notice_date ?? ''}
            onChange={(e) => set('notice_date', e.target.value || null)}
            error={errors.notice_date}
          />
        </div>
        <div className="grid-2">
          {exemption && (
            <Field
              label={t('Letzter Veranlagungszeitraum')}
              value={v.assessment_period}
              placeholder={t('z. B. 2022 bis 2024')}
              onChange={(e) => set('assessment_period', e.target.value)}
              error={errors.assessment_period}
              maxLength={50}
            />
          )}
          <Field
            label={t('Ort der Ausstellung')}
            value={v.place}
            onChange={(e) => set('place', e.target.value)}
            maxLength={100}
          />
        </div>
        <Checkbox
          label={t('Auch Mitgliedsbeiträge bestätigen')}
          hint={t(
            'nur, wenn die Beiträge abziehbar sind; bei Sport-, Heimat- und Brauchtumsvereinen meist nicht (§ 10b Abs. 1 Satz 8 EStG)',
          )}
          checked={v.fees_allowed}
          onChange={(on) => set('fees_allowed', on)}
        />
      </fieldset>
      <Why k="donation_fees" />
      {message && <Alert kind={message.kind}>{message.text}</Alert>}
      {canEdit && (
        <div className="button-row">
          <button type="submit" className="button button-primary" disabled={busy}>
            {t('Speichern')}
          </button>
        </div>
      )}
    </form>
  )
}
