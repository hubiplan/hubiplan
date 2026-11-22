// „Zu erledigen“ in der Kopfzeile (Konzept Web-Oberfläche, Rahmen): die Zahl dessen, was in der
// gewählten Einheit auf die Person wartet, von jeder Seite aus. Dieselben Einträge wie in der
// Kachel der Startseite; geladen wird beim Wechsel der Einheit und beim Öffnen.
import { useCallback, useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { orgApi } from '../api/orgs.ts'
import type { OpenTask, OrgSummary } from '../api/orgs.ts'
import { t, tn } from '../i18n/index.ts'

/** So viele Einträge zeigt die Liste; der Rest steht auf der Startseite */
const SHOWN = 8

export function TodoMenu({ org }: { org: OrgSummary }) {
  const [open, setOpen] = useState(false)
  const [items, setItems] = useState<OpenTask[] | null>(null)
  const ref = useRef<HTMLDivElement>(null)
  const buttonRef = useRef<HTMLButtonElement>(null)
  const orgId = org.id

  const load = useCallback(() => {
    let alive = true
    orgApi
      .openTasks(orgId)
      .then((d) => alive && setItems(d.items))
      .catch(() => alive && setItems(null))
    return () => {
      alive = false
    }
  }, [orgId])
  useEffect(() => load(), [load])

  // Klick daneben oder Esc schließt
  useEffect(() => {
    if (!open) return
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

  const count = items?.length ?? 0
  const name =
    count > 0
      ? tn('Zu erledigen: {n} Eintrag', 'Zu erledigen: {n} Einträge', count)
      : t('Zu erledigen')
  return (
    <div className="account-menu todo-menu" ref={ref}>
      <button
        type="button"
        ref={buttonRef}
        className="button button-ghost todo-menu-button"
        aria-expanded={open}
        aria-controls="erledigen-menue"
        aria-label={name}
        title={t('Zu erledigen')}
        onClick={() => {
          if (!open) load()
          setOpen((o) => !o)
        }}
      >
        <svg
          viewBox="0 0 24 24"
          width="20"
          height="20"
          aria-hidden="true"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
        >
          <path d="M4 5h16v15H4zM8 12l3 3 5-7" />
        </svg>
        {count > 0 && (
          <span className="todo-menu-count" aria-hidden="true">
            {count > 99 ? '99+' : count}
          </span>
        )}
      </button>
      {open && (
        <nav
          id="erledigen-menue"
          className="account-menu-list todo-menu-list"
          aria-label={t('Zu erledigen')}
        >
          <p className="account-menu-heading">{t('Zu erledigen')}</p>
          {count === 0 && <p className="todo-menu-empty muted">{t('Nichts zu erledigen.')}</p>}
          <ul>
            {(items ?? []).slice(0, SHOWN).map((tm, i) => (
              <li key={`${tm.kind}-${i}`}>
                <Link to={tm.link} onClick={() => setOpen(false)}>
                  <span className="todo-menu-title">{tm.title}</span>
                  <span className="todo-menu-kind">
                    {tm.kind_label}
                    {tm.highlight && tm.due_label ? ` · ${tm.due_label}` : ''}
                  </span>
                </Link>
              </li>
            ))}
          </ul>
          <div className="account-menu-logout">
            <Link to="/" onClick={() => setOpen(false)}>
              {count > SHOWN ? t('Alle {n} auf der Startseite', { n: count }) : t('Zur Startseite')}
            </Link>
          </div>
        </nav>
      )}
    </div>
  )
}
