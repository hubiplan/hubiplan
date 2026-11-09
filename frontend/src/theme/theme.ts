// Laufzeit-Theme der aktiven Organisation. Das Backend liefert das bereits
// vererbte Erscheinungsbild (Abteilung ← Verein ← Dachverband ← Plattform) und
// die lesbare Schriftfarbe auf Primär- und Akzentfarbe.

export interface ThemeColors {
  primary: string
  on_primary: string
  accent: string
  on_accent: string
}

import { contrastRatio, readableOn } from './contrast.ts'

const VARS = [
  '--color-primary',
  '--color-primary-hover',
  '--color-link',
  '--color-focus',
  '--color-on-primary',
  '--color-accent',
  '--color-on-accent',
  '--sidebar-bg',
  '--sidebar-muted',
  '--sidebar-focus',
  '--button-brand-primary',
  '--button-brand-primary-hover',
  '--button-brand-on-primary',
] as const

/** Seitenhintergrund (--color-bg in theme.css): Links stehen auf Weiß und auf ihm. */
export const PAGE_BG = '#eef0ed'

/** Farbe mit Schwarz mischen (0 = unverändert, 1 = schwarz). */
export function darken(hex: string, amount: number): string {
  const n = parseInt(hex.slice(1), 16)
  const ch = (shift: number) => Math.round(((n >> shift) & 255) * (1 - amount))
  return `#${[16, 8, 0].map((s) => ch(s).toString(16).padStart(2, '0')).join('')}`
}

/** Farbe mit Weiß mischen (0 = unverändert, 1 = weiß). */
export function lighten(hex: string, amount: number): string {
  const n = parseInt(hex.slice(1), 16)
  const ch = (shift: number) => {
    const c = (n >> shift) & 255
    return Math.round(c + (255 - c) * amount)
  }
  return `#${[16, 8, 0].map((s) => ch(s).toString(16).padStart(2, '0')).join('')}`
}

/** Fließtext (--color-text in theme.css). */
export const TEXT_COLOR = '#121614'

/** Erreicht ein Link-Ton beide Ziele: 4,5 : 1 zum Grund und 3 : 1 zum Fließtext? */
function linkContrastOk(c: string): boolean {
  return (
    Math.min(contrastRatio(c, '#ffffff'), contrastRatio(c, PAGE_BG)) >= 4.5 &&
    contrastRatio(c, TEXT_COLOR) >= 3
  )
}

/**
 * Linkfarbe aus der Primärfarbe: ein Ton der Vereinsfarbe, so wenig wie nötig abgedunkelt
 * oder aufgehellt, bis normaler Text auf Weiß und auf dem Seitenhintergrund 4,5 : 1 erreicht
 * (WCAG 1.4.3, UI-Audit NUI-04) und der Link sich zugleich mit 3 : 1 vom Fließtext abhebt
 * (WCAG 1.4.1, Technik G183; UX-Audit 08.11., W-16). Links werden nie unterstrichen; so
 * bleiben sie auch bei dunklen Vereinsfarben an der Farbe erkennbar. Die Markenfarbe
 * selbst bleibt.
 */
export function linkColor(primary: string): string {
  if (linkContrastOk(primary)) return primary
  for (let step = 1; step <= 100; step++) {
    for (const c of [darken(primary, step / 100), lighten(primary, step / 100)]) {
      if (linkContrastOk(c)) return c
    }
  }
  // Kommt bei den heutigen Grundfarben nicht vor: neutrales Grau, das beide Ziele erfüllt
  return '#646464'
}

/** Schrift der Seitenleiste (--sidebar-text in theme.css). */
export const SIDEBAR_TEXT = '#d7e4df'

/** Farbe a mit Deckkraft alpha über b (wie color-mix mit transparent über b). */
export function blend(a: string, b: string, alpha: number): string {
  const x = parseInt(a.slice(1), 16)
  const y = parseInt(b.slice(1), 16)
  const ch = (shift: number) =>
    Math.round(((x >> shift) & 255) * alpha + ((y >> shift) & 255) * (1 - alpha))
  return `#${[16, 8, 0].map((sh) => ch(sh).toString(16).padStart(2, '0')).join('')}`
}

/**
 * Seitenleiste aus der Primärfarbe (stark abgedunkelt). Bei hellen Vereinsfarben so weit
 * dunkler, dass die Schrift auch auf dem markierten Punkt 4,5 : 1 erreicht (UX-Audit 08.11., W-15).
 */
export function sidebarColor(primary: string): string {
  for (let amount = 0.55; amount < 1; amount += 0.025) {
    const bg = darken(primary, amount)
    // Markierter Punkt: 12 % Weiß darüber (--sidebar-active-bg)
    if (contrastRatio(SIDEBAR_TEXT, blend('#ffffff', bg, 0.12)) >= 4.5) return bg
  }
  return '#000000'
}

/**
 * Gedämpfte Schrift der Seitenleiste (Gruppen- und Zwischenüberschriften): 70 % Deckkraft,
 * bei hellen Vereinsfarben so viel kräftiger wie nötig für 4,5 : 1 (WCAG 1.4.3, W-15).
 */
export function sidebarMuted(sidebar: string): string {
  for (let alpha = 0.7; alpha < 1; alpha += 0.05) {
    const c = blend(SIDEBAR_TEXT, sidebar, alpha)
    if (contrastRatio(c, sidebar) >= 4.5) return c
  }
  return SIDEBAR_TEXT
}

/**
 * Hoverfarbe für gefüllte Schaltflächen: in die Richtung, in der die Schrift
 * besser lesbar bleibt (helle Schrift → dunkler, dunkle Schrift → heller).
 */
export function hoverColor(primary: string, onPrimary: string): string {
  const darker = darken(primary, 0.15)
  const lighter = lighten(primary, 0.15)
  return contrastRatio(darker, onPrimary) >= contrastRatio(lighter, onPrimary) ? darker : lighter
}

/** Auch eine sehr helle Vereinsfarbe darf den Aktionsknopf nicht im Hintergrund verlieren. */
export function buttonColors(primary: string, onPrimary: string) {
  const background = contrastRatio(primary, PAGE_BG) >= 1.35 ? primary : linkColor(primary)
  const foreground =
    contrastRatio(background, onPrimary) >= 4.5
      ? onPrimary
      : contrastRatio(background, '#ffffff') >= 4.5
        ? '#ffffff'
        : '#000000'
  const candidate = hoverColor(background, foreground)
  const hover = contrastRatio(candidate, PAGE_BG) >= 1.35 ? candidate : darken(background, 0.15)
  return { background, foreground, hover }
}

/** CSS-Variablen, die ein Erscheinungsbild setzt (Namen wie in theme.css). */
export function themeVars(theme: ThemeColors): Record<(typeof VARS)[number], string> {
  const button = buttonColors(theme.primary, theme.on_primary)
  const sidebar = sidebarColor(theme.primary)
  return {
    '--color-primary': theme.primary,
    '--button-brand-primary': button.background,
    '--button-brand-primary-hover': button.hover,
    '--button-brand-on-primary': button.foreground,
    '--color-primary-hover': hoverColor(theme.primary, theme.on_primary),
    '--color-link': linkColor(theme.primary),
    // Fokusrahmen, Feldfokus und Häkchen: dieselbe abgedunkelte Farbe, damit sie auch bei
    // hellen Vereinsfarben (Gold, Gelb, Hellblau) deutlich zu sehen sind (WCAG 1.4.11)
    '--color-focus': linkColor(theme.primary),
    '--color-on-primary': theme.on_primary,
    '--color-accent': theme.accent,
    '--color-on-accent': theme.on_accent,
    '--sidebar-bg': sidebar,
    '--sidebar-muted': sidebarMuted(sidebar),
    // Fokusrahmen in der Seitenleiste: Weiß oder Schwarz, je nachdem was dort absticht
    '--sidebar-focus': readableOn(sidebar),
  }
}

/**
 * Erscheinungsbild der aktiven Einheit direkt am Wurzelelement. null: keines, dann gilt
 * das der Instanz (applyPlatformTheme) und darunter der Standard aus theme.css.
 */
export function applyTheme(
  theme: ThemeColors | null,
  root: HTMLElement = document.documentElement,
) {
  if (!theme) {
    for (const v of VARS) root.style.removeProperty(v)
    return
  }
  for (const [name, value] of Object.entries(themeVars(theme))) root.style.setProperty(name, value)
}

const PLATFORM_STYLE_ID = 'plattform-farben'

/**
 * Farben der Instanz (White Label) als eigene Stilregel für :root. Sie liegt über
 * theme.css, aber unter den Farben einer Einheit, die applyTheme direkt am Element
 * setzt. So gewinnt immer die Einheit, und ohne Einheit gilt die Instanz.
 */
export function applyPlatformTheme(theme: ThemeColors | null, doc: Document = document) {
  let el = doc.getElementById(PLATFORM_STYLE_ID)
  if (!theme) {
    el?.remove()
    return
  }
  if (!el) {
    el = doc.createElement('style')
    el.id = PLATFORM_STYLE_ID
  }
  // Immer ans Ende, damit die Regel nach theme.css kommt
  doc.head.appendChild(el)
  const vars = Object.entries(themeVars(theme))
    .map(([name, value]) => `${name}: ${value};`)
    .join(' ')
  el.textContent = `:root { ${vars} }`
}
