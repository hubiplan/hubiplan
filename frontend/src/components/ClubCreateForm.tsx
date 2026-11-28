import type { FormEvent } from 'react'
import { transferApi } from '../api/datatransfer.ts'
import { useForm } from './forms.ts'
import { Alert, Field } from './ui.tsx'
import { fillTerms, useTerms } from '../org/terms.ts'
import { t } from '../i18n/index.ts'

/** Dachverband legt einen Verein von Hand an. */
export function ClubCreateForm({
  federationId,
  onDone,
}: {
  federationId: number
  onDone: () => void
}) {
  const tm = useTerms()
  const form = useForm({
    name: '',
    founding_year: '',
    street: '',
    postal_code: '',
    city: '',
    contact_email: '',
    board_email: '',
  })
  const v = form.values

  async function save(e: FormEvent) {
    e.preventDefault()
    const result = await form.submit(
      () =>
        transferApi.createClub(federationId, {
          ...v,
          founding_year: v.founding_year ? Number(v.founding_year) : null,
        }),
      fillTerms(t('{Nom} wurde angelegt.'), tm),
    )
    if (result) {
      form.setValues({
        name: '',
        founding_year: '',
        street: '',
        postal_code: '',
        city: '',
        contact_email: '',
        board_email: '',
      })
      onDone()
    }
  }

  return (
    <form className="card card-wide" onSubmit={(e) => void save(e)}>
      <h2>
        {tm.Sg} {t('von Hand anlegen')}
      </h2>
      <div className="grid-2">
        <Field
          label={t('Name')}
          value={v.name}
          error={form.errors.name}
          onChange={(e) => form.set('name', e.target.value)}
          required
        />
        <Field
          label={t('Gründungsjahr')}
          inputMode="numeric"
          value={v.founding_year}
          error={form.errors.founding_year}
          onChange={(e) => form.set('founding_year', e.target.value)}
          required
        />
        <Field
          label={t('Straße und Hausnummer')}
          value={v.street}
          error={form.errors.street}
          onChange={(e) => form.set('street', e.target.value)}
          required
        />
        <Field
          label={t('PLZ')}
          value={v.postal_code}
          error={form.errors.postal_code}
          onChange={(e) => form.set('postal_code', e.target.value)}
          required
        />
        <Field
          label={t('Ort')}
          value={v.city}
          error={form.errors.city}
          onChange={(e) => form.set('city', e.target.value)}
          required
        />
        <Field
          label={t('E-Mail {gen}', { gen: tm.gen })}
          type="email"
          value={v.contact_email}
          error={form.errors.contact_email}
          onChange={(e) => form.set('contact_email', e.target.value)}
        />
        <Field
          label={t('Erster Vorstand (E-Mail, optional)')}
          type="email"
          value={v.board_email}
          error={form.errors.board_email}
          onChange={(e) => form.set('board_email', e.target.value)}
          hint={t('Bekommt die Rolle „Vorstand“. Ohne Konto wird eine Einladung verschickt.')}
        />
      </div>
      {form.message && <Alert kind={form.message.kind}>{form.message.text}</Alert>}
      <button type="submit" className="button button-primary" disabled={form.busy}>
        {tm.Sg} {t('anlegen')}
      </button>
    </form>
  )
}
