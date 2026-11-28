import { useState } from 'react'
import type { FormEvent } from 'react'
import { billingApi } from '../../api/billing.ts'
import { euro, parseAmount } from '../../api/finance.ts'
import { errorMessage, useForm, useLoad } from '../../components/forms.ts'
import { Alert, Field, Loading } from '../../components/ui.tsx'
import { HowTo, Term, Why } from '../../learning/Aids.tsx'
import { t } from '../../i18n/index.ts'
import { useOrgBillingSettings } from './rulesHelpers.ts'

export function DunningLevelsPage() {
  const { org, settings } = useOrgBillingSettings()
  if (settings.error) return <Alert kind="error">{settings.error}</Alert>
  if (!settings.data) return <Loading />
  return <DunningLevelsCard orgId={org.id} canEdit={settings.data.can_edit} />
}

function DunningLevelsCard({ orgId, canEdit }: { orgId: number; canEdit: boolean }) {
  const { data, error, reload } = useLoad(() => billingApi.dunningLevels(orgId), [orgId])
  const [message, setMessage] = useState<string | null>(null)
  const form = useForm({ name: '', days: '14', fee: '', text: '' })
  const v = form.values

  async function add(e: FormEvent) {
    e.preventDefault()
    const next = Math.max(0, ...(data ?? []).map((d) => d.level)) + 1
    const ok = await form.submit(
      () =>
        billingApi.createDunningLevel(orgId, {
          level: next,
          name: v.name,
          days: Number(v.days) || 0,
          fee: parseAmount(v.fee) || '0',
          text: v.text,
        }),
      t('Mahnstufe angelegt.'),
    )
    if (ok) {
      form.setValues({ name: '', days: String((Number(v.days) || 0) + 14), fee: '', text: '' })
      await reload()
    }
  }

  async function remove(id: number) {
    setMessage(null)
    try {
      await billingApi.deleteDunningLevel(orgId, id)
      await reload()
    } catch (err) {
      setMessage(errorMessage(err))
    }
  }

  if (error) return <Alert kind="error">{error}</Alert>
  if (!data) return null
  return (
    <div className="card card-wide">
      <h2>
        <Term k="dunning_level">{t('Mahnstufen')}</Term>
      </h2>
      <div className="aid-row">
        <Why k="dunning_levels" />
        <HowTo k="calc_dunning" />
      </div>
      <p className="muted small">
        {t(
          'Zum Beispiel Zahlungserinnerung 14 Tage nach Fälligkeit, 1. Mahnung nach 28 Tagen mit 5 € Gebühr. Fällige Mahnungen erscheinen unter Mahnungen.',
        )}
      </p>
      {data.length === 0 ? (
        <p className="muted">{t('Keine Mahnstufen.')}</p>
      ) : (
        <table className="table">
          <thead>
            <tr>
              <th>{t('Stufe')}</th>
              <th>{t('fällig nach')}</th>
              <th className="num">{t('Gebühr')}</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {data.map((d) => (
              <tr key={d.id}>
                <td>
                  <strong>
                    {d.level}. {d.name}
                  </strong>
                </td>
                <td>
                  {d.days} {t('Tagen über Fälligkeit')}
                </td>
                <td className="num">{Number(d.fee) ? euro(d.fee) : '–'}</td>
                <td className="actions">
                  {canEdit && (
                    <button type="button" className="link-button" onClick={() => void remove(d.id)}>
                      {t('Löschen')}
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {message && <Alert kind="error">{message}</Alert>}
      {canEdit && (
        <form className="subcard" onSubmit={add}>
          <h3>{t('Neue Mahnstufe')}</h3>
          <div className="grid-3">
            <Field
              label={t('Bezeichnung')}
              required
              placeholder={t('z. B. Zahlungserinnerung')}
              value={v.name}
              error={form.errors.name}
              onChange={(e) => form.set('name', e.target.value)}
            />
            <Field
              label={t('Tage nach Fälligkeit')}
              type="number"
              min={0}
              value={v.days}
              error={form.errors.days}
              onChange={(e) => form.set('days', e.target.value)}
            />
            <Field
              label={t('Gebühr (€, optional)')}
              inputMode="decimal"
              value={v.fee}
              error={form.errors.fee}
              onChange={(e) => form.set('fee', e.target.value)}
            />
          </div>
          <label className="field">
            <span>{t('Text im Schreiben (optional)')}</span>
            <textarea
              rows={3}
              placeholder={t('leer = Standardtext')}
              value={v.text}
              onChange={(e) => form.set('text', e.target.value)}
            />
          </label>
          {form.message && <Alert kind={form.message.kind}>{form.message.text}</Alert>}
          <button type="submit" className="button button-primary" disabled={form.busy}>
            {t('Anlegen')}
          </button>
        </form>
      )}
    </div>
  )
}
