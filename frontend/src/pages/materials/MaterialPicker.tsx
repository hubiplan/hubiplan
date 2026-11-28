import { useEffect, useState } from 'react'
import { api } from '../../api/client.ts'
import type { MaterialChoice } from '../../api/materials.ts'
import { useQueryLoad } from '../../components/forms.ts'
import { t, locale } from '../../i18n/index.ts'
import './materials.css'

export function MaterialPicker({
  base,
  kind,
  onSelect,
}: {
  base: string
  kind: string
  onSelect: (choice: MaterialChoice) => void
}) {
  const [search, setSearch] = useState('')
  const [open, setOpen] = useState(false)
  const [debounced, setDebounced] = useState('')
  const query = search.trim()
  useEffect(() => {
    const timer = setTimeout(() => setDebounced(query), 250)
    return () => clearTimeout(timer)
  }, [query])
  const { data, error, loading } = useQueryLoad(
    () =>
      api.get<{ items: MaterialChoice[]; more: boolean }>(
        `${base}choices/?kind=${kind}&q=${encodeURIComponent(query)}`,
      ),
    [base, kind, query],
    open && query.length >= 2 && debounced === query,
  )
  return (
    <div
      className="material-picker member-picker"
      onFocus={() => setOpen(true)}
      onBlur={(e) => {
        if (!e.currentTarget.contains(e.relatedTarget)) setOpen(false)
      }}
      onKeyDown={(e) => {
        if (e.key === 'Escape') {
          e.stopPropagation()
          setOpen(false)
        }
      }}
    >
      <label>
        {t('Auswahl suchen')}
        <input
          type="search"
          value={search}
          onChange={(e) => {
            setSearch(e.target.value)
            setOpen(true)
          }}
        />
      </label>
      {open && query && (
        <small className="muted" role="status">
          {query.length < 2
            ? t('Mindestens 2 Zeichen eingeben.')
            : loading || debounced !== query
              ? t('Suche läuft …')
              : data?.items.length === 0
                ? t('Keine passenden Einträge gefunden.')
                : data
                  ? t('{n} Treffer', { n: data.items.length })
                  : ''}
        </small>
      )}
      {!!data?.items.length && (
        <ul className="picker-results material-picker-results" aria-label={t('Suchergebnisse')}>
          {data.items.map((choice) => (
            <li key={choice.id}>
              <button
                className="button button-ghost"
                type="button"
                onClick={() => {
                  onSelect(choice)
                  setSearch('')
                  setOpen(false)
                }}
              >
                {choice.title}
                {choice.starts_at && (
                  <span className="muted">
                    {new Date(choice.starts_at).toLocaleDateString(locale(), {
                      timeZone: 'Europe/Berlin',
                    })}
                  </span>
                )}
              </button>
            </li>
          ))}
        </ul>
      )}
      {data?.more && <p>{t('Bitte die Suche eingrenzen.')}</p>}
      {error && <p role="alert">{error}</p>}
    </div>
  )
}
