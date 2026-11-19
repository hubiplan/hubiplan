// Textfeld mit eigener Vorschlagsliste im HUBIplan-Design (statt HTML-datalist).
// Das Browsermenü einer datalist lässt sich nicht gestalten und erscheint je nach System
// schwarz, auch auf heller Seite (Ralf 19.11.). Freie Eingabe bleibt immer möglich.
// Barrierefrei nach dem ARIA-Muster „Combobox mit Listbox“: Pfeiltasten, Eingabe, Escape.
import { useId, useRef, useState } from 'react'
import type { InputHTMLAttributes, KeyboardEvent } from 'react'
import { t } from '../i18n/index.ts'
import { matchSuggestions } from './suggest.ts'
import type { Suggestion } from './suggest.ts'

export type { Suggestion }

/** Wert setzen wie bei einer Eingabe, damit onChange der Aufrufer wie gewohnt feuert. */
function typeValue(input: HTMLInputElement, value: string) {
  const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')?.set
  setter?.call(input, value)
  input.dispatchEvent(new Event('input', { bubbles: true }))
}

export function SuggestInput({
  suggestions,
  className,
  ...input
}: Omit<InputHTMLAttributes<HTMLInputElement>, 'list'> & { suggestions: Suggestion[] }) {
  const listId = useId()
  const ref = useRef<HTMLInputElement>(null)
  const [open, setOpen] = useState(false)
  const [active, setActive] = useState(-1)
  const query = typeof input.value === 'string' ? input.value : String(input.value ?? '')
  const shown = matchSuggestions(suggestions, query)
  const expanded = open && shown.length > 0
  const optionId = (i: number) => `${listId}-${i}`

  const show = (index = -1) => {
    setOpen(true)
    setActive(index)
  }
  const close = () => {
    setOpen(false)
    setActive(-1)
  }
  const pick = (s: Suggestion) => {
    if (ref.current) typeValue(ref.current, s.value)
    close()
  }
  const move = (to: number) => {
    const next = (to + shown.length) % shown.length
    setActive(next)
    document.getElementById(optionId(next))?.scrollIntoView?.({ block: 'nearest' })
  }

  const onKeyDown = (e: KeyboardEvent<HTMLInputElement>) => {
    input.onKeyDown?.(e)
    if (e.defaultPrevented || shown.length === 0) return
    if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
      e.preventDefault()
      const down = e.key === 'ArrowDown'
      if (!expanded) show(e.altKey ? -1 : down ? 0 : shown.length - 1)
      else move(active < 0 ? (down ? 0 : shown.length - 1) : active + (down ? 1 : -1))
    } else if (e.key === 'Enter' && expanded && active >= 0) {
      e.preventDefault()
      pick(shown[active])
    } else if (e.key === 'Escape' && expanded) {
      // nur die Liste schließen, nicht den Dialog drumherum
      e.preventDefault()
      e.stopPropagation()
      close()
    } else if (e.key === 'Tab') {
      close()
    }
  }

  return (
    <div className={`suggest${expanded ? ' is-open' : ''}`}>
      <input
        {...input}
        ref={ref}
        className={[className, 'suggest-input'].filter(Boolean).join(' ')}
        autoComplete="off"
        role="combobox"
        aria-autocomplete="list"
        aria-expanded={expanded}
        aria-controls={listId}
        aria-activedescendant={expanded && active >= 0 ? optionId(active) : undefined}
        onChange={(e) => {
          input.onChange?.(e)
          show()
        }}
        onClick={(e) => {
          input.onClick?.(e)
          if (!input.readOnly && !input.disabled) show()
        }}
        onKeyDown={onKeyDown}
        onBlur={(e) => {
          input.onBlur?.(e)
          close()
        }}
      />
      {suggestions.length > 0 && !input.disabled && !input.readOnly && (
        <button
          type="button"
          className="suggest-toggle"
          tabIndex={-1}
          aria-label={t('Vorschläge zeigen')}
          title={t('Vorschläge zeigen')}
          // Fokus im Feld lassen
          onMouseDown={(e) => e.preventDefault()}
          onClick={() => {
            ref.current?.focus()
            if (expanded) close()
            else show()
          }}
        >
          <svg viewBox="0 0 16 16" width="16" height="16" aria-hidden="true" focusable="false">
            <path d="M4 6l4 4 4-4" fill="none" stroke="currentColor" strokeWidth="2" />
          </svg>
        </button>
      )}
      <ul
        id={listId}
        role="listbox"
        className="suggest-list"
        hidden={!expanded}
        aria-label={t('Vorschläge')}
        // Klick in die Liste nimmt dem Feld nicht den Fokus
        onMouseDown={(e) => e.preventDefault()}
      >
        {expanded &&
          shown.map((s, i) => (
            <li
              key={`${s.value}\u0000${i}`}
              id={optionId(i)}
              role="option"
              aria-selected={i === active}
              className={i === active ? 'is-active' : undefined}
              onMouseEnter={() => setActive(i)}
              onClick={() => pick(s)}
            >
              <span className="suggest-value">{s.value}</span>
              {s.detail && <span className="suggest-detail">{s.detail}</span>}
            </li>
          ))}
      </ul>
    </div>
  )
}
