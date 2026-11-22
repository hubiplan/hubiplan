// „Neu“ in der Kopfzeile (Konzept Web-Oberfläche, Rahmen): alles, was die Person in der
// gewählten Einheit anlegen darf, an einer Stelle und von jeder Seite aus. Die Einträge kommen
// aus dem Katalog der Schnellaktionen, damit Startseite und Kopfzeile nie auseinanderlaufen.
import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import type { CatalogAction } from './home/roleActions.ts'
import { t } from '../i18n/index.ts'

export function NewMenu({ actions }: { actions: CatalogAction[] }) {
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)
  const buttonRef = useRef<HTMLButtonElement>(null)

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

  if (actions.length === 0) return null
  const groups = [...new Set(actions.map((a) => a.group))]
  return (
    <div className="account-menu new-menu" ref={ref}>
      <button
        type="button"
        ref={buttonRef}
        className="button button-primary new-menu-button"
        aria-expanded={open}
        aria-controls="neu-menue"
        onClick={() => setOpen((o) => !o)}
      >
        <svg
          viewBox="0 0 24 24"
          width="18"
          height="18"
          aria-hidden="true"
          fill="none"
          stroke="currentColor"
          strokeWidth="2.25"
          strokeLinecap="round"
        >
          <path d="M12 5v14M5 12h14" />
        </svg>
        <span>{t('Neu')}</span>
      </button>
      {open && (
        <nav id="neu-menue" className="account-menu-list new-menu-list" aria-label={t('Neu')}>
          {groups.map((group) => (
            <div key={group} className="account-menu-personal">
              {groups.length > 1 && <p className="account-menu-heading">{group}</p>}
              <ul>
                {actions
                  .filter((a) => a.group === group)
                  .map((a) => (
                    <li key={a.key}>
                      <Link to={a.to} onClick={() => setOpen(false)}>
                        {a.label}
                      </Link>
                    </li>
                  ))}
              </ul>
            </div>
          ))}
        </nav>
      )}
    </div>
  )
}
