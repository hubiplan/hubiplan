/**
 * Namensform je Bereich der Webseite (Issue #709): Vorstand mit vollem Namen, Aktive als
 * „D. Muster“, Passive wieder voll. Ohne eigene Wahl gilt die Namensform der Webseite.
 * Gehört zur Gestaltung: erscheint erst nach „Veröffentlichen“.
 */
import { SelectField } from '../../components/ui.tsx'
import { t } from '../../i18n/index.ts'
import type { MenuItem, NameFormat } from '../../api/website.ts'

export const NAME_FORMAT_LABELS = (): Record<NameFormat, string> => ({
  full: t('Vorname Name'),
  short: t('V. Nachname'),
  initial: t('Vorname N.'),
})

const AREAS = (): { key: string; label: string }[] => [
  { key: 'board', label: t('Vorstand und Ansprechpartner') },
  { key: 'offices', label: t('Ämter und ihre Chronik') },
  { key: 'members', label: t('Mitgliederlisten') },
  { key: 'memorial', label: t('In Gedenken') },
  { key: 'honors', label: t('Würdenträger und Ehrungen') },
  { key: 'results', label: t('Ergebnisse') },
]

export function NameFormats({
  value,
  base,
  menuItems,
  onChange,
}: {
  value: Record<string, NameFormat>
  /** Namensform der Webseite (gilt, wo nichts gewählt ist) */
  base: NameFormat
  menuItems?: MenuItem[]
  onChange: (next: Record<string, NameFormat>) => void
}) {
  const labels = NAME_FORMAT_LABELS()
  const types = (menuItems ?? []).filter((it) => it.toggle?.startsWith('membertype:'))

  function choose(key: string, fmt: string) {
    const next = { ...value }
    if (fmt) next[key] = fmt as NameFormat
    else delete next[key]
    onChange(next)
  }

  const field = (key: string, label: string, fallback: NameFormat) => (
    <SelectField
      key={key}
      label={label}
      value={value[key] ?? ''}
      onChange={(e) => choose(key, e.target.value)}
    >
      <option value="">{t('wie oben ({format})', { format: labels[fallback] })}</option>
      {(Object.keys(labels) as NameFormat[]).map((fmt) => (
        <option key={fmt} value={fmt}>
          {labels[fmt]}
        </option>
      ))}
    </SelectField>
  )

  const membersFallback = value.members ?? base
  return (
    <details className="name-formats">
      <summary>{t('Namensform je Bereich')}</summary>
      <p className="muted small">
        {t(
          'Zum Beispiel den Vorstand mit vollem Namen und die Aktiven als „M. Muster“. Gehört zur Gestaltung und erscheint nach „Veröffentlichen“.',
        )}
      </p>
      <div className="grid-2">
        {AREAS().map((a) => field(a.key, a.label, base))}
        {types.map((it) =>
          field(
            it.toggle as string,
            t('Mitgliederliste „{name}“', { name: it.label || it.default_label || '' }),
            membersFallback,
          ),
        )}
      </div>
    </details>
  )
}
