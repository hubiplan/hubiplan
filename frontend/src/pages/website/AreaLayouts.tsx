// Webseite › Gestaltung › Darstellung der Bereiche (Konzept webseite-baukasten G5, Ralf
// 10.11.2026): je fester Bereich zwei bis drei Darstellungen mit Skizze. Die erste ist der
// bisherige Stand; gespeichert werden nur Abweichungen, alles geht in den Entwurf (G2).
import type { ReactNode } from 'react'
import { Link } from 'react-router-dom'
import type { LayoutArea } from '../../api/website.ts'
import { t } from '../../i18n/index.ts'

const box = (x: number, y: number, w: number, h: number, o = 0.25) => (
  <rect key={`${x}-${y}-${w}-${h}`} x={x} y={y} width={w} height={h} rx="1.5" opacity={o} />
)

function grid(cols: number, rows: number, w: number, h: number, gap = 3, top = 4): ReactNode[] {
  const left = (80 - cols * w - (cols - 1) * gap) / 2
  return Array.from({ length: cols * rows }, (_, i) =>
    box(left + (i % cols) * (w + gap), top + Math.floor(i / cols) * (h + gap), w, h),
  )
}

const rows = (n: number, labelW = 22) =>
  Array.from({ length: n }, (_, i) => [
    box(6, 6 + i * 9, labelW, 4, 0.55),
    box(32, 6 + i * 9, 40, 4, 0.3),
  ]).flat()

/** Skizze je Darstellung (nur Flächen, Farbe vom Text) */
const SKETCHES: Record<string, () => ReactNode[]> = {
  'board:cards': () => [
    ...grid(3, 1, 22, 34),
    box(13, 9, 10, 10, 0.5),
    box(35, 9, 10, 10, 0.5),
    box(57, 9, 10, 10, 0.5),
  ],
  'board:list': () => rows(4),
  'events:list': () =>
    [0, 1, 2].map((i) => [box(6, 5 + i * 12, 9, 9, 0.55), box(19, 7 + i * 12, 50, 4, 0.3)]).flat(),
  'events:calendar': () => [...grid(7, 4, 9, 7, 1.5, 6), box(18.5, 14.5, 9, 7, 0.6)],
  'units:large': () => [
    ...grid(2, 2, 34, 15),
    box(9, 7, 9, 9, 0.5),
    box(46, 7, 9, 9, 0.5),
    box(9, 25, 9, 9, 0.5),
    box(46, 25, 9, 9, 0.5),
  ],
  'units:small': () => grid(3, 3, 22, 9),
  'units:list': () =>
    [0, 1, 2, 3]
      .map((i) => [box(8, 6 + i * 9, 3, 3, 0.55), box(14, 6 + i * 9, 38, 3, 0.35)])
      .flat(),
  'gallery:tiles': () => grid(4, 2, 15, 15),
  'gallery:masonry': () => [
    box(6, 4, 15, 20),
    box(6, 27, 15, 13),
    box(24, 4, 15, 12),
    box(24, 19, 15, 21),
    box(42, 4, 15, 24),
    box(42, 31, 15, 9),
    box(60, 4, 15, 14),
    box(60, 21, 15, 19),
  ],
}

function Sketch({ id }: { id: string }) {
  const shapes = SKETCHES[id]
  if (!shapes) return null
  return (
    <svg viewBox="0 0 80 44" width="80" height="44" aria-hidden="true" fill="currentColor">
      {shapes()}
    </svg>
  )
}

export function AreaLayouts({
  catalog,
  labels,
  blocks,
  value,
  onChange,
}: {
  catalog: LayoutArea[]
  labels: Record<string, string>
  blocks: Record<string, boolean>
  value: Record<string, string>
  onChange: (next: Record<string, string>) => void
}) {
  function choose(area: LayoutArea, key: string) {
    const next = { ...value }
    // Standard (erste Darstellung) wird nicht gespeichert
    if (key === area.variants[0]?.key) delete next[area.area]
    else next[area.area] = key
    onChange(next)
  }

  return (
    <div className="area-layouts">
      <p className="muted small">
        {t('Eine Einleitung über einem Bereich schreibst du unter')}{' '}
        <Link to="../inhalte">{t('Webseite › Texte')}</Link>.
      </p>
      {catalog.map((area) => {
        const current = value[area.area] ?? area.variants[0]?.key
        const label = labels[area.area] ?? area.area
        return (
          <fieldset key={area.area} className="area-layout">
            <legend>{label}</legend>
            {blocks[area.area] === false && (
              <p className="muted small">{t('Der Bereich ist zurzeit ausgeschaltet.')}</p>
            )}
            <div className="area-layout-choices">
              {area.variants.map((variant) => (
                <button
                  key={variant.key}
                  type="button"
                  className="home-kind"
                  aria-pressed={current === variant.key}
                  onClick={() => choose(area, variant.key)}
                >
                  <Sketch id={`${area.area}:${variant.key}`} />
                  <span>{variant.label}</span>
                </button>
              ))}
            </div>
          </fieldset>
        )
      })}
    </div>
  )
}
