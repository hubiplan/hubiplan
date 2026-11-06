import { useState } from 'react'
import type { FormEvent } from 'react'
import { ApiError } from '../../api/client.ts'
import { memberApi } from '../../api/members.ts'
import type { BillingAddress, MemberDetail } from '../../api/members.ts'
import { errorMessage } from '../../components/forms.ts'
import { confirmDialog } from '../../components/dialog.ts'
import { Alert, Field } from '../../components/ui.tsx'
import { t } from '../../i18n/index.ts'

const EMPTY: BillingAddress = {
  name: '',
  attention: '',
  street: '',
  postal_code: '',
  city: '',
  country: '',
  email: '',
  order_reference: '',
  leitweg_id: '',
}

/** Abweichende Rechnungsanschrift, Rechnungs-E-Mail, Bestellnummer und Leitweg-ID. */
export function BillingAddressSection({
  orgId,
  member,
  canEdit,
  onSaved,
}: {
  orgId: number
  member: MemberDetail
  canEdit: boolean
  onSaved: (m: MemberDetail) => void
}) {
  const current = member.billing_address ?? null
  const [editing, setEditing] = useState(false)
  const [v, setV] = useState<BillingAddress>(current ?? EMPTY)
  const [errors, setErrors] = useState<Record<string, string>>({})
  const [busy, setBusy] = useState(false)
  const set = (key: keyof BillingAddress, value: string) =>
    setV((old) => ({ ...old, [key]: value }))

  async function save(ev: FormEvent) {
    ev.preventDefault()
    setBusy(true)
    try {
      onSaved(await memberApi.setBillingAddress(orgId, member.id, v))
      setErrors({})
      setEditing(false)
    } catch (err) {
      setErrors(
        err instanceof ApiError && Object.keys(err.fieldErrors).length > 0
          ? err.fieldErrors
          : { detail: errorMessage(err) },
      )
    } finally {
      setBusy(false)
    }
  }

  async function remove() {
    const ok = await confirmDialog({
      title: t('Rechnungsangaben entfernen?'),
      message: t('Rechnungen gehen dann wieder an die Anschrift des Mitglieds.'),
      confirmLabel: t('Entfernen'),
    })
    if (!ok) return
    try {
      onSaved(await memberApi.removeBillingAddress(orgId, member.id))
      setV(EMPTY)
    } catch (err) {
      setErrors({ detail: errorMessage(err) })
    }
  }

  const address = current
    ? [
        current.name,
        current.attention,
        current.street,
        `${current.postal_code} ${current.city}`.trim(),
        current.country,
      ].filter(Boolean)
    : []
  const extra = current
    ? [
        current.email && t('Rechnungs-E-Mail: {x}', { x: current.email }),
        current.order_reference && t('Bestellnummer: {x}', { x: current.order_reference }),
        current.leitweg_id && t('Leitweg-ID: {x}', { x: current.leitweg_id }),
      ].filter(Boolean)
    : []

  return (
    <section className="card card-wide" aria-labelledby="rechnungsanschrift-titel">
      <h2 id="rechnungsanschrift-titel">{t('Rechnungsanschrift')}</h2>
      {errors.detail && <Alert kind="error">{errors.detail}</Alert>}
      {!editing && (
        <>
          {current ? (
            <>
              {current.street || current.city ? (
                <p style={{ whiteSpace: 'pre-line' }}>{address.join('\n')}</p>
              ) : (
                <p className="muted">{t('Rechnungen gehen an die Anschrift des Mitglieds.')}</p>
              )}
              {extra.length > 0 && <p className="muted small">{extra.join(' · ')}</p>}
            </>
          ) : (
            <p className="muted">
              {t(
                'Keine abweichende Rechnungsanschrift. Rechnungen und Mahnungen gehen an die Anschrift des Mitglieds.',
              )}
            </p>
          )}
          {canEdit && (
            <p className="actions">
              <button
                type="button"
                className="button"
                onClick={() => {
                  setV(current ?? EMPTY)
                  setEditing(true)
                }}
              >
                {current ? t('Rechnungsangaben bearbeiten') : t('Rechnungsanschrift festlegen')}
              </button>{' '}
              {current && (
                <button type="button" className="link-button" onClick={() => void remove()}>
                  {t('Entfernen')}
                </button>
              )}
            </p>
          )}
        </>
      )}
      {editing && (
        <form className="stack" onSubmit={(ev) => void save(ev)}>
          <fieldset disabled={busy} className="stack">
            <p className="muted small">
              {t(
                'Rechnungen und Mahnungen gehen an diese Anschrift. Briefe, Rundschreiben und Einladungen nicht. Ohne Anschrift gelten nur Rechnungs-E-Mail, Bestellnummer und Leitweg-ID.',
              )}
            </p>
            <div className="grid-2">
              <Field
                label={t('Rechnungsempfänger')}
                hint={t('leer: Name des Mitglieds')}
                value={v.name}
                error={errors.name}
                onChange={(ev) => set('name', ev.target.value)}
              />
              <Field
                label={t('Abteilung / z. Hd.')}
                value={v.attention}
                error={errors.attention}
                onChange={(ev) => set('attention', ev.target.value)}
              />
            </div>
            <Field
              label={t('Straße oder Postfach')}
              value={v.street}
              error={errors.street}
              onChange={(ev) => set('street', ev.target.value)}
            />
            <div className="grid-3">
              <Field
                label={t('PLZ')}
                value={v.postal_code}
                error={errors.postal_code}
                onChange={(ev) => set('postal_code', ev.target.value)}
              />
              <Field
                label={t('Ort')}
                value={v.city}
                error={errors.city}
                onChange={(ev) => set('city', ev.target.value)}
              />
              <Field
                label={t('Land')}
                value={v.country}
                error={errors.country}
                onChange={(ev) => set('country', ev.target.value)}
              />
            </div>
            <div className="grid-3">
              <Field
                label={t('Rechnungs-E-Mail')}
                type="email"
                value={v.email}
                error={errors.email}
                onChange={(ev) => set('email', ev.target.value)}
              />
              <Field
                label={t('Bestellnummer')}
                value={v.order_reference}
                error={errors.order_reference}
                onChange={(ev) => set('order_reference', ev.target.value)}
              />
              <Field
                label={t('Leitweg-ID')}
                hint={t('für Rechnungen an Behörden')}
                value={v.leitweg_id}
                error={errors.leitweg_id}
                onChange={(ev) => set('leitweg_id', ev.target.value)}
              />
            </div>
            <div className="actions">
              <button type="submit">{t('Speichern')}</button>{' '}
              <button type="button" className="link-button" onClick={() => setEditing(false)}>
                {t('Abbrechen')}
              </button>
            </div>
          </fieldset>
        </form>
      )}
    </section>
  )
}
