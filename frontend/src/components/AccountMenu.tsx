// „Mein Konto“ oben rechts: klappt die Unterseiten auf (statt eines Eintrags in der Seitenleiste).
import { useEffect, useRef, useState } from 'react'
import type { ReactNode } from 'react'
import { NavLink, useLocation } from 'react-router-dom'
import { ACCOUNT_SECTIONS, isAccountPath } from '../pages/settings/accountNav.ts'
import { t } from '../i18n/index.ts'

/** Persönliches eines Mitglieds (Mein Bereich), direkt aus dem Kontomenü erreichbar */
export interface PersonalArea {
  key: string
  /** Vereinsname, nur gezeigt, wenn jemand in mehreren Vereinen Mitglied ist */
  title?: string
  links: { to: string; label: string }[]
}

export function AccountMenu({
  email,
  onLogout,
  extra,
  personal = [],
  onPersonal,
}: {
  email: string | undefined
  onLogout: () => Promise<void>
  /** Selten gebrauchte Werkzeuge, z. B. „Ansicht als Rolle“ (UX-Audit W-06) */
  extra?: ReactNode
  personal?: PersonalArea[]
  /** Wechselt in den Bereich des Mitglieds und öffnet dort die Seite */
  onPersonal?: (key: string, to: string) => void
}) {
  const [open, setOpen] = useState(false)
  const [signingOut, setSigningOut] = useState(false)
  const { pathname } = useLocation()
  const ref = useRef<HTMLDivElement>(null)
  const buttonRef = useRef<HTMLButtonElement>(null)

  // Klick daneben oder Esc schließt
  useEffect(() => {
    if (!open) return
    const onClick = (e: MouseEvent) => {
      if (signingOut) return
      if (!ref.current?.contains(e.target as Node)) setOpen(false)
    }
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== 'Escape' || e.defaultPrevented || signingOut) return
      setOpen(false)
      buttonRef.current?.focus()
    }
    document.addEventListener('mousedown', onClick)
    window.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('mousedown', onClick)
      window.removeEventListener('keydown', onKey)
    }
  }, [open, signingOut])

  async function signOut() {
    if (signingOut) return
    setSigningOut(true)
    try {
      await onLogout()
    } finally {
      setSigningOut(false)
    }
  }

  return (
    <div className="account-menu" ref={ref}>
      <button
        type="button"
        ref={buttonRef}
        className={`button button-ghost${isAccountPath(pathname) ? ' active' : ''}`}
        aria-expanded={open}
        aria-controls="konto-menue"
        onClick={() => setOpen((o) => !o)}
      >
        <svg
          className="account-menu-icon"
          viewBox="0 0 24 24"
          width="20"
          height="20"
          aria-hidden="true"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
        >
          <circle cx="12" cy="8" r="4" />
          <path d="M4 20c1.5-4 4.5-6 8-6s6.5 2 8 6" />
        </svg>
        {/* Auf dem Handy nur das Symbol (W-05), der Name bleibt für Screenreader */}
        <span className="account-menu-label">{t('Mein Konto')}</span>{' '}
        <span aria-hidden="true">▾</span>
      </button>
      {open && (
        <nav id="konto-menue" className="account-menu-list" aria-label={t('Mein Konto')}>
          {email && <p className="account-menu-email">{email}</p>}
          {extra && <div className="account-menu-extra">{extra}</div>}
          {personal.map((area) => (
            <div key={area.key} className="account-menu-personal">
              <p className="account-menu-heading">
                {area.title ? t('Mein Bereich: {club}', { club: area.title }) : t('Mein Bereich')}
              </p>
              <ul>
                {area.links.map((l) => (
                  <li key={l.to}>
                    <button
                      type="button"
                      onClick={() => {
                        setOpen(false)
                        onPersonal?.(area.key, l.to)
                      }}
                    >
                      {l.label}
                    </button>
                  </li>
                ))}
              </ul>
            </div>
          ))}
          {personal.length > 0 && <p className="account-menu-heading">{t('Mein Konto')}</p>}
          <ul>
            {ACCOUNT_SECTIONS.map((s) => (
              <li key={s.to}>
                <NavLink to={s.to} end onClick={() => setOpen(false)}>
                  {s.label}
                </NavLink>
              </li>
            ))}
            <li className="account-menu-logout">
              <button type="button" onClick={() => void signOut()} disabled={signingOut}>
                {t('Abmelden')}
              </button>
            </li>
          </ul>
        </nav>
      )}
    </div>
  )
}
