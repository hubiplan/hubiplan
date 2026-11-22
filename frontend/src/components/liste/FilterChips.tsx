// Gesetzte Filter als Chips über einer Liste (Web-Oberfläche W11, Tabellenbaustein).
// Jeder Chip nennt Filter und Wert und lässt sich mit einem Klick entfernen.
import { t } from '../../i18n/index.ts'

export interface ActiveFilter {
  key: string
  /** z. B. „Mitgliedsart: Aktive“ */
  label: string
  onRemove: () => void
}

export function FilterChips({
  filters,
  onClearAll,
}: {
  filters: ActiveFilter[]
  /** Setzt alle Filter auf den Standard zurück; ohne diese Angabe kein Sammelknopf */
  onClearAll?: () => void
}) {
  if (filters.length === 0) return null
  return (
    <div className="filter-chips" role="group" aria-label={t('Gesetzte Filter')}>
      {filters.map((f) => (
        <button
          key={f.key}
          type="button"
          className="filter-chip"
          aria-label={t('Filter entfernen: {label}', { label: f.label })}
          onClick={f.onRemove}
        >
          <span>{f.label}</span>
          <span aria-hidden="true" className="filter-chip-x">
            ×
          </span>
        </button>
      ))}
      {onClearAll && filters.length > 1 && (
        <button type="button" className="button button-link small" onClick={onClearAll}>
          {t('Alle Filter entfernen')}
        </button>
      )}
    </div>
  )
}
