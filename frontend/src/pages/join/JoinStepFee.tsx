// Beitrittsformular, Schritt 2: Beitrag und Zahlung.
import { Checkbox, Field } from '../../components/ui.tsx'
import { t } from '../../i18n/index.ts'
import { type JoinModel } from './joinModel.ts'

export function JoinStepFee({ m }: { m: JoinModel }) {
  const { s, values, set, err, type } = m
  return (
    <>
      {type && (
        <p>
          {t('Mitgliedsart: {x}', { x: type.label })}
          {type.fee
            ? ` · ${t('Beitrag: {x} € im Jahr', { x: type.fee })}`
            : ` · ${t('Den Beitrag nennt dir der Verein.')}`}
        </p>
      )}
      {s.company && (
        <p className="muted">
          {t('Beitrag zahlt {x}. Eine Lastschrift ist nur nötig, wenn du selbst zahlen möchtest.', {
            x: s.company,
          })}
        </p>
      )}
      {s.sepa === 'off' && !s.company && (
        <p className="muted">{t('Wie der Beitrag gezahlt wird, erfährst du nach der Aufnahme.')}</p>
      )}
      {s.sepa === 'offer' && (
        <Checkbox
          label={t('Beitrag per Lastschrift zahlen')}
          checked={values.pay}
          onChange={(on) => set('pay', on)}
        />
      )}
      {values.pay && s.sepa !== 'off' && (
        <fieldset className="stack-sm">
          <legend>{t('SEPA-Lastschriftmandat')}</legend>
          {s.mandate.text && <p className="small rsvp-public-text">{s.mandate.text}</p>}
          {s.mandate.creditor_id && (
            <p className="small muted">
              {t('Gläubiger-ID: {x}', { x: s.mandate.creditor_id })} ·{' '}
              {t('Die Mandatsreferenz erhältst du nach der Aufnahme.')}
            </p>
          )}
          <Field
            label={t('Kontoinhaber')}
            value={values.holder}
            autoComplete="name"
            onChange={(e) => set('holder', e.target.value)}
            error={err('holder')}
            required
          />
          <Field
            label={t('IBAN')}
            value={values.iban}
            autoComplete="off"
            spellCheck={false}
            onChange={(e) => set('iban', e.target.value.toUpperCase())}
            error={err('iban') || err('mandate')}
            required
          />
          <Field
            label={t('BIC (freiwillig)')}
            value={values.bic}
            autoComplete="off"
            spellCheck={false}
            onChange={(e) => set('bic', e.target.value.toUpperCase())}
          />
        </fieldset>
      )}
    </>
  )
}
