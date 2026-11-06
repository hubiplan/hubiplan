import { PRODUCT_NAME, usePlatform } from '../theme/platform.ts'

// Zeichen von HUBIplan: Akte mit H, der Querstrich ist ein ansteigender Steg
// (Entwurf C3, Ralf 31.10.2026). Akte in der Primärfarbe, Reiter und Steg in der
// Akzentfarbe, H-Striche weiß. Die Akte ist zugleich der Hintergrund, so bleibt das
// Zeichen auf hellem und dunklem Grund erkennbar.
export function LogoMark({ className = 'logo-img' }: { className?: string }) {
  return (
    <svg viewBox="2 3.5 60 60" className={className} aria-hidden="true">
      <path
        d="M4 20V15a8 8 0 0 1 8-8h9c2.5 0 4.2 1 5.6 2.6L30 14h22a8 8 0 0 1 8 8Z"
        fill="var(--color-accent)"
      />
      <rect x="4" y="18" width="56" height="42" rx="10" fill="var(--color-primary)" />
      <path d="M22 28V52M42 28V52" stroke="#fff" strokeWidth="7" strokeLinecap="round" />
      <path d="M22 44L42 35" stroke="var(--color-accent)" strokeWidth="7" strokeLinecap="round" />
    </svg>
  )
}

/**
 * Logo mit Namen. Ohne Namen: Name und Logo der Instanz (White Label, Vorgabe „HUBIplan“
 * mit dem H-Zeichen). Mit Namen einer Einheit: deren Logo, sonst das H-Zeichen in den
 * Farben, die gerade gelten.
 */
export function Logo({ name, logoUrl = null }: { name?: string; logoUrl?: string | null }) {
  const instance = usePlatform()
  const shown = name || instance.name
  const logo = name ? logoUrl : (logoUrl ?? instance.logo_url)
  return (
    <span className="logo">
      {logo ? <img src={logo} alt="" className="logo-img logo-upload" /> : <LogoMark />}
      {shown === PRODUCT_NAME ? (
        <span className="logo-name logo-wordmark">
          HUBI<span className="logo-wordmark-light">plan</span>
        </span>
      ) : (
        <span className="logo-name">{shown}</span>
      )}
    </span>
  )
}
