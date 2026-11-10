// Einstellungen › Erscheinungsbild › Farbblatt: Palette, Verwendung und Verläufe der Einheit
// auf einen Blick, zum Weitergeben oder Drucken (Ralf 10.11.2026)
import { Link } from 'react-router-dom'
import { gradientCss, orgApi } from '../../api/orgs.ts'
import type { PaletteColor } from '../../api/orgs.ts'
import { LoadError, Loading } from '../../components/ui.tsx'
import { useLoad } from '../../components/forms.ts'
import { useActiveOrg } from '../../org/OrgContext.tsx'
import { t } from '../../i18n/index.ts'

/** RGB-Werte einer Farbe (#rrggbb → „5 72 122“) */
function rgbText(hex: string): string {
  const n = parseInt(hex.slice(1), 16)
  return `${(n >> 16) & 255} ${(n >> 8) & 255} ${n & 255}`
}

function slotLabel(i: number): string {
  return i === 0 ? t('Hauptfarbe') : i === 1 ? t('Zweitfarbe') : t('{x}. Farbe', { x: i + 1 })
}

export function ColorSheetPage() {
  const org = useActiveOrg()
  const { data, error, reload } = useLoad(() => orgApi.theme(org.id), [org.id])
  if (error) return <LoadError message={error} onRetry={() => void reload()} />
  if (!data) return <Loading />
  const eff = data.effective
  const palette: PaletteColor[] = eff.palette ?? [
    { color: eff.primary, on_color: eff.on_primary, name: '' },
    { color: eff.accent, on_color: eff.on_accent, name: '' },
  ]
  const gradients = eff.gradients ?? []
  return (
    <div className="stack color-sheet">
      <p className="muted small no-print">
        <Link to="/einstellungen/erscheinungsbild">{t('Zurück zum Erscheinungsbild')}</Link>
        {' · '}
        <button type="button" className="button button-ghost" onClick={() => window.print()}>
          {t('Drucken')}
        </button>
      </p>
      <section className="card card-wide">
        <h2>{t('Farben von {name}', { name: org.name })}</h2>
        {eff.inherited_from.colors && !data.primary_color && (
          <p className="muted small">
            {t('Übernommen von „{x0}“.', { x0: eff.inherited_from.colors })}
          </p>
        )}
        <div className="color-sheet-grid">
          {palette.map((c, i) => (
            <figure key={i} className="color-sheet-card">
              <div className="color-sheet-swatch" style={{ background: c.color }} />
              <figcaption>
                <strong>{c.name || slotLabel(i)}</strong>
                <span className="color-sheet-code">
                  {c.color.toUpperCase()} · {t('RGB {x}', { x: rgbText(c.color) })}
                </span>
                {c.name && <span className="muted small">{slotLabel(i)}</span>}
                {c.use && <span>{c.use}</span>}
              </figcaption>
            </figure>
          ))}
        </div>
        {gradients.length > 0 && (
          <>
            <h3>{t('Verläufe')}</h3>
            <div className="color-sheet-grid color-sheet-grid-wide">
              {gradients.map((g, i) => (
                <figure key={i} className="color-sheet-card">
                  <div
                    className="color-sheet-swatch"
                    style={{ background: gradientCss(g.colors[0], g.colors[1], g.direction) }}
                  />
                  <figcaption>
                    <strong>{g.name || t('Verlauf {x}', { x: i + 1 })}</strong>
                    <span className="color-sheet-code">
                      {g.colors[0].toUpperCase()} → {g.colors[1].toUpperCase()}
                    </span>
                    <span className="muted small">
                      {g.direction === 'down'
                        ? t('von oben nach unten')
                        : t('von links nach rechts')}
                    </span>
                  </figcaption>
                </figure>
              ))}
            </div>
          </>
        )}
      </section>
    </div>
  )
}
