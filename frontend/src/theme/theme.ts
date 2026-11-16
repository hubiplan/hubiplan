// Laufzeit-Theme der aktiven Organisation. Das Backend liefert das bereits
// vererbte Erscheinungsbild (Abteilung ← Verein ← Dachverband ← Plattform) und
// die lesbare Schriftfarbe auf Primär- und Akzentfarbe.

export interface ThemeColors {
  primary: string
  on_primary: string
  accent: string
  on_accent: string
  /** Palette und Farbrollen (Ralf 13.11.2026); fehlen bei Seiten ohne Einheit */
  palette?: { color: string }[]
  palette_roles?: Partial<Record<AppRole, number>>
  palette_roles_in_app?: boolean
}

import { contrastRatio, readableOn } from './contrast.ts'

/** Rollen, die eine Vereinsfarbe in der Oberfläche übernehmen kann */
export type AppRole = 'text' | 'muted' | 'surface' | 'background'

const BASE_VARS = [
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
/** Nur mit Farbrollen und nur im hellen Modus gesetzt */
const ROLE_VARS = [
  '--color-text',
  '--color-text-muted',
  '--color-surface',
  '--color-bg',
  '--color-input-bg',
] as const
const VARS = [...BASE_VARS, ...ROLE_VARS]
type ThemeVars = Record<(typeof BASE_VARS)[number], string> &
  Partial<Record<(typeof ROLE_VARS)[number], string>>

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

/**
 * Farbe aufhellen und dabei den Farbton behalten (0 = unverändert, 1 = fast weiß). Anders als
 * `lighten` mischt das kein Weiß bei: Ein dunkles Vereinsgrün wird ein helles Grün und kein Grau.
 */
export function brighten(hex: string, amount: number): string {
  const n = parseInt(hex.slice(1), 16)
  const [r, g, b] = [16, 8, 0].map((s) => ((n >> s) & 255) / 255)
  const max = Math.max(r, g, b)
  const min = Math.min(r, g, b)
  const l = (max + min) / 2
  const d = max - min
  const sat = d === 0 ? 0 : d / (1 - Math.abs(2 * l - 1))
  let h = 0
  if (d !== 0) {
    if (max === r) h = ((g - b) / d) % 6
    else if (max === g) h = (b - r) / d + 2
    else h = (r - g) / d + 4
  }
  const light = l + (0.96 - l) * amount
  const c = (1 - Math.abs(2 * light - 1)) * sat
  const x = c * (1 - Math.abs((h % 2) - 1))
  const m = light - c / 2
  const sector = ((Math.floor(h) % 6) + 6) % 6
  const rgb = [
    [c, x, 0],
    [x, c, 0],
    [0, c, x],
    [0, x, c],
    [x, 0, c],
    [c, 0, x],
  ][sector]
  return `#${rgb
    .map((v) =>
      Math.round(Math.min(1, Math.max(0, v + m)) * 255)
        .toString(16)
        .padStart(2, '0'),
    )
    .join('')}`
}

/** Fließtext (--color-text in theme.css). */
export const TEXT_COLOR = '#121614'

/** Anteil der Vereinsfarbe in --color-brand-soft (theme.css), hell und dunkel. */
export const BRAND_SOFT = 0.1
export const BRAND_SOFT_DARK = 0.22

/** Getönte Fläche in Vereinsfarbe (--color-brand-soft): markierter Menüpunkt, Symbolkästchen. */
export function brandSoft(primary: string, surface = '#ffffff'): string {
  return blend(primary, surface, surface === '#ffffff' ? BRAND_SOFT : BRAND_SOFT_DARK)
}

/**
 * Erreicht ein Link-Ton beide Ziele: 4,5 : 1 zum Grund (auch zur getönten Fläche der
 * Vereinsfarbe, auf der markierte Punkte stehen) und 3 : 1 zum Fließtext?
 */
function linkContrastOk(c: string, primary: string): boolean {
  return (
    Math.min(
      contrastRatio(c, '#ffffff'),
      contrastRatio(c, PAGE_BG),
      contrastRatio(c, brandSoft(primary)),
    ) >= 4.5 && contrastRatio(c, TEXT_COLOR) >= 3
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
  if (linkContrastOk(primary, primary)) return primary
  for (let step = 1; step <= 100; step++) {
    for (const c of [darken(primary, step / 100), lighten(primary, step / 100)]) {
      if (linkContrastOk(c, primary)) return c
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
 * Seitenleiste in Vereinsfarbe (Design „Frisch“, Ralf 14.11.2026: hebt sich von den weißen
 * Karten ab). Nur so weit abgedunkelt wie nötig, dass die Schrift auch auf dem markierten
 * Punkt 4,5 : 1 erreicht (UX-Audit 08.11., W-15); helle Farben wie Gold werden dabei kräftig
 * dunkler, dunkle bleiben fast unverändert.
 */
export function sidebarColor(primary: string): string {
  for (let amount = 0; amount < 1; amount += 0.025) {
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

/** Hell oder dunkel (Dunkelmodus D1, konzepte/dunkelmodus-web.md, X-02). */
export type Scheme = 'light' | 'dark'

/** Seitengrund und Kartenfläche im Dunkelmodus (--color-bg/--color-surface in theme.css). */
export const DARK_BG = '#111614'
export const DARK_SURFACE = '#1a201d'

/**
 * Linkfarbe im Dunkelmodus: ein Ton der Vereinsfarbe, so wenig wie nötig aufgehellt (oder
 * abgedunkelt), bis Text auf Grund und Karte 4,5 : 1 erreicht. 3 : 1 zum hellen Fließtext
 * ist auf dunklem Grund zusammen damit nicht erreichbar; Links bleiben dort wie im Hellen
 * am Fettdruck und in fetter Umgebung am „ ›“ erkennbar (W-16).
 */
export function linkColorDark(primary: string): string {
  const ok = (c: string) =>
    Math.min(
      contrastRatio(c, DARK_BG),
      contrastRatio(c, DARK_SURFACE),
      contrastRatio(c, brandSoft(primary, DARK_SURFACE)),
    ) >= 4.5
  if (ok(primary)) return primary
  for (let step = 1; step <= 100; step++) {
    // Aufhellen ohne Weiß beizumischen: Links bleiben auch bei dunklen Vereinsfarben farbig
    for (const c of [brighten(primary, step / 100), darken(primary, step / 100)]) {
      if (ok(c)) return c
    }
  }
  return '#ffffff'
}

/** Aktionsknöpfe im Dunkelmodus: heben sich vom dunklen Grund ab, Schrift bleibt lesbar. */
export function buttonColorsDark(primary: string, onPrimary: string) {
  const background = contrastRatio(primary, DARK_BG) >= 1.35 ? primary : linkColorDark(primary)
  // Bei mittleren Grautönen reicht dunkelgraue Schrift nicht ganz; dann Schwarz
  const foreground =
    [onPrimary, '#ffffff', '#000000'].find((c) => contrastRatio(background, c) >= 4.5) ?? '#000000'
  const readable = (c: string) =>
    contrastRatio(c, DARK_BG) >= 1.35 && contrastRatio(c, foreground) >= 4.5
  const hover =
    [hoverColor(background, foreground), lighten(background, 0.15), darken(background, 0.15)].find(
      readable,
    ) ?? background
  return { background, foreground, hover }
}

/** Vorgaben der hellen Oberfläche (theme.css) für Text, Flächen und Hintergrund */
export const APP_DEFAULTS: Record<AppRole, string> = {
  text: TEXT_COLOR,
  muted: '#5d6763',
  surface: '#ffffff',
  background: PAGE_BG,
}
const APP_VARS: Record<AppRole, (typeof ROLE_VARS)[number]> = {
  text: '--color-text',
  muted: '--color-text-muted',
  surface: '--color-surface',
  background: '--color-bg',
}
/** Text auf Flächen und Hintergrund: mindestens 4,5 : 1 (WCAG 1.4.3) */
const APP_PAIRS: [AppRole, AppRole][] = [
  ['text', 'surface'],
  ['text', 'background'],
  ['muted', 'surface'],
  ['muted', 'background'],
]

/**
 * Farbrollen in der hellen Oberfläche (Ralf 13.11.2026): welche Vereinsfarben für Fließtext,
 * Sekundärtext, Flächen und Hintergrund gelten. Wäre Text darauf schlechter lesbar als
 * 4,5 : 1, fällt eine Rolle auf die Vorgabe zurück (zuerst Fläche oder Hintergrund, die der
 * Text nicht selbst gewählt hat); `dropped` nennt sie für den Hinweis in den Einstellungen.
 */
export function appColors(
  palette: { color: string }[],
  roles: Partial<Record<AppRole, number>>,
): { colors: Partial<Record<AppRole, string>>; dropped: AppRole[] } {
  const colors: Partial<Record<AppRole, string>> = {}
  for (const role of Object.keys(APP_DEFAULTS) as AppRole[]) {
    const slot = roles[role]
    const color = slot === undefined ? undefined : palette[slot]?.color
    if (color && /^#[0-9a-f]{6}$/i.test(color)) colors[role] = color
  }
  const dropped: AppRole[] = []
  const value = (r: AppRole) => colors[r] ?? APP_DEFAULTS[r]
  for (let guard = 0; guard < 8; guard++) {
    const bad = APP_PAIRS.find(([a, b]) => contrastRatio(value(a), value(b)) < 4.5)
    if (!bad) break
    const [a, b] = bad
    const drop = colors[b] !== undefined ? b : a
    if (colors[drop] === undefined) break
    delete colors[drop]
    dropped.push(drop)
  }
  return { colors, dropped }
}

/** CSS-Variablen, die ein Erscheinungsbild setzt (Namen wie in theme.css). */
export function themeVars(theme: ThemeColors, scheme: Scheme = 'light'): ThemeVars {
  const dark = scheme === 'dark'
  const button = (dark ? buttonColorsDark : buttonColors)(theme.primary, theme.on_primary)
  const link = (dark ? linkColorDark : linkColor)(theme.primary)
  const sidebar = sidebarColor(theme.primary)
  // Farbrollen nur im hellen Modus; im dunklen bleiben Grund, Flächen und Text aus theme.css
  const roles: Partial<Record<(typeof ROLE_VARS)[number], string>> = {}
  if (!dark && theme.palette_roles_in_app && theme.palette && theme.palette_roles) {
    const { colors } = appColors(theme.palette, theme.palette_roles)
    for (const [role, color] of Object.entries(colors)) roles[APP_VARS[role as AppRole]] = color
    // #539: Felder bleiben weiß (theme.css), außer Text wäre darauf schlechter lesbar als 4,5 : 1
    // (heller Text auf dunkler Fläche); dann wie bisher in der Fläche
    const text = colors.text ?? APP_DEFAULTS.text
    if (colors.surface && contrastRatio(text, '#ffffff') < 4.5)
      roles['--color-input-bg'] = colors.surface
  }
  return {
    ...roles,
    '--color-primary': theme.primary,
    '--button-brand-primary': button.background,
    '--button-brand-primary-hover': button.hover,
    '--button-brand-on-primary': button.foreground,
    '--color-primary-hover': hoverColor(theme.primary, theme.on_primary),
    '--color-link': link,
    // Fokusrahmen, Feldfokus und Häkchen: dieselbe abgedunkelte Farbe, damit sie auch bei
    // hellen Vereinsfarben (Gold, Gelb, Hellblau) deutlich zu sehen sind (WCAG 1.4.11)
    '--color-focus': link,
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
  lastTheme = { theme, root }
  if (!theme) {
    for (const v of VARS) root.style.removeProperty(v)
    return
  }
  const vars: Partial<Record<(typeof VARS)[number], string>> = themeVars(theme, scheme)
  for (const name of VARS) {
    const value = vars[name]
    if (value) root.style.setProperty(name, value)
    else root.style.removeProperty(name)
  }
}

let scheme: Scheme = 'light'
let lastTheme: { theme: ThemeColors | null; root: HTMLElement } | null = null

/**
 * Hell oder dunkel für die Vereinsfarben. Die Farben einer Einheit stehen direkt am
 * Element und gewinnen damit gegen theme.css; deshalb rechnet applyTheme sie für die
 * gewählte Darstellung und wird bei einem Wechsel neu angewandt.
 */
export function setThemeScheme(next: Scheme) {
  if (next === scheme) return
  scheme = next
  if (lastTheme) applyTheme(lastTheme.theme, lastTheme.root)
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
  const css = (mode: Scheme) =>
    Object.entries(themeVars(theme, mode))
      .map(([name, value]) => `${name}: ${value};`)
      .join(' ')
  // Dunkel mit eigener Regel, damit sie die dunklen Standardwerte aus theme.css ersetzt
  el.textContent = `:root { ${css('light')} } :root[data-theme='dark'] { ${css('dark')} }`
}
