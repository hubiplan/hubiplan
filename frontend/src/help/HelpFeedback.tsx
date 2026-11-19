// „Hat das geholfen?“ unter einer Anleitung oder Seitenhilfe (docs/hilfe.md).
//
// Gespeichert werden nur der Hilfetext, die Sprache, die Fassung, Ja oder Nein, ein
// freiwilliger Satz und der Tag: keine Person, kein Verein. Die Plattformverwaltung sieht
// die Antworten unter Plattform › Hilfe. In der Ansicht als Rolle wird nichts gesendet.
import { useId, useState } from 'react'
import type { FormEvent } from 'react'
import { helpApi } from '../api/help.ts'
import { errorMessage } from '../components/forms.ts'
import { Alert } from '../components/ui.tsx'
import { lang, t } from '../i18n/index.ts'
import { TextArea } from '../pages/settings/TextArea.tsx'
import type { HelpEntry } from './content.ts'
import { useHelp } from './HelpContext.tsx'

export const FEEDBACK_MAX = 300

/** Eltern setzen `key={entry.key}`, damit jede Hilfe frisch beginnt. */
export function HelpFeedback({ entry }: { entry: Pick<HelpEntry, 'key'> }) {
  const help = useHelp()
  const id = useId()
  const [state, setState] = useState<'ask' | 'missing' | 'done'>('ask')
  const [comment, setComment] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  if (help?.previewRole) return null

  async function send(helpful: boolean, text = '') {
    setBusy(true)
    setError(null)
    try {
      await helpApi.feedback(entry.key, lang(), helpful, text.trim())
      setState('done')
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setBusy(false)
    }
  }

  function submit(e: FormEvent) {
    e.preventDefault()
    void send(false, comment)
  }

  return (
    <section className="help-feedback" aria-labelledby={id}>
      <h2 id={id} className="help-feedback-title">
        {t('Hat das geholfen?')}
      </h2>
      {state === 'done' && <p role="status">{t('Danke für die Rückmeldung.')}</p>}
      {state === 'ask' && (
        <p className="help-actions">
          <button
            type="button"
            className="button button-ghost"
            disabled={busy}
            onClick={() => void send(true)}
          >
            {t('Ja')}
          </button>
          <button
            type="button"
            className="button button-ghost"
            disabled={busy}
            onClick={() => setState('missing')}
          >
            {t('Nein')}
          </button>
        </p>
      )}
      {state === 'missing' && (
        <form onSubmit={submit}>
          <TextArea
            label={t('Was hat gefehlt? (freiwillig)')}
            value={comment}
            rows={2}
            hint={t(
              'Ein Satz genügt. Bitte keine Namen oder persönlichen Angaben: Gespeichert werden nur diese Hilfe, die Sprache, deine Antwort und das Datum, nicht wer du bist.',
            )}
            onChange={(value) => setComment(value.slice(0, FEEDBACK_MAX))}
          />
          <p className="help-actions">
            <button type="submit" className="button" disabled={busy}>
              {t('Absenden')}
            </button>
          </p>
        </form>
      )}
      {error && <Alert kind="error">{error}</Alert>}
    </section>
  )
}
