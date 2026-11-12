// Titel vor dem Namen (Dr., Prof. …): Auswahlliste mit den üblichen Titeln oder frei
// eingetragen (Ralf 12.11.). Steht in Anrede und Anschrift; die Webseite nennt ihn nur
// mit „Titel vor dem Namen nennen“.
import { useState } from 'react'
import { Field, SelectField } from './ui.tsx'
import { t } from '../i18n/index.ts'

const TITLES = ['Dr.', 'Dr. Dr.', 'Prof.', 'Prof. Dr.'] as const
const TITLE_MAX_LENGTH = 30
const OTHER = '__anderer__'

export function TitleField({
  value,
  onChange,
  error,
  hint,
  disabled,
}: {
  value: string
  onChange: (value: string) => void
  error?: string
  hint?: string
  disabled?: boolean
}) {
  const known = value === '' || (TITLES as readonly string[]).includes(value)
  // „Anderer …“ gewählt, aber noch nichts eingetragen: Textfeld trotzdem zeigen
  const [other, setOther] = useState(!known)
  const free = other || !known
  return (
    <>
      <SelectField
        label={t('Titel')}
        value={free ? OTHER : value}
        error={free ? undefined : error}
        hint={free ? undefined : hint}
        disabled={disabled}
        autoComplete="honorific-prefix"
        onChange={(ev) => {
          if (ev.target.value === OTHER) {
            // bisherigen Titel zum Bearbeiten übernehmen
            setOther(true)
          } else {
            setOther(false)
            onChange(ev.target.value)
          }
        }}
      >
        <option value="">{t('kein Titel')}</option>
        {TITLES.map((title) => (
          <option key={title} value={title}>
            {title}
          </option>
        ))}
        <option value={OTHER}>{t('anderer Titel …')}</option>
      </SelectField>
      {free && (
        <Field
          label={t('Anderer Titel')}
          value={value}
          maxLength={TITLE_MAX_LENGTH}
          placeholder={t('z. B. Dipl.-Ing.')}
          error={error}
          hint={hint}
          disabled={disabled}
          autoComplete="honorific-prefix"
          onChange={(ev) => onChange(ev.target.value)}
        />
      )}
    </>
  )
}
