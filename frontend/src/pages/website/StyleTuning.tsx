// Webseite › Gestaltung › Feinabstimmung (Ralf 10.11.2026, Konzept webseite-baukasten G1):
// feste Stufen statt CSS. Sechs aufklappbare Gruppen, jeder Regler eine Leiste mit 2 oder 3
// gleich breiten Feldern oder ein Schalter. Nicht verstellt = wie das Design; ein zweiter Klick
// auf das gewählte Feld stellt zurück. Stufen und Sperren je Design kommen aus HUBIplan
// (website/style.py), die Namen stehen hier.
import type { StyleCatalog, StyleValues } from '../../api/website.ts'
import { confirmDialog } from '../../components/dialog.ts'
import { t } from '../../i18n/index.ts'

type Row = { key: string; label: string; options?: Record<string, string>; hint?: string }

const GROUPS: { title: string; rows: Row[] }[] = [
  {
    title: t('Schrift'),
    rows: [
      {
        key: 'font',
        label: t('Schriftart'),
        options: { system: t('System'), modern: t('Modern'), festive: t('Festlich') },
      },
      { key: 'size', label: t('Größe'), options: { normal: t('normal'), large: t('größer') } },
      {
        key: 'leading',
        label: t('Zeilenabstand'),
        options: { tight: t('eng'), normal: t('normal'), airy: t('luftig') },
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
      { key: 'script_greeting', label: t('Schmuckschrift für die Begrüßung') },
    ],
  },
  {
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
      { key: 'image_frame', label: t('Rahmen um Bilder') },
      {
        key: 'buttons',
        label: t('Knöpfe'),
        options: { filled: t('gefüllt'), outline: t('umrandet') },
      },
      {
        key: 'date',
        label: t('Datumsfeld'),
        options: { tile: t('Kachel'), strip: t('Streifen') },
      },
    ],
  },
  {
    title: t('Kopf und Menü'),
    rows: [
      {
        key: 'header_bg',
        label: t('Hintergrund'),
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
        options: { low: t('niedrig'), normal: t('normal'), high: t('hoch') },
      },
      {
        key: 'line',
        label: t('Zierlinie'),
        options: { none: t('keine'), thin: t('dünn'), strong: t('kräftig') },
      },
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
      { key: 'sticky', label: t('Menü oben anheften') },
    ],
  },
  {
    title: t('Startseite'),
    rows: [
      {
        key: 'hero',
        label: t('Titelbild'),
        options: { low: t('niedrig'), normal: t('normal'), high: t('hoch') },
      },
      { key: 'hero_name', label: t('Name auf dem Titelbild') },
    ],
  },
  {
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

// Schalter ohne eigene Wahl: so, wie das Design es zeigt
const SWITCH_DEFAULTS: Record<string, boolean> = {
  script_greeting: false,
  image_frame: false,
  logo: true,
  name: true,
  sticky: false,
  hero_name: false,
}
const SWITCH_BY_DESIGN: Record<string, Record<string, boolean>> = {
  stage: { sticky: true, hero_name: true },
  sidebar: { sticky: true },
}

function switchValue(style: StyleValues, design: string, key: string): boolean {
  const own = style[key]
  if (typeof own === 'boolean') return own
  return SWITCH_BY_DESIGN[design]?.[key] ?? SWITCH_DEFAULTS[key] ?? false
}

export function StyleTuning({
  catalog,
  design,
  designLabel,
  value,
  onChange,
  headerImage,
}: {
  catalog: StyleCatalog
  design: string
  designLabel: string
  value: StyleValues
  onChange: (next: StyleValues) => void
  /** Bildauswahl für „Hintergrund: Kopfbild“ */
  headerImage: React.ReactNode
}) {
  const locks = catalog.locks[design] ?? {}
  const changed = Object.keys(value).length

  function setKey(key: string, next: string | boolean | null) {
    const result = { ...value }
    if (next === null) delete result[key]
    else result[key] = next
    // Wappen und Vereinsname nie beide aus: der andere Schalter geht wieder an
    if (next === false && key === 'logo' && switchValue(result, design, 'name') === false)
      result.name = true
    if (next === false && key === 'name' && switchValue(result, design, 'logo') === false)
      result.logo = true
    onChange(result)
  }

  async function reset() {
    const ok = await confirmDialog({
      title: t('Feinabstimmung zurücksetzen?'),
      message: t('Alle Regler zeigen danach wieder, was das Design vorsieht.'),
      confirmLabel: t('Zurücksetzen'),
    })
    if (ok) onChange({})
  }

  const locked = (key: string, option?: string) => {
    if (!(key in locks)) return false
    const values = locks[key]
    return values === null || (option !== undefined && values.includes(option))
  }
  const lockedHint = t('Legt das Design „{design}“ selbst fest.', { design: designLabel })
  // Kopfbild: eigene Wahl oder (ohne Wahl) wie bisher, wenn eins gesetzt ist
  const showHeaderImage = value.header_bg === 'image' || value.header_bg === undefined

  return (
    <>
      <p className="muted small">
        {t(
          'Feste Stufen für Schrift, Abstände, Kopf, Menü und Fuß. Nicht gewählt heißt: so, wie das Design es zeigt. Ein zweiter Klick auf das gewählte Feld stellt den Regler zurück.',
        )}
      </p>
      {GROUPS.map((group) => (
        <details key={group.title} className="style-group" open={group.title === GROUPS[0].title}>
          <summary>
            {group.title}
            {group.rows.some((r) => r.key in value) && (
              <span className="style-changed">{t('verstellt')}</span>
            )}
          </summary>
          {group.rows.map((row) => {
            const options = catalog.options[row.key]
            if (!options) return null
            const whole = locked(row.key)
            const id = `style-${row.key}`
            return (
              <div key={row.key} className="style-row">
                <span className="style-label" id={id}>
                  {row.label}
                  {whole && <small className="muted">{lockedHint}</small>}
                  {!whole && row.hint && <small className="muted">{row.hint}</small>}
                </span>
                {options === 'switch' ? (
                  <label className="style-switch">
                    <input
                      type="checkbox"
                      role="switch"
                      aria-labelledby={id}
                      checked={switchValue(value, design, row.key)}
                      disabled={whole}
                      onChange={(e) => setKey(row.key, e.target.checked)}
                    />
                    <span aria-hidden="true">
                      {switchValue(value, design, row.key) ? t('an') : t('aus')}
                    </span>
                  </label>
                ) : (
                  <div
                    className={`style-segments style-n${options.length}`}
                    role="group"
                    aria-labelledby={id}
                  >
                    {options.map((option) => {
                      const on = value[row.key] === option
                      const off = whole || locked(row.key, option)
                      return (
                        <button
                          key={option}
                          type="button"
                          aria-pressed={on}
                          disabled={off}
                          title={off ? lockedHint : undefined}
                          onClick={() => setKey(row.key, on ? null : option)}
                        >
                          {row.options?.[option] ?? option}
                        </button>
                      )
                    })}
                  </div>
                )}
                {row.key === 'header_bg' && showHeaderImage && (
                  <div className="style-extra">{headerImage}</div>
                )}
              </div>
            )
          })}
        </details>
      ))}
      <div className="button-row">
        <button
          type="button"
          className="button button-ghost"
          disabled={changed === 0}
          onClick={() => void reset()}
        >
          {t('Zurücksetzen')}
        </button>
        <span className="muted small">
          {changed === 0 ? t('Alles wie das Design.') : t('{n} Regler verstellt.', { n: changed })}
        </span>
      </div>
    </>
  )
}
