// Schnellsuche im Kopf (Design „Frisch“ D7): Seiten des Menüs und, wo erlaubt, Mitglieder.
// Öffnet mit dem Knopf im Kopf oder Strg+K / ⌘K. Pfeiltasten wählen, Eingabe öffnet, Esc schließt.
import { useEffect, useId, useMemo, useRef, useState } from 'react'
import type { KeyboardEvent as ReactKeyboardEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import { memberApi } from '../api/members.ts'
import { Modal } from './Modal.tsx'
import { t } from '../i18n/index.ts'

export interface QuickPage {
  to: string
  label: string
  /** Bereich, zu dem ein Unterpunkt gehört, z. B. „Finanzen“ */
  parent?: string
}

interface Hit {
  key: string
  to: string
  label: string
  detail?: string
}

/** Befehlstaste + K, überall gleich geschrieben */
const MAC_SHORTCUT = '\u2318K'
const MAX_PAGES = 8
const MAX_MEMBERS = 6

function fold(text: string): string {
  return text.toLocaleLowerCase('de').normalize('NFD').replace(/[̀-ͯ]/g, '')
}

/** Seiten, deren Name oder Bereich alle Suchwörter enthält; Treffer am Wortanfang zuerst. */
export function matchPages(pages: QuickPage[], term: string): QuickPage[] {
  const words = fold(term).split(/\s+/).filter(Boolean)
  if (words.length === 0) return []
  const scored: { page: QuickPage; score: number }[] = []
  for (const page of pages) {
    const label = fold(page.label)
    const all = `${label} ${fold(page.parent ?? '')}`
    if (!words.every((w) => all.includes(w))) continue
    scored.push({ page, score: label.startsWith(words[0]) ? 0 : label.includes(words[0]) ? 1 : 2 })
  }
  return scored
    .sort((a, b) => a.score - b.score)
    .slice(0, MAX_PAGES)
    .map((s) => s.page)
}

function isTyping(target: EventTarget | null): boolean {
  const el = target as HTMLElement | null
  return !!el?.closest?.('input, textarea, select, [contenteditable="true"]')
}

export function QuickSearch({
  pages,
  memberOrg,
}: {
  pages: QuickPage[]
  /** Einheit, deren Mitglieder die Person suchen darf; sonst null */
  memberOrg: number | null
}) {
  const [open, setOpen] = useState(false)
  const mac = typeof navigator !== 'undefined' && /Mac|iPhone|iPad/.test(navigator.platform)

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key.toLowerCase() !== 'k' || !(e.ctrlKey || e.metaKey) || e.altKey || e.shiftKey) return
      // In Textfeldern gehört Strg+K dem Feld (z. B. Link einfügen im Editor)
      if (isTyping(e.target)) return
      e.preventDefault()
      setOpen(true)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])

  return (
    <>
      <button
        type="button"
        className="button quick-search-button"
        aria-haspopup="dialog"
        aria-keyshortcuts={mac ? 'Meta+K' : 'Control+K'}
        onClick={() => setOpen(true)}
      >
        <svg
          viewBox="0 0 24 24"
          width="18"
          height="18"
          aria-hidden="true"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
        >
          <circle cx="11" cy="11" r="6.5" />
          <path d="m20 20-4.2-4.2" />
        </svg>
        <span>{t('Schnellsuche')}</span>
        <kbd aria-hidden="true">{mac ? MAC_SHORTCUT : t('Strg K')}</kbd>
      </button>
      {open && (
        <QuickSearchDialog pages={pages} memberOrg={memberOrg} onClose={() => setOpen(false)} />
      )}
    </>
  )
}

function QuickSearchDialog({
  pages,
  memberOrg,
  onClose,
}: {
  pages: QuickPage[]
  memberOrg: number | null
  onClose: () => void
}) {
  const navigate = useNavigate()
  const [term, setTerm] = useState('')
  const [members, setMembers] = useState<{ term: string; hits: Hit[] }>({ term: '', hits: [] })
  const [index, setIndex] = useState(0)
  const inputRef = useRef<HTMLInputElement>(null)
  const listId = useId()
  const query = term.trim()

  useEffect(() => {
    inputRef.current?.focus()
  }, [])

  // Mitglieder erst ab zwei Zeichen und mit kurzer Pause suchen
  useEffect(() => {
    if (memberOrg === null || query.length < 2) return
    let stale = false
    const timer = setTimeout(() => {
      memberApi
        .list(memberOrg, { suche: query, status: 'alle', page_size: MAX_MEMBERS })
        .then((page) => {
          if (stale) return
          setMembers({
            term: query,
            hits: page.results.map((m) => ({
              key: `m${m.id}`,
              to: `/mitglieder/${m.id}`,
              label: [m.first_name, m.last_name].filter(Boolean).join(' '),
              detail: m.club_number ? t('Nr. {nr}', { nr: m.club_number }) : undefined,
            })),
          })
        })
        .catch(() => {
          if (!stale) setMembers({ term: query, hits: [] })
        })
    }, 250)
    return () => {
      stale = true
      clearTimeout(timer)
    }
  }, [memberOrg, query])

  const pageHits = useMemo<Hit[]>(
    () =>
      matchPages(pages, query).map((p) => ({
        key: `p${p.to}`,
        to: p.to,
        label: p.label,
        detail: p.parent,
      })),
    [pages, query],
  )
  const memberHits = memberOrg !== null && members.term === query ? members.hits : []
  const hits = [...pageHits, ...memberHits]
  const current = Math.min(index, Math.max(hits.length - 1, 0))
  const optionId = (i: number) => `${listId}-${i}`

  function go(hit: Hit) {
    onClose()
    navigate(hit.to)
  }

  function onKeyDown(e: ReactKeyboardEvent<HTMLInputElement>) {
    if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
      e.preventDefault()
      if (hits.length === 0) return
      const step = e.key === 'ArrowDown' ? 1 : -1
      setIndex((current + step + hits.length) % hits.length)
    } else if (e.key === 'Enter' && hits[current]) {
      e.preventDefault()
      go(hits[current])
    }
  }

  const group = (title: string, items: Hit[], offset: number) =>
    items.length > 0 && (
      <li role="presentation">
        <div className="quick-search-group" id={`${listId}-g${offset}`}>
          {title}
        </div>
        <ul role="group" aria-labelledby={`${listId}-g${offset}`}>
          {items.map((hit, i) => (
            <li
              key={hit.key}
              id={optionId(offset + i)}
              role="option"
              aria-selected={offset + i === current}
              className={offset + i === current ? 'is-active' : undefined}
              onMouseMove={() => setIndex(offset + i)}
              onClick={() => go(hit)}
            >
              <span>{hit.label}</span>
              {hit.detail && <span className="muted small">{hit.detail}</span>}
            </li>
          ))}
        </ul>
      </li>
    )

  return (
    <Modal title={t('Schnellsuche')} onClose={onClose}>
      <div className="quick-search">
        <input
          ref={inputRef}
          type="search"
          role="combobox"
          aria-expanded={hits.length > 0}
          aria-controls={listId}
          aria-autocomplete="list"
          aria-activedescendant={hits.length > 0 ? optionId(current) : undefined}
          aria-label={memberOrg !== null ? t('Seite oder Mitglied suchen') : t('Seite suchen')}
          placeholder={memberOrg !== null ? t('Seite oder Mitglied suchen …') : t('Seite suchen …')}
          autoComplete="off"
          value={term}
          onChange={(e) => {
            setTerm(e.target.value)
            setIndex(0)
          }}
          onKeyDown={onKeyDown}
        />
        <ul className="quick-search-list" id={listId} role="listbox" aria-label={t('Treffer')}>
          {group(t('Seiten'), pageHits, 0)}
          {group(t('Mitglieder'), memberHits, pageHits.length)}
        </ul>
        <p className="muted small" role="status">
          {query.length === 0
            ? t('Pfeiltasten wählen, Eingabe öffnet, Esc schließt.')
            : hits.length === 0
              ? t('Nichts gefunden.')
              : t('{n} Treffer', { n: hits.length })}
        </p>
      </div>
    </Modal>
  )
}
