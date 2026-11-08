// Einheitlicher Seitenkopf (UX-Audit 08.11. S-05, Konzept „Seitenkopf“): feste Plätze für
// Pfad, h1, Einheit, eine Hauptaktion und „Weitere Aktionen“. h1 und Pfad kommen aus der
// Menüstruktur (navTrail.ts), damit Überschrift und Menüpunkt gleich heißen.
import { createContext, useContext, useEffect, useId, useMemo, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import type { MouseEvent as ReactMouseEvent, ReactNode } from 'react'
import { Link, useLocation } from 'react-router-dom'
import { useNavTrail, trailTitle } from './navTrail.ts'
import type { TrailItem } from './navTrail.ts'
import { usePageTitle } from './pageTitle.ts'
import { t } from '../i18n/index.ts'
import './pageHeader.css'

export interface PageAction {
  label: string
  /** Seite in der App */
  to?: string
  /** Datei oder fremde Adresse, z. B. ein PDF */
  href?: string
  /** href in neuem Tab öffnen (z. B. PDF) */
  newTab?: boolean
  onClick?: () => void
  icon?: ReactNode
  /** Löschen und Ähnliches: steht im Menü immer zuletzt und rot abgesetzt */
  danger?: boolean
  disabled?: boolean
  /** Knopf klappt etwas auf (z. B. ein Formular): Zustand und Ziel für Screenreader */
  expanded?: boolean
  controls?: string
  /** Kurze Erklärung (title) */
  hint?: string
}

/** Zwei gleich wichtige Aktionen: ein Knopf mit Auswahl („Neue Buchung ▾“). */
export interface PageActionMenu {
  label: string
  items: PageAction[]
}

export function PageHeader({
  title: ownTitle,
  name,
  subtitle,
  primary,
  actions = [],
  extra,
  status,
  children,
  onBack,
}: {
  /** Nur für Seiten ohne eigenen Menüpunkt, z. B. eine Mitgliedsakte („Max Mustermann“) */
  title?: string
  /**
   * Name der Seite, falls sie keinen eigenen Menüpunkt hat (z. B. „Urkundenvorlagen“ unter
   * Wettbewerbe). Auf einer Seite mit Menüpunkt gilt die Beschriftung des Menüpunkts.
   */
  name?: string
  /** Ein Satz, was man hier tut */
  subtitle?: ReactNode
  /** Höchstens eine Hauptaktion; bei zwei gleich wichtigen ein Knopf mit Auswahl */
  primary?: PageAction | PageActionMenu | null
  /** Weitere Aktionen; erscheinen im Menü „Weitere Aktionen“ */
  actions?: (PageAction | false | null | undefined)[]
  /** Zusatzplatz für Sonderköpfe (Foto, Status, Nummer) */
  extra?: ReactNode
  /** Kurzer Zustand hinter der Überschrift, z. B. „nur lesen“ */
  status?: ReactNode
  /** Zusatzzeile unter der Überschrift, z. B. Status, Nummer, Ämter einer Mitgliedsakte */
  children?: ReactNode
  /** Detailansicht in einer Liste: der Weg zur Elternseite schließt sie (statt neu zu laden) */
  onBack?: () => void
}) {
  const { trail, unit } = useNavTrail()
  const slot = useContext(PageSlotContext)
  const { pathname } = useLocation()
  const menuPage = trail.at(-1)?.to === pathname.replace(/(.)\/$/, '$1')
  const title = ownTitle ?? (name && !menuPage ? name : undefined)
  const current = title ?? trail.at(-1)?.label ?? ''
  // Pfad ab der zweiten Ebene; das letzte Glied ist die Seite selbst
  const crumbs: TrailItem[] = title ? trail : trail.slice(0, -1)
  usePageTitle(title ? trailTitle(trail, title) : null)
  const more = actions.filter((a): a is PageAction => !!a)
  const parent = crumbs.at(-1)
  const back = (e: ReactMouseEvent) => {
    if (!onBack) return
    e.preventDefault()
    onBack()
  }

  return (
    <header className="page-header">
      {crumbs.length > 0 && (
        <nav className="page-header-trail" aria-label={t('Pfad')}>
          <ol>
            {crumbs.map((c) => (
              <li key={c.to}>
                <Link to={c.to} onClick={c === parent ? back : undefined}>
                  {c.label}
                </Link>
              </li>
            ))}
            <li>
              <span aria-current="page">{current}</span>
            </li>
          </ol>
          {parent && (
            <Link
              to={parent.to}
              className="page-header-back"
              onClick={back}
              aria-label={t('Zurück zu {label}', { label: parent.label })}
            >
              <span aria-hidden="true">‹ </span>
              {parent.label}
            </Link>
          )}
        </nav>
      )}
      <div className="page-header-main">
        {extra && <div className="page-header-extra">{extra}</div>}
        <div className="page-header-title">
          <h1>{current}</h1>
          {unit && <span className="page-header-unit">{unit}</span>}
          {status && <span className="page-header-status muted small">{status}</span>}
        </div>
        {/* Auch leer vorhanden: Unterseiten setzen ihre Aktionen per PageActions hierher */}
        <div className="page-header-actions" ref={slot?.setNode}>
          {more.length > 0 && <ActionMenu actions={more} />}
          {primary && <PrimaryAction action={primary} />}
        </div>
      </div>
      {subtitle && <p className="page-header-subtitle muted">{subtitle}</p>}
      {children && <div className="page-header-more">{children}</div>}
    </header>
  )
}

interface PageSlot {
  node: HTMLElement | null
  setNode: (node: HTMLElement | null) => void
}

const PageSlotContext = createContext<PageSlot | null>(null)

/** Im App-Rahmen: Platz für die Aktionen der Seite im Seitenkopf. */
export function PageSlotProvider({ children }: { children: ReactNode }) {
  const [node, setNode] = useState<HTMLElement | null>(null)
  const value = useMemo(() => ({ node, setNode }), [node])
  return <PageSlotContext.Provider value={value}>{children}</PageSlotContext.Provider>
}

/**
 * Aktionen einer Unterseite, deren Seitenkopf der Rahmen zeichnet (z. B. Finanzen › Rechnungen ›
 * Mahnungen): erscheinen im Kopf an den festen Plätzen. Ohne Seitenkopf stehen sie an Ort und
 * Stelle.
 */
export function PageActions({
  primary,
  actions = [],
}: {
  primary?: PageAction | PageActionMenu | null
  actions?: (PageAction | false | null | undefined)[]
}) {
  const slot = useContext(PageSlotContext)
  const more = actions.filter((a): a is PageAction => !!a)
  const body = (
    <>
      {more.length > 0 && <ActionMenu actions={more} />}
      {primary && <PrimaryAction action={primary} />}
    </>
  )
  if (slot?.node) return createPortal(body, slot.node)
  return <div className="page-header-actions page-actions-inline">{body}</div>
}

function PrimaryAction({ action }: { action: PageAction | PageActionMenu }) {
  if ('items' in action) {
    return (
      <ActionMenu
        actions={action.items}
        label={action.label}
        buttonClass="button button-primary page-header-primary"
        sort={false}
      />
    )
  }
  return <ActionButton action={action} className="button button-primary page-header-primary" />
}

function ActionButton({
  action,
  className,
  onDone,
}: {
  action: PageAction
  className: string
  onDone?: () => void
}) {
  const body = (
    <>
      {action.icon}
      {action.label}
    </>
  )
  if (action.to && !action.disabled)
    return (
      <Link to={action.to} className={className} title={action.hint} onClick={onDone}>
        {body}
      </Link>
    )
  if (action.href && !action.disabled)
    return (
      <a
        href={action.href}
        className={className}
        title={action.hint}
        onClick={onDone}
        {...(action.newTab ? { target: '_blank', rel: 'noreferrer' } : {})}
      >
        {body}
      </a>
    )
  return (
    <button
      type="button"
      className={className}
      title={action.hint}
      disabled={action.disabled}
      aria-expanded={action.expanded}
      aria-controls={action.controls}
      onClick={() => {
        onDone?.()
        action.onClick?.()
      }}
    >
      {body}
    </button>
  )
}

/** Aufklappliste „Weitere Aktionen“ (Handy: „⋯“); Gefährliches immer zuletzt. */
export function ActionMenu({
  actions,
  label,
  buttonClass = 'button button-ghost',
  sort = true,
}: {
  actions: PageAction[]
  /** Sichtbare Beschriftung; ohne: „Weitere Aktionen“, auf dem Handy nur „⋯“ */
  label?: string
  buttonClass?: string
  sort?: boolean
}) {
  const [open, setOpen] = useState(false)
  const id = useId()
  const ref = useRef<HTMLDivElement>(null)
  const buttonRef = useRef<HTMLButtonElement>(null)
  const items = sort
    ? [...actions.filter((a) => !a.danger), ...actions.filter((a) => a.danger)]
    : actions

  useEffect(() => {
    if (!open) return
    ref.current
      ?.querySelector<HTMLElement>('.action-menu-list a, .action-menu-list button')
      ?.focus()
    const onClick = (e: MouseEvent) => {
      if (!ref.current?.contains(e.target as Node)) setOpen(false)
    }
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== 'Escape' || e.defaultPrevented) return
      setOpen(false)
      buttonRef.current?.focus()
    }
    document.addEventListener('mousedown', onClick)
    window.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('mousedown', onClick)
      window.removeEventListener('keydown', onKey)
    }
  }, [open])

  return (
    <div className="action-menu" ref={ref}>
      <button
        type="button"
        ref={buttonRef}
        className={`${buttonClass}${label ? '' : ' action-menu-more'}`}
        aria-expanded={open}
        aria-controls={id}
        onClick={() => setOpen((o) => !o)}
      >
        {label ? (
          <>
            {label} <span aria-hidden="true">▾</span>
          </>
        ) : (
          <>
            <span className="action-menu-text">{t('Weitere Aktionen')}</span>
            <span className="action-menu-dots" aria-hidden="true">
              ⋯
            </span>
          </>
        )}
      </button>
      {open && (
        <ul className="action-menu-list" id={id}>
          {items.map((a, i) => (
            <li
              key={`${a.label}-${i}`}
              className={a.danger && !items[i - 1]?.danger && i > 0 ? 'action-menu-gap' : undefined}
            >
              <ActionButton
                action={a}
                className={`action-menu-item${a.danger ? ' action-menu-danger' : ''}`}
                onDone={() => setOpen(false)}
              />
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

/**
 * Ansichtswahl als Segmentschalter (W-14): zeigt einen Zustand, keine Aktion. Steht unter
 * dem Seitenkopf, nie darin; gewähltes Segment mit aria-pressed, nicht in Primärfarbe.
 */
export function Segmented<T extends string>({
  label,
  options,
  value,
  onChange,
}: {
  label: string
  options: { value: T; label: string }[]
  value: T
  onChange: (value: T) => void
}) {
  return (
    <div className="segmented" role="group" aria-label={label}>
      {options.map((o) => (
        <button
          key={o.value}
          type="button"
          className="button button-ghost"
          aria-pressed={o.value === value}
          onClick={() => onChange(o.value)}
        >
          {o.label}
        </button>
      ))}
    </div>
  )
}
