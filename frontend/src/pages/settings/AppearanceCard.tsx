// Mein Konto › Profil › Darstellung: wie Gerät, hell oder dunkel (X-02, D1).
import { useState } from 'react'
import { appearanceApi } from '../../api/appearance.ts'
import { errorMessage } from '../../components/forms.ts'
import { Alert, Checkbox, SelectField } from '../../components/ui.tsx'
import { helpShortcutEnabled, setHelpShortcutEnabled } from '../../help/shortcut.ts'
import { t } from '../../i18n/index.ts'
import { colorSchemeChoice, setColorSchemeChoice } from '../../theme/colorScheme.ts'
import type { ColorSchemeChoice } from '../../theme/colorScheme.ts'

export function AppearanceCard() {
  const [value, setValue] = useState<ColorSchemeChoice>(colorSchemeChoice())
  const [busy, setBusy] = useState(false)
  const [shortcut, setShortcut] = useState(helpShortcutEnabled())
  const [error, setError] = useState<string | null>(null)

  async function choose(next: ColorSchemeChoice) {
    const before = value
    setError(null)
    setBusy(true)
    setValue(next)
    setColorSchemeChoice(next)
    try {
      const data = await appearanceApi.update(next)
      setValue(data.color_scheme)
      setColorSchemeChoice(data.color_scheme)
    } catch (err) {
      setValue(before)
      setColorSchemeChoice(before)
      setError(errorMessage(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="card card-wide">
      <h2>{t('Darstellung')}</h2>
      <SelectField
        label={t('Hell oder dunkel')}
        value={value}
        disabled={busy}
        onChange={(e) => void choose(e.target.value as ColorSchemeChoice)}
        hint={t(
          'Gilt für alle Seiten von HUBIplan und auf allen Geräten, an denen du angemeldet bist.',
        )}
      >
        <option value="light">{t('Hell')}</option>
        <option value="dark">{t('Dunkel')}</option>
        <option value="auto">{t('Wie Gerät')}</option>
      </SelectField>
      {/* VW-03: Einzeltasten-Kürzel abschaltbar (WCAG 2.1.4) */}
      <Checkbox
        label={t('Taste „?“ öffnet die Hilfe zu dieser Seite')}
        checked={shortcut}
        onChange={(on) => {
          setHelpShortcutEnabled(on)
          setShortcut(on)
        }}
        hint={t('Gilt in diesem Browser. Ausschalten hilft, wenn du mit Spracheingabe arbeitest.')}
      />
      {error && <Alert kind="error">{error}</Alert>}
    </div>
  )
}
