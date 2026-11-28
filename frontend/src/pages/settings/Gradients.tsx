import { gradientCss } from '../../api/orgs.ts'
import type { GradientSetting } from '../../api/orgs.ts'
import { Field, SelectField } from '../../components/ui.tsx'
import { contrastRatio, readableOnPair } from '../../theme/contrast.ts'
import { t } from '../../i18n/index.ts'

const MAX_GRADIENTS = 2

/** Bis zu zwei benannte Verläufe aus der Palette (Webseite: Kopf, Fuß, Bänder, Zierlinien) */
export function Gradients({
  gradients,
  palette,
  error,
  ownPrimary,
  onChange,
}: {
  gradients: GradientSetting[]
  palette: { color: string; name: string }[]
  error?: string
  ownPrimary: boolean
  onChange: (v: GradientSetting[]) => void
}) {
  const update = (i: number, patch: Partial<GradientSetting>) =>
    onChange(gradients.map((g, j) => (j === i ? { ...g, ...patch } : g)))
  const valid = (c?: string) => Boolean(c && /^#[0-9a-f]{6}$/i.test(c))
  const slotName = (i: number) => {
    const p = palette[i]
    const role =
      i === 0 ? t('Hauptfarbe') : i === 1 ? t('Zweitfarbe') : t('{x}. Farbe', { x: i + 1 })
    return p?.name ? `${role} (${p.name})` : role
  }
  return (
    <div className={`field color-group${error ? ' field-invalid' : ''}`}>
      <span>{t('Verläufe')}</span>
      <small className="muted">
        {t(
          'Für Kopf, Fuß, Farbbänder und Zierlinien der Webseite, z. B. von Blau nach Dunkelblau. Welche Stelle einen Verlauf bekommt, stellst du unter Webseite › Gestaltung ein.',
        )}
        {!ownPrimary && t(' Verläufe gelten nur zusammen mit einer eigenen Hauptfarbe.')}
      </small>
      <div className="color-list">
        {gradients.map((g, i) => {
          const a = palette[g.from]?.color
          const b = palette[g.to]?.color
          const ok = valid(a) && valid(b)
          const on = ok ? readableOnPair(a as string, b as string) : '#000000'
          const ratio = ok
            ? Math.min(contrastRatio(a as string, on), contrastRatio(b as string, on))
            : 0
          return (
            <div className="gradient-row" key={i}>
              <div className="gradient-row-head">
                <span
                  className="gradient-swatch"
                  aria-hidden="true"
                  style={
                    ok ? { background: gradientCss(a!, b!, g.direction), color: on } : undefined
                  }
                >
                  {g.name || t('Verlauf {x}', { x: i + 1 })}
                </span>
                <span className={`color-contrast small ${ok && ratio >= 4.5 ? 'ok' : 'bad'}`}>
                  {ok &&
                    `${ratio >= 4.5 ? '✓' : '✗'} ${t('Text darauf {x} : 1', { x: ratio.toFixed(1) })}`}
                </span>
                <button
                  type="button"
                  className="button button-ghost"
                  onClick={() => onChange(gradients.filter((_, j) => j !== i))}
                >
                  {t('Entfernen')}
                </button>
              </div>
              <div className="gradient-row-fields">
                <Field
                  label={t('Name')}
                  value={g.name}
                  maxLength={30}
                  placeholder={t('z. B. Blauverlauf')}
                  onChange={(e) => update(i, { name: e.target.value })}
                />
                <SelectField
                  label={t('von')}
                  value={String(g.from)}
                  onChange={(e) => update(i, { from: Number(e.target.value) })}
                >
                  {palette.map((_, j) => (
                    <option key={j} value={String(j)}>
                      {slotName(j)}
                    </option>
                  ))}
                </SelectField>
                <SelectField
                  label={t('nach')}
                  value={String(g.to)}
                  onChange={(e) => update(i, { to: Number(e.target.value) })}
                >
                  {palette.map((_, j) => (
                    <option key={j} value={String(j)}>
                      {slotName(j)}
                    </option>
                  ))}
                </SelectField>
                <SelectField
                  label={t('Richtung')}
                  value={g.direction}
                  onChange={(e) =>
                    update(i, { direction: e.target.value === 'down' ? 'down' : 'right' })
                  }
                >
                  <option value="right">{t('von links nach rechts')}</option>
                  <option value="down">{t('von oben nach unten')}</option>
                </SelectField>
              </div>
            </div>
          )
        })}
      </div>
      {gradients.length < MAX_GRADIENTS && palette.length >= 2 && (
        <div>
          <button
            type="button"
            className="button button-ghost"
            onClick={() =>
              onChange([...gradients, { name: '', from: 0, to: 1, direction: 'right' }])
            }
          >
            {t('Verlauf hinzufügen')}
          </button>
        </div>
      )}
      {error && <small className="field-error">{error}</small>}
    </div>
  )
}
