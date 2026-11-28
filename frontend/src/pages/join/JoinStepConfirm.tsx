// Beitrittsformular, Schritt 3: Bestätigungen, Einwilligungen und Unterschrift.
import { SignaturePad } from '../../components/SignaturePad.tsx'
import { Checkbox } from '../../components/ui.tsx'
import { t } from '../../i18n/index.ts'
import { confirmKey, type JoinModel } from './joinModel.ts'

export function JoinStepConfirm({ m }: { m: JoinModel }) {
  const { s, kiosk, values, toggle, err, confirmations, padKey, setSignature } = m
  return (
    <>
      <fieldset className="stack-sm">
        <legend>{t('Bestätigungen')}</legend>
        {confirmations.map((c) => (
          <div key={c.key}>
            <Checkbox
              label={c.label}
              checked={values.confirmations.includes(c.key)}
              onChange={(on) => toggle('confirmations', c.key, on)}
              hint={'version' in c && c.version ? t('Fassung {x}', { x: c.version }) : undefined}
            />
            {'url' in c && c.url && (
              <a href={c.url} target="_blank" rel="noreferrer" className="small">
                {t('Dokument öffnen')}
              </a>
            )}
            {'text' in c && c.text && (
              <details className="small">
                <summary>{t('Text lesen')}</summary>
                <p className="rsvp-public-text">{c.text}</p>
              </details>
            )}
            {err(confirmKey(c.key)) && <p className="field-error">{err(confirmKey(c.key))}</p>}
          </div>
        ))}
      </fieldset>
      {s.consents.length > 0 && (
        <fieldset className="stack-sm">
          <legend>{t('Einwilligungen (freiwillig)')}</legend>
          <p className="muted small">{t('Du kannst sie jederzeit beim Verein widerrufen.')}</p>
          {s.consents.map((c) => (
            <Checkbox
              key={c.key}
              label={c.label}
              checked={values.consents.includes(c.key)}
              onChange={(on) => toggle('consents', c.key, on)}
            />
          ))}
        </fieldset>
      )}
      {s.signature === 'required' && (
        <fieldset className="stack-sm">
          <legend>{t('Unterschrift')}</legend>
          <p className="muted small">
            {kiosk
              ? t('Bitte hier mit dem Finger oder Stift unterschreiben.')
              : t(
                  'Der Verein braucht eine Unterschrift. Du kannst hier unterschreiben oder später den Antrag als PDF ausdrucken und unterschrieben abgeben.',
                )}
          </p>
          <SignaturePad key={padKey} onChange={setSignature} />
          {err('signature') && <p className="field-error">{err('signature')}</p>}
        </fieldset>
      )}
    </>
  )
}
