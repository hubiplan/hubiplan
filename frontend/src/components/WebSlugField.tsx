// Adresse auf der Webseite (Webseite #149): leer = aus dem Namen, sonst selbst festgelegt.
// Übernommen beim Verlassen des Feldes; frühere Adressen leitet die Webseite weiter.
import { useState } from 'react'
import { errorMessage } from './forms.ts'
import { Field } from './ui.tsx'
import { t } from '../i18n/index.ts'

export function WebSlugField({
  slug,
  auto,
  hint,
  onSave,
}: {
  /** wirksame Adresse */
  slug: string
  /** true: folgt dem Namen */
  auto: boolean
  hint: string
  onSave: (webSlug: string) => Promise<unknown>
}) {
  // Der Aufrufer setzt key aus Adresse und Art: ein neuer Wert beginnt mit frischem Text
  const [text, setText] = useState(auto ? '' : slug)
  const [error, setError] = useState<string | undefined>()
  async function commit() {
    const next = text.trim()
    if (next === (auto ? '' : slug)) return
    try {
      setError(undefined)
      await onSave(next)
    } catch (e) {
      setError(errorMessage(e))
    }
  }
  return (
    <Field
      label={t('Adresse auf der Webseite')}
      value={text}
      placeholder={slug || undefined}
      error={error}
      hint={hint}
      onChange={(e) => setText(e.target.value)}
      onBlur={() => void commit()}
    />
  )
}
