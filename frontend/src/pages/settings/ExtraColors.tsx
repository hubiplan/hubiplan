import type { ExtraColor, PaletteRole, PaletteRoles } from '../../api/orgs.ts'
import { contrastRatio, readableOn } from '../../theme/contrast.ts'
import { t } from '../../i18n/index.ts'
import { ColorRoles } from './ColorRoles.tsx'

const MAX_EXTRA = 4
/** Weitere Farben der Einheit (zusammen bis sechs); genutzt von den Webseiten-Designs */
export function ExtraColors({
  colors,
  error,
  ownPrimary,
  roles,
  onToggleRole,
  onChange,
}: {
  colors: ExtraColor[]
  error?: string
  ownPrimary: boolean
  roles: PaletteRoles
  onToggleRole: (slot: number, role: PaletteRole, on: boolean) => void
  /** ``map``: neuer Palettenplatz je altem (null = entfernt), für Rollen und Verläufe */
  onChange: (v: ExtraColor[], map?: (slot: number) => number | null) => void
}) {
  const update = (i: number, patch: Partial<ExtraColor>) =>
    onChange(colors.map((c, j) => (j === i ? { ...c, ...patch } : c)))
  const move = (i: number, d: number) => {
    const next = [...colors]
    ;[next[i], next[i + d]] = [next[i + d], next[i]]
    const a = i + 2
    const b = i + d + 2
    onChange(next, (slot) => (slot === a ? b : slot === b ? a : slot))
  }
  const remove = (i: number) => {
    const gone = i + 2
    onChange(
      colors.filter((_, j) => j !== i),
      (slot) => (slot === gone ? null : slot > gone ? slot - 1 : slot),
    )
  }
  return (
    <div className={`field color-group${error ? ' field-invalid' : ''}`}>
      <span>{t('Weitere Farben')}</span>
      <small className="muted">
        {t(
          'Für Einheiten mit drei oder mehr Vereinsfarben. Die Webseiten-Designs nutzen sie für Zierlinien, Farbbänder und Datumsfelder.',
        )}
        {!ownPrimary && t(' Weitere Farben gelten nur zusammen mit einer eigenen Hauptfarbe.')}
      </small>
      <div className="color-list">
        {colors.map((c, i) => {
          const valid = /^#[0-9a-f]{6}$/i.test(c.color)
          const ratio = valid ? contrastRatio(c.color, readableOn(c.color)) : 0
          return (
            <div className="color-row extra-color-row" key={i}>
              <input
                type="color"
                aria-label={t('{x}. Farbe wählen', { x: i + 3 })}
                value={valid ? c.color : '#000000'}
                onChange={(e) => update(i, { color: e.target.value })}
              />
              <input
                aria-label={t('{x}. Farbe als Hex-Wert', { x: i + 3 })}
                value={c.color}
                onChange={(e) => update(i, { color: e.target.value.trim() })}
              />
              <input
                aria-label={t('Name der {x}. Farbe', { x: i + 3 })}
                value={c.name}
                maxLength={30}
                placeholder={t('Name, z. B. Weinrot')}
                onChange={(e) => update(i, { name: e.target.value })}
              />
              <input
                aria-label={t('Verwendung der {x}. Farbe', { x: i + 3 })}
                value={c.use ?? ''}
                maxLength={60}
                placeholder={t('Verwendung, z. B. Fließtext')}
                onChange={(e) => update(i, { use: e.target.value })}
              />
              <span className={`color-contrast small ${valid && ratio >= 4.5 ? 'ok' : 'bad'}`}>
                {valid &&
                  `${ratio >= 4.5 ? '✓' : '✗'} ${t('Text darauf {x} : 1', { x: ratio.toFixed(1) })}`}
              </span>
              <div className="color-row-actions">
                <button
                  type="button"
                  className="button button-ghost"
                  aria-label={t('{x}. Farbe nach oben', { x: i + 3 })}
                  disabled={i === 0}
                  onClick={() => move(i, -1)}
                >
                  ↑
                </button>
                <button
                  type="button"
                  className="button button-ghost"
                  aria-label={t('{x}. Farbe nach unten', { x: i + 3 })}
                  disabled={i === colors.length - 1}
                  onClick={() => move(i, 1)}
                >
                  ↓
                </button>
                <button type="button" className="button button-ghost" onClick={() => remove(i)}>
                  {t('Entfernen')}
                </button>
              </div>
              <ColorRoles
                label={t('{x}. Farbe verwendet für', { x: i + 3 })}
                slot={i + 2}
                roles={roles}
                onToggle={onToggleRole}
              />
            </div>
          )
        })}
      </div>
      {colors.length < MAX_EXTRA && (
        <div>
          <button
            type="button"
            className="button button-ghost"
            onClick={() => onChange([...colors, { color: '#8b1e2d', name: '' }])}
          >
            {t('Farbe hinzufügen')}
          </button>
        </div>
      )}
      {error && <small className="field-error">{error}</small>}
    </div>
  )
}
