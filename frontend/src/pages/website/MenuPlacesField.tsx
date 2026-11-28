import type { MenuItem, MenuNode, MenuPlace } from '../../api/website.ts'
import { Alert, SelectField } from '../../components/ui.tsx'
import { t } from '../../i18n/index.ts'
import { normalizeMenu } from './menuTree.ts'

/** Platz der Hauptpunkte (Webseite #75): nur im Menü, nur im Fuß (neben Impressum und
 * Datenschutz) oder in beiden; z. B. „Kontakt“ aus der vollen Menüleiste in den Fuß. */
export function MenuPlacesField({
  items,
  menu,
  names,
  value,
  error,
  disabled,
  onChange,
}: {
  items: MenuItem[]
  menu: MenuNode[]
  names: Record<string, string>
  value: Record<string, MenuPlace>
  error?: string
  disabled: boolean
  onChange: (next: Record<string, MenuPlace>) => void
}) {
  const byKey = new Map(items.map((it) => [it.key, it]))
  // Wie beim Knopf nur einfache Hauptpunkte: keine Überschrift, kein Aufklappmenü
  const rows = normalizeMenu(menu, items)
    .filter((n) => n.children.length === 0 && byKey.has(n.key) && !byKey.get(n.key)!.heading)
    .map((n) => {
      const it = byKey.get(n.key)!
      return { key: n.key, label: (it.renamable && names[n.key]?.trim()) || it.label }
    })
  if (rows.length === 0) return null
  return (
    <details className="menue-plaetze">
      <summary>{t('Menüpunkte im Fuß')}</summary>
      <p className="muted small">
        {t(
          'Ein Punkt kann statt im Menü im Fuß neben Impressum und Datenschutz stehen, oder in beiden. Die Seite bleibt erreichbar und ihr Baustein bleibt an.',
        )}
      </p>
      <div className="grid-2">
        {rows.map((row) => (
          <SelectField
            key={row.key}
            label={row.label}
            value={value[row.key] ?? ''}
            disabled={disabled}
            onChange={(e) => {
              const next = { ...value }
              const place = e.target.value as MenuPlace | ''
              if (place) next[row.key] = place
              else delete next[row.key]
              onChange(next)
            }}
          >
            <option value="">{t('im Menü')}</option>
            <option value="footer">{t('nur im Fuß')}</option>
            <option value="both">{t('im Menü und im Fuß')}</option>
          </SelectField>
        ))}
      </div>
      {error && <Alert kind="error">{error}</Alert>}
    </details>
  )
}
