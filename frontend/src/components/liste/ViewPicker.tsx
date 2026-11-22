// Auswahl „Ansicht“ über einer Liste (Web-Oberfläche W11): Standard oder eine gemerkte Ansicht,
// dazu die aktuelle Einstellung unter einem Namen merken oder eine gemerkte löschen.
import { useState } from 'react'
import type { FormEvent } from 'react'
import { t } from '../../i18n/index.ts'
import { loadViews, sameParams, storeViews } from './savedViews.ts'
import type { SavedView } from './savedViews.ts'

export function ViewPicker<T extends object>({
  list,
  current,
  standard,
  onApply,
}: {
  /** Name der Liste samt Einheit, z. B. „mitglieder.7“ */
  list: string
  current: T
  standard: T
  onApply: (params: T) => void
}) {
  const [views, setViews] = useState<SavedView<T>[]>(() => loadViews<T>(list))
  const [naming, setNaming] = useState(false)
  const [name, setName] = useState('')
  const active = views.find((v) => sameParams(v.params, current))
  const isStandard = sameParams(standard, current)
  const value = active ? active.name : isStandard ? '' : '__eigen'

  function update(next: SavedView<T>[]) {
    setViews(next)
    storeViews(list, next)
  }

  function add(e: FormEvent) {
    e.preventDefault()
    const n = name.trim()
    if (!n) return
    update([...views.filter((v) => v.name !== n), { name: n, params: current }])
    setNaming(false)
    setName('')
  }

  return (
    <div className="view-picker">
      <label className="view-picker-select small">
        {t('Ansicht')}
        <select
          value={value}
          onChange={(e) => {
            const v = e.target.value
            if (v === '') onApply(standard)
            else {
              const found = views.find((x) => x.name === v)
              if (found) onApply(found.params)
            }
          }}
        >
          <option value="">{t('Standard')}</option>
          {views.map((v) => (
            <option key={v.name} value={v.name}>
              {v.name}
            </option>
          ))}
          {value === '__eigen' && (
            <option value="__eigen" disabled>
              {t('Eigene Auswahl')}
            </option>
          )}
        </select>
      </label>
      {active ? (
        <button
          type="button"
          className="button button-link small"
          onClick={() => update(views.filter((v) => v !== active))}
        >
          {t('Ansicht löschen')}
        </button>
      ) : (
        !isStandard &&
        !naming && (
          <button
            type="button"
            className="button button-link small"
            onClick={() => setNaming(true)}
          >
            {t('Als Ansicht merken')}
          </button>
        )
      )}
      {naming && (
        <form className="view-picker-form" onSubmit={add}>
          <input
            type="text"
            aria-label={t('Name der Ansicht')}
            placeholder={t('Name der Ansicht')}
            value={name}
            maxLength={40}
            autoFocus
            onChange={(e) => setName(e.target.value)}
          />
          <button type="submit" className="button button-primary small" disabled={!name.trim()}>
            {t('Merken')}
          </button>
          <button
            type="button"
            className="button button-ghost small"
            onClick={() => setNaming(false)}
          >
            {t('Abbrechen')}
          </button>
        </form>
      )}
    </div>
  )
}
