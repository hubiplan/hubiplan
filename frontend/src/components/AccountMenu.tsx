// „Mein Konto“ oben rechts: klappt die Unterseiten auf (statt eines Eintrags in der Seitenleiste).
import { useEffect, useRef, useState } from 'react'
import { NavLink, useLocation } from 'react-router-dom'
import { ACCOUNT_SECTIONS, isAccountPath } from '../pages/settings/accountNav.ts'
import { t } from '../i18n/index.ts'

export function AccountMenu({
  email,
  onLogout,
}: {
  email: string | undefined
  onLogout: () => Promise<void>
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
