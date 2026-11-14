// Webseite › Feinabstimmung (Ralf 10.11.2026, Konzept webseite-baukasten G1; neu gegliedert
// 14.11.2026): feste Stufen statt CSS. Neun aufklappbare Gruppen, jeder Regler eine Leiste mit
// 2 bis 4 gleich breiten Feldern (mit Bildzeichen, wo es hilft) oder ein Schalter.
// Nicht verstellt = wie das Design; die Stufe des Designs ist markiert. Oben: Voreinstellungen,
// Suche und die verstellten Regler als Chips; ↺ stellt einen Regler oder eine Gruppe zurück.
// Stufen, Sperren, Vorgaben und Voreinstellungen kommen aus HUBIplan (website/style.py),
// die Namen stehen hier.
import { useMemo, useState } from 'react'
import type { HomeSection, StyleCatalog, StyleValues } from '../../api/website.ts'
import { confirmDialog } from '../../components/dialog.ts'
import { t } from '../../i18n/index.ts'
import { styleIcon } from './StyleIcons.tsx'

type Row = {
  key: string
  label: string
  options?: Record<string, string>
  hint?: string
}
type Group = { id: string; title: string; rows: Row[] }

function GROUPS(): Group[] {
  return [
    {
      id: 'font',
      title: t('Schrift'),
      rows: [
        {
          key: 'font',
          label: t('Schriftart'),
          options: { system: t('System'), modern: t('Modern'), festive: t('Festlich') },
        },
        {
          key: 'heading_font',
          label: t('Schrift der Überschriften'),
          options: { text: t('wie der Text'), modern: t('Modern'), festive: t('Festlich') },
        },
        {
          key: 'headings',
          label: t('Überschriften'),
          options: { plain: t('schlicht'), line: t('mit Linie'), color: t('in Farbe') },
        },
        {
          key: 'heading_align',
          label: t('Ausrichtung der Überschriften'),
          options: { left: t('links'), center: t('mittig') },
        },
        {
          key: 'leading',
          label: t('Zeilenabstand'),
          options: { tight: t('eng'), normal: t('normal'), airy: t('luftig') },
        },
        { key: 'script_greeting', label: t('Schmuckschrift für die Begrüßung') },
      ],
    },
    {
      id: 'reading',
      title: t('Lesbarkeit'),
      rows: [
        {
          key: 'size',
          label: t('Schriftgröße'),
          options: { normal: t('normal'), large: t('größer'), xlarge: t('sehr groß') },
        },
        {
          key: 'contrast',
          label: t('Kontrast erhöht'),
          hint: t('Dunklere Schrift und kräftigere Linien, leichter zu lesen.'),
        },
        {
          key: 'dark',
          label: t('Dunkle Darstellung'),
          options: { off: t('aus'), auto: t('nach Gerät') },
          hint: t(
            'Nach Gerät: Wer sein Handy oder seinen Rechner dunkel eingestellt hat, sieht die Webseite dunkel. Kopf, Menü und Fuß behalten ihre Vereinsfarben.',
          ),
        },
        {
          key: 'stripes',
          label: t('Tabellen gestreift'),
          hint: t('Jede zweite Zeile hinterlegt, z. B. bei Ergebnissen und Ämtern.'),
        },
        { key: 'to_top', label: t('Knopf „Nach oben“ auf langen Seiten') },
        {
          key: 'motion',
          label: t('Beim Blättern einblenden'),
          options: { off: t('aus'), subtle: t('dezent') },
          hint: t('Wer am Gerät „weniger Bewegung“ eingestellt hat, sieht es nie.'),
        },
      ],
    },
    {
      id: 'page',
      title: t('Seite'),
      rows: [
        {
          key: 'width',
          label: t('Breite'),
          options: { narrow: t('schmal'), normal: t('normal'), wide: t('breit') },
          hint: t('Schmal zeigt die Seite als Kasten auf dem Hintergrund.'),
        },
        {
          key: 'background',
          label: t('Hintergrund'),
          options: { light: t('hell'), tinted: t('getönt'), grey: t('grau') },
        },
        {
          key: 'spacing',
          label: t('Abstände'),
          options: { compact: t('kompakt'), normal: t('normal'), generous: t('großzügig') },
        },
        {
          key: 'corners',
          label: t('Ecken'),
          options: { square: t('eckig'), slight: t('leicht'), round: t('rund') },
        },
      ],
    },
    {
      id: 'cards',
      title: t('Karten, Bilder, Knöpfe'),
      rows: [
        {
          key: 'cards',
          label: t('Karten'),
          options: { border: t('Rahmen'), shadow: t('Schatten'), flat: t('flach') },
        },
        {
          key: 'images',
          label: t('Bilder'),
          options: { cards: t('wie Karten'), square: t('eckig') },
        },
        {
          key: 'tile_ratio',
          label: t('Bildformat in Kacheln'),
          options: { wide: '3:2', classic: '4:3', square: t('quadratisch') },
        },
        { key: 'image_frame', label: t('Rahmen um Bilder') },
        {
          key: 'buttons',
          label: t('Knöpfe'),
          options: { filled: t('gefüllt'), outline: t('umrandet') },
        },
      ],
    },
    {
      id: 'header',
      title: t('Kopf'),
      rows: [
        {
          key: 'header_bg',
          label: t('Hintergrund des Kopfes'),
          options: { white: t('weiß'), color: t('farbig'), image: t('Kopfbild') },
        },
        { key: 'logo', label: t('Wappen zeigen') },
        {
          key: 'logo_pos',
          label: t('Lage des Wappens'),
          options: { left: t('links'), center: t('mittig'), right: t('rechts') },
        },
        { key: 'name', label: t('Vereinsnamen zeigen') },
        {
          key: 'header_height',
          label: t('Kopfhöhe'),
          options: { low: t('niedrig'), medium: t('mittel'), normal: t('normal'), high: t('hoch') },
        },
        {
          key: 'line',
          label: t('Zierlinie'),
          options: { none: t('keine'), thin: t('dünn'), strong: t('kräftig') },
        },
        { key: 'sticky', label: t('Kopf und Menü oben anheften') },
      ],
    },
    {
      id: 'nav',
      title: t('Menü'),
      rows: [
        {
          key: 'nav',
          label: t('Menü'),
          options: { bar: t('Leiste'), buttons: t('Knöpfe'), text: t('Text') },
        },
        {
          key: 'nav_active',
          label: t('Aktiver Menüpunkt'),
          options: { underline: t('Linie'), filled: t('hinterlegt') },
        },
        {
          key: 'nav_case',
          label: t('Schreibweise'),
          options: { normal: t('normal'), upper: t('GROSS') },
        },
        {
          key: 'nav_size',
          label: t('Schriftgröße im Menü'),
          options: { normal: t('normal'), large: t('größer') },
        },
        {
          key: 'nav_mobile',
          label: t('Menü auf dem Handy'),
          options: { toggle: t('aufklappbar'), scroll: t('Leiste zum Wischen') },
        },
        {
          key: 'nav_start',
          label: t('„Start“ im Menü'),
          hint: t(
            'Aus: Am Bildschirm führen Wappen, Name oder Kopfbild zur Startseite. Im Handymenü bleibt „Start“.',
          ),
        },
        {
          key: 'search',
          label: t('Suche'),
          options: { nav: t('im Menü'), header: t('oben rechts'), footer: t('im Fuß') },
        },
      ],
    },
    {
      id: 'home',
      title: t('Startseite'),
      rows: [
        {
          key: 'hero',
          label: t('Titelbild'),
          options: { low: t('niedrig'), medium: t('mittel'), normal: t('normal'), high: t('hoch') },
        },
        {
          key: 'hero_shade',
          label: t('Titelbild abdunkeln'),
          options: { none: t('nein'), light: t('leicht'), strong: t('kräftig') },
          hint: t(
            'Eine halb durchsichtige Farbe über dem Bild macht Schrift darauf besser lesbar.',
          ),
        },
        {
          key: 'hero_tint',
          label: t('Farbe darüber'),
          options: { dark: t('schwarz'), primary: t('Vereinsfarbe'), accent: t('Zweitfarbe') },
        },
        {
          key: 'hero_focus',
          label: t('Bildausschnitt'),
          options: { top: t('oben'), center: t('Mitte'), bottom: t('unten') },
          hint: t('Welcher Teil sichtbar bleibt, wenn das Bild beschnitten wird.'),
        },
        { key: 'hero_name', label: t('Name auf dem Titelbild') },
        {
          key: 'hero_text',
          label: t('Lage des Namens'),
          options: { top: t('oben'), center: t('mittig'), band: t('unten als Band') },
        },
        {
          key: 'carousel',
          label: t('Bilderkarussell blättert'),
          options: { off: t('nur von Hand'), slow: t('langsam'), normal: t('normal') },
          hint: t('Langsam: doppelt so lange je Bild wie beim Karussell eingestellt.'),
        },
        {
          key: 'sections',
          label: t('Abschnitte trennen'),
          options: { none: t('nicht'), line: t('mit Linie'), alternate: t('abwechselnd getönt') },
        },
      ],
    },
    {
      id: 'pages',
      title: t('Unterseiten und Termine'),
      rows: [
        {
          key: 'page_title',
          label: t('Überschrift der Unterseiten'),
          options: { plain: t('schlicht'), band: t('farbiges Band'), image: t('mit Titelbild') },
          hint: t('Mit Titelbild: das Bild der Startseite hinter der Überschrift.'),
        },
        {
          key: 'date',
          label: t('Datumsfeld'),
          options: { tile: t('Kachel'), strip: t('Streifen') },
        },
        {
          key: 'date_text',
          label: t('Datum daneben'),
          options: {
            weekday: t('Wochentag'),
            short: t('Sa., 14.11.'),
            long: t('Samstag, 14. November'),
          },
        },
      ],
    },
    {
      id: 'footer',
      title: t('Fuß'),
      rows: [
        {
          key: 'footer',
          label: t('Farbe'),
          options: { dark: t('dunkel'), light: t('hell'), color: t('farbig') },
        },
        {
          key: 'footer_align',
          label: t('Ausrichtung'),
          options: { left: t('links'), center: t('mittig'), right: t('rechts') },
        },
      ],
    },
  ]
}

/** Namen der Voreinstellungen (Inhalt aus HUBIplan, style.PRESETS) */
const PRESET_LABELS: () => Record<string, { label: string; hint: string }> = () => ({
  calm: { label: t('Ruhig'), hint: t('Schlicht, viel Weißraum, wenig Farbe') },
  festive: { label: t('Festlich'), hint: t('Serifen, Schmuckschrift, Titelbild in Vereinsfarbe') },
  modern: { label: t('Modern'), hint: t('Runde Ecken, Schatten, Menü als Knöpfe') },
  readable: {
    label: t('Gut lesbar'),
    hint: t('Große Schrift, hoher Kontrast, gestreifte Tabellen'),
  },
})

// Schalter ohne eigene Wahl und ohne Vorgabe aus HUBIplan (ältere Server)
const SWITCH_DEFAULTS: Record<string, boolean> = {
  script_greeting: false,
  image_frame: false,
  logo: true,
  name: true,
  sticky: false,
  hero_name: false,
  contrast: false,
  to_top: false,
  nav_start: true,
  stripes: false,
}
const SWITCH_BY_DESIGN: Record<string, Record<string, boolean>> = {
  stage: { sticky: true, hero_name: true },
  sidebar: { sticky: true },
}

/** Stelle der Webseite, die die Vorschau nach einer Änderung zeigt (Punkt 5) */
export type PreviewFocus = {
  target?: 'kopf' | 'fuss' | 'inhalt' | 'unterseite' | 'termine'
  device?: 'phone'
}

export function previewFocus(key: string, eventsOn: boolean): PreviewFocus {
  if (key === 'nav_mobile') return { target: 'kopf', device: 'phone' }
  if (key === 'page_title') return { target: 'unterseite' }
  if (key === 'date' || key === 'date_text') return eventsOn ? { target: 'termine' } : {}
  if (key === 'footer' || key === 'footer_align') return { target: 'fuss' }
  if (key === 'search') return { target: 'kopf' }
  const group = GROUPS().find((g) => g.rows.some((r) => r.key === key))
  if (group?.id === 'header' || group?.id === 'nav') return { target: 'kopf' }
  if (group?.id === 'cards' || key === 'headings' || key === 'heading_align')
    return { target: 'inhalt' }
  return {}
}

export function StyleTuning({
  catalog,
  design,
  designLabel,
  value,
  onChange,
  headerImage,
  homeSections,
  blocks,
  onFocus,
}: {
  catalog: StyleCatalog
  design: string
  designLabel: string
  value: StyleValues
  onChange: (next: StyleValues) => void
  /** Bildauswahl für „Hintergrund des Kopfes: Kopfbild“ */
  headerImage: React.ReactNode
  /** Abschnitte der Startseite (Titelbild vorhanden?); fehlt bei älteren Ständen */
  homeSections?: HomeSection[]
  /** Eingeschaltete Bausteine (Suche, Termine) */
  blocks?: Record<string, boolean>
  /** Nach einer Änderung: welche Stelle die Vorschau zeigen soll */
  onFocus?: (focus: PreviewFocus) => void
}) {
  const groups = useMemo(() => GROUPS(), [])
  const presets = PRESET_LABELS()
  const locks = catalog.locks[design] ?? {}
  const defaults = catalog.defaults?.[design] ?? {}
  const changed = Object.keys(value).length
  const [query, setQuery] = useState('')
  const [open, setOpen] = useState<Record<string, boolean>>({ [groups[0].id]: true })

  const rowByKey = useMemo(
    () =>
      Object.fromEntries(groups.flatMap((g) => g.rows.map((r) => [r.key, { row: r, group: g }]))),
    [groups],
  )

  function switchValue(style: StyleValues, key: string): boolean {
    const own = style[key]
    if (typeof own === 'boolean') return own
    const given = defaults[key]
    if (typeof given === 'boolean') return given
    return SWITCH_BY_DESIGN[design]?.[key] ?? SWITCH_DEFAULTS[key] ?? false
  }
  /** Wirksame Stufe: eigene Wahl, sonst Vorgabe des Designs */
  const effective = (key: string) => value[key] ?? defaults[key]

  const locked = (key: string, option?: string) => {
    if (!(key in locks)) return false
    const values = locks[key]
    return values === null || (option !== undefined && values.includes(option))
  }
  const lockedHint = t('Legt das Design „{design}“ selbst fest.', { design: designLabel })

  // Punkt 4: nur zeigen, was zutrifft
  const hasHero =
    design === 'stage' ||
    homeSections === undefined ||
    homeSections.some((s) => s.key === 'carousel' && s.on)
  const eventsOn = blocks?.events !== false
  function applies(key: string): boolean {
    switch (key) {
      case 'logo_pos':
        return switchValue(value, 'logo')
      case 'hero':
      case 'hero_shade':
      case 'hero_focus':
      case 'hero_name':
        return hasHero
      case 'hero_tint':
        return hasHero && (effective('hero_shade') ?? 'none') !== 'none'
      case 'hero_text':
        return hasHero && (design === 'stage' || switchValue(value, 'hero_name'))
      case 'search':
        return blocks === undefined || blocks.search !== false
      case 'date':
      case 'date_text':
        return eventsOn
      default:
        return true
    }
  }

  function setKey(key: string, next: string | boolean | null) {
    const result = { ...value }
    if (next === null) delete result[key]
    else result[key] = next
    // Wappen und Vereinsname nie beide aus: der andere Schalter geht wieder an
    if (next === false && key === 'logo' && switchValue(result, 'name') === false)
      result.name = true
    if (next === false && key === 'name' && switchValue(result, 'logo') === false)
      result.logo = true
    onChange(result)
    onFocus?.(previewFocus(key, eventsOn))
  }

  function resetGroup(group: Group) {
    const result = { ...value }
    for (const row of group.rows) delete result[row.key]
    onChange(result)
  }

  function applyPreset(name: string) {
    const preset = catalog.presets?.[name] ?? {}
    const result: StyleValues = { ...value }
    for (const [key, v] of Object.entries(preset)) {
      if (!(key in catalog.options)) continue
      if (typeof v === 'string' && locked(key, v)) continue
      if (locked(key)) continue
      result[key] = v
    }
    if (switchValue(result, 'logo') === false && switchValue(result, 'name') === false)
      result.name = true
    onChange(result)
    onFocus?.({})
  }

  async function reset() {
    const ok = await confirmDialog({
      title: t('Feinabstimmung zurücksetzen?'),
      message: t('Alle Regler zeigen danach wieder, was das Design vorsieht.'),
      confirmLabel: t('Zurücksetzen'),
    })
    if (ok) onChange({})
  }

  /** Text einer Stufe für Chips und Suche */
  function optionLabel(row: Row, option: string | boolean): string {
    if (typeof option === 'boolean') return option ? t('an') : t('aus')
    return row.options?.[option] ?? option
  }

  // Punkt 8: Suche über Namen, Hinweise und Stufen
  const q = query.trim().toLowerCase()
  const matches = (row: Row) =>
    !q ||
    [row.label, row.hint ?? '', ...Object.values(row.options ?? {})].some((s) =>
      s.toLowerCase().includes(q),
    )

  function jumpTo(key: string) {
    const entry = rowByKey[key]
    if (!entry) return
    setQuery('')
    setOpen((o) => ({ ...o, [entry.group.id]: true }))
    window.setTimeout(() => {
      const el = document.getElementById(`style-row-${key}`)
      el?.scrollIntoView?.({ block: 'center' })
      el?.querySelector<HTMLElement>('button, input')?.focus()
    }, 0)
  }

  const shownChips = Object.entries(value).filter(([key]) => key in rowByKey)
  const presetNames = Object.keys(catalog.presets ?? {}).filter((n) => n in presets)
  const visible = groups
    .map((group) => {
      const known = group.rows.filter((r) => catalog.options[r.key])
      const wholeLocked = known.filter((r) => locked(r.key))
      const rows = known.filter((r) => !locked(r.key) && applies(r.key) && matches(r))
      return { group, rows, wholeLocked }
    })
    .filter(({ rows, wholeLocked }) => rows.length > 0 || (!q && wholeLocked.length > 0))

  return (
    <>
      <p className="muted small">
        {t(
          'Feste Stufen für Schrift, Abstände, Kopf, Menü und Fuß. Ohne eigene Wahl zeigt die Webseite, was das Design vorsieht; diese Stufe ist mit einem Punkt markiert. ↺ stellt zurück.',
        )}
      </p>

      {presetNames.length > 0 && (
        <div className="style-presets">
          <span className="style-label" id="style-presets-label">
            {t('Voreinstellungen')}
            <small className="muted">
              {t('Setzt mehrere Regler auf einmal; danach bleibt alles einzeln änderbar.')}
            </small>
          </span>
          <div className="button-row" role="group" aria-labelledby="style-presets-label">
            {presetNames.map((name) => (
              <button
                key={name}
                type="button"
                className="button button-ghost"
                title={presets[name].hint}
                onClick={() => applyPreset(name)}
              >
                {presets[name].label}
              </button>
            ))}
          </div>
        </div>
      )}

      <div className="style-tools">
        <label className="style-search">
          <span className="sr-only">{t('Regler suchen')}</span>
          <input
            type="search"
            placeholder={t('Regler suchen, z. B. Wappen oder Handy')}
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
        </label>
      </div>

      {shownChips.length > 0 && (
        <ul className="style-chips" aria-label={t('Verstellte Regler')}>
          {shownChips.map(([key, v]) => {
            const row = rowByKey[key].row
            return (
              <li key={key} className="style-chip-item">
                <button type="button" className="style-chip" onClick={() => jumpTo(key)}>
                  {row.label}: <strong>{optionLabel(row, v)}</strong>
                </button>
                <button
                  type="button"
                  className="style-chip-x"
                  aria-label={t('{label} zurücksetzen', { label: row.label })}
                  onClick={() => setKey(key, null)}
                >
                  ×
                </button>
              </li>
            )
          })}
        </ul>
      )}

      {visible.map(({ group, rows, wholeLocked }) => {
        const groupChanged = group.rows.some((r) => r.key in value)
        return (
          <details
            key={group.id}
            className="style-group"
            open={q ? true : !!open[group.id]}
            onToggle={(e) => {
              if (q) return
              const isOpen = (e.currentTarget as HTMLDetailsElement).open
              setOpen((o) => (o[group.id] === isOpen ? o : { ...o, [group.id]: isOpen }))
            }}
          >
            <summary>
              {group.title}
              {groupChanged && <span className="style-changed">{t('verstellt')}</span>}
            </summary>
            {groupChanged && (
              <div className="style-group-tools">
                <button
                  type="button"
                  className="button button-ghost"
                  onClick={() => resetGroup(group)}
                >
                  ↺ {t('Gruppe „{group}“ zurücksetzen', { group: group.title })}
                </button>
              </div>
            )}
            {rows.map((row) => {
              const options = catalog.options[row.key]
              const id = `style-${row.key}`
              const own = row.key in value
              return (
                <div key={row.key} id={`style-row-${row.key}`} className="style-row">
                  <span className="style-label" id={id}>
                    {row.label}
                    {row.hint && <small className="muted">{row.hint}</small>}
                  </span>
                  <div className="style-control">
                    {options === 'switch' ? (
                      <label className="style-switch">
                        <input
                          type="checkbox"
                          role="switch"
                          aria-labelledby={id}
                          checked={switchValue(value, row.key)}
                          onChange={(e) => setKey(row.key, e.target.checked)}
                        />
                        <span aria-hidden="true">
                          {switchValue(value, row.key) ? t('an') : t('aus')}
                        </span>
                        {!own && <small className="muted">{t('wie das Design')}</small>}
                      </label>
                    ) : (
                      <div
                        className={`style-segments style-n${options.length}`}
                        role="group"
                        aria-labelledby={id}
                      >
                        {options.map((option) => {
                          const on = value[row.key] === option
                          const off = locked(row.key, option)
                          const isDefault = defaults[row.key] === option
                          const icon = styleIcon(row.key, option)
                          return (
                            <button
                              key={option}
                              type="button"
                              aria-pressed={on}
                              disabled={off}
                              className={[isDefault ? 'is-default' : '', icon ? 'has-icon' : '']
                                .filter(Boolean)
                                .join(' ')}
                              title={
                                off
                                  ? lockedHint
                                  : isDefault
                                    ? t('So zeigt es das Design „{design}“.', {
                                        design: designLabel,
                                      })
                                    : undefined
                              }
                              onClick={() => setKey(row.key, on ? null : option)}
                            >
                              {icon}
                              <span>{row.options?.[option] ?? option}</span>
                              {isDefault && (
                                <span className="style-default-dot" aria-hidden="true" />
                              )}
                            </button>
                          )
                        })}
                      </div>
                    )}
                    {own && (
                      <button
                        type="button"
                        className="style-reset"
                        aria-label={t('{label} zurücksetzen', { label: row.label })}
                        title={t('Zurück auf das Design')}
                        onClick={() => setKey(row.key, null)}
                      >
                        ↺
                      </button>
                    )}
                  </div>
                  {row.key === 'header_bg' &&
                    (value.header_bg === 'image' || value.header_bg === undefined) && (
                      <div className="style-extra">{headerImage}</div>
                    )}
                </div>
              )
            })}
            {!q && wholeLocked.length > 0 && (
              <p className="muted small style-locked">
                {t('Legt das Design „{design}“ selbst fest: {list}.', {
                  design: designLabel,
                  list: wholeLocked.map((r) => r.label).join(', '),
                })}
              </p>
            )}
          </details>
        )
      })}
      {q && visible.length === 0 && <p className="muted">{t('Kein Regler gefunden.')}</p>}

      <div className="button-row">
        <button
          type="button"
          className="button button-ghost"
          disabled={changed === 0}
          onClick={() => void reset()}
        >
          {t('Alles zurücksetzen')}
        </button>
        <span className="muted small">
          {changed === 0 ? t('Alles wie das Design.') : t('{n} Regler verstellt.', { n: changed })}
        </span>
      </div>
    </>
  )
}
