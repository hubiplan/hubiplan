// Webseite › Domain: Server, von denen ein KI-Assistent Bilder per Adresse holen darf
// (KI-Schnittstelle W3, docs/mcp.md). Leer = keine; gespeichert wird beim Verlassen des Felds.
import { useEffect, useState } from 'react'
import { Field } from '../../components/ui.tsx'
import { t } from '../../i18n/index.ts'

export function ImageHosts({
  value,
  error,
  disabled,
  onChange,
}: {
  value: string[]
  error?: string
  disabled?: boolean
  onChange: (next: string[]) => void
}) {
  const joined = value.join(', ')
  const [text, setText] = useState(joined)
  useEffect(() => setText(joined), [joined])

  function commit() {
    const next = text
      .split(/[\s,;]+/)
      .map((h) => h.trim().toLowerCase())
      .filter(Boolean)
    if (next.join(', ') !== joined) onChange(next)
  }

  return (
    <Field
      label={t('Erlaubte Server')}
      value={text}
      error={error}
      disabled={disabled}
      placeholder={t('z. B. cloud.example.org')}
      hint={t(
        'Nur Rechnernamen, durch Komma getrennt, z. B. die Nextcloud des Vereins. Leer: Ein KI-Assistent kann keine Bilder per Adresse holen, nur über einen Hochladelink.',
      )}
      onChange={(e) => setText(e.target.value)}
      onBlur={commit}
    />
  )
}
