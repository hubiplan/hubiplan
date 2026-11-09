// Suche, Zeitraum und Blättern für lange Listen (Protokoll, Postausgang).
import { useState } from 'react'
import type { FormEvent, ReactNode } from 'react'
import type { ListQuery, Paged } from '../api/client.ts'
import { t, tc } from '../i18n/index.ts'

export function ListSearch({
  query,
  onChange,
  placeholder,
  children,
}: {
  query: ListQuery
  onChange: (q: ListQuery) => void
  placeholder: string
  /** zusätzliche Filter (z. B. Status) */
  children?: ReactNode
}) {
  const [text, setText] = useState(query.q ?? '')
  const [von, setVon] = useState(query.von ?? '')
  const [bis, setBis] = useState(query.bis ?? '')
  const submit = (e: FormEvent) => {
    e.preventDefault()
    onChange({ ...query, q: text.trim(), von, bis, seite: 1 })
  }
  const filtered = !!(query.q || query.von || query.bis)
  return (
    <form className="list-search" role="search" onSubmit={submit}>
      <label className="field">
        <span>{t('Suchen')}</span>
        <input
          type="search"
          value={text}
          placeholder={placeholder}
          onChange={(e) => setText(e.target.value)}
        />
      </label>
      <label className="field">
        <span>{t('von')}</span>
        <input type="date" value={von} onChange={(e) => setVon(e.target.value)} />
      </label>
      <label className="field">
        <span>{t('bis')}</span>
        <input type="date" value={bis} onChange={(e) => setBis(e.target.value)} />
      </label>
      {children}
      <div className="button-row">
        <button type="submit" className="button">
          {t('Suchen')}
        </button>
        {filtered && (
          <button
            type="button"
            className="button button-ghost"
            onClick={() => {
              setText('')
              setVon('')
              setBis('')
              onChange({ ...query, q: '', von: '', bis: '', seite: 1 })
            }}
          >
            {t('Suche zurücksetzen')}
          </button>
        )}
      </div>
    </form>
  )
}

/**
 * Gemeinsamer Blätter-Baustein: „‹ Vorherige“, Stand, „Nächste ›“ (UX-Audit 08.11., W-20 a).
 * Alle Listen blättern damit, damit Wortlaut, Vorlesetext und Abstände überall gleich sind.
 */
export function PageNav({
  prevDisabled,
  nextDisabled,
  onPrev,
  onNext,
  children,
}: {
  prevDisabled: boolean
  nextDisabled: boolean
  onPrev: () => void
  onNext: () => void
  /** Stand, z. B. „Seite 2 von 5“ */
  children?: ReactNode
}) {
  return (
    <div className="button-row pager">
      <button
        type="button"
        className="button button-ghost"
        aria-label={t('Vorherige Seite')}
        disabled={prevDisabled}
        onClick={onPrev}
      >
        <span aria-hidden="true">‹</span> {t('Vorherige')}
      </button>
      {children != null && children !== false && (
        <span className="small" aria-live="polite">
          {children}
        </span>
      )}
      <button
        type="button"
        className="button button-ghost"
        aria-label={t('Nächste Seite')}
        disabled={nextDisabled}
        onClick={onNext}
      >
        {t('Nächste')} <span aria-hidden="true">›</span>
      </button>
    </div>
  )
}

export function Pager({
  data,
  onPage,
  noun,
}: {
  data: Paged<unknown>
  onPage: (page: number) => void
  /** z. B. „Einträge“ */
  noun: string
}) {
  return (
    <PageNav
      prevDisabled={data.page <= 1}
      nextDisabled={data.page >= data.pages}
      onPrev={() => onPage(data.page - 1)}
      onNext={() => onPage(data.page + 1)}
    >
      {data.count} {noun} {t('· Seite {page} von', { page: data.page })} {Math.max(data.pages, 1)}
    </PageNav>
  )
}

/**
 * Blättern in einer schon geladenen Liste: „1–50 von 437 Einträgen“ (UX-Audit 31.10. W04).
 * Nichts anzeigen, wenn alles auf eine Seite passt.
 */
export function RangePager({
  page,
  size,
  total,
  onPage,
  noun,
}: {
  page: number
  size: number
  total: number
  onPage: (page: number) => void
  noun: string
}) {
  const pages = Math.max(1, Math.ceil(total / size))
  if (total <= size) return null
  const from = (page - 1) * size + 1
  const to = Math.min(total, page * size)
  return (
    <PageNav
      prevDisabled={page <= 1}
      nextDisabled={page >= pages}
      onPrev={() => onPage(page - 1)}
      onNext={() => onPage(page + 1)}
    >
      {from}–{to} {tc('count', 'von')} {total} {noun}
    </PageNav>
  )
}
