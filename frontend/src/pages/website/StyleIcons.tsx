// Kleine Bildzeichen für die Stufen der Feinabstimmung (Ralf 14.11.2026, Punkt 6): eine
// Skizze über dem Wort, damit man die Wirkung ohne Ausprobieren erkennt. Nur Formen in
// currentColor, keine Texte; das Wort bleibt die Beschriftung des Knopfs.
import type { ReactNode } from 'react'

const W = 32
const H = 20

function svg(children: ReactNode) {
  return (
    <svg
      className="style-icon"
      viewBox={`0 0 ${W} ${H}`}
      width={W}
      height={H}
      aria-hidden="true"
      focusable="false"
    >
      {children}
    </svg>
  )
}

const frame = (rx: number) => (
  <rect
    x="4"
    y="3"
    width="24"
    height="14"
    rx={rx}
    fill="none"
    stroke="currentColor"
    strokeWidth="2"
  />
)
const bar = (x: number, y: number, w: number, h = 2.5, o = 1) => (
  <rect
    key={`${x}-${y}-${w}`}
    x={x}
    y={y}
    width={w}
    height={h}
    rx="1"
    fill="currentColor"
    opacity={o}
  />
)
const lines = (align: 'left' | 'center' | 'right') => {
  const ws = [18, 12, 15]
  return ws.map((w, i) => {
    const x = align === 'left' ? 5 : align === 'right' ? 27 - w : 16 - w / 2
    return bar(x, 4 + i * 5, w)
  })
}

const ICONS: Record<string, Record<string, () => ReactNode>> = {
  corners: {
    square: () => svg(frame(0)),
    slight: () => svg(frame(2.5)),
    round: () => svg(frame(6)),
  },
  cards: {
    border: () => svg(frame(2)),
    shadow: () =>
      svg(
        <>
          <rect x="6" y="5" width="24" height="13" rx="2" fill="currentColor" opacity=".25" />
          <rect
            x="3"
            y="2"
            width="24"
            height="13"
            rx="2"
            style={{ fill: 'var(--color-surface, #fff)' }}
            stroke="currentColor"
            strokeWidth="1"
          />
        </>,
      ),
    flat: () =>
      svg(<rect x="4" y="3" width="24" height="14" rx="2" fill="currentColor" opacity=".3" />),
  },
  nav: {
    bar: () =>
      svg(
        <>
          <rect x="1" y="6" width="30" height="8" rx="1" fill="currentColor" opacity=".85" />
        </>,
      ),
    buttons: () =>
      svg(
        <>
          <rect x="1" y="6" width="9" height="8" rx="4" fill="currentColor" />
          <rect x="11.5" y="6" width="9" height="8" rx="4" fill="none" stroke="currentColor" />
          <rect x="22" y="6" width="9" height="8" rx="4" fill="none" stroke="currentColor" />
        </>,
      ),
    text: () => svg(<>{[bar(2, 9, 8), bar(12, 9, 8), bar(22, 9, 8)]}</>),
  },
  logo_pos: {
    left: () =>
      svg(<>{[<circle key="c" cx="7" cy="10" r="4" fill="currentColor" />, bar(13, 9, 14)]}</>),
    center: () =>
      svg(<>{[<circle key="c" cx="16" cy="7" r="4" fill="currentColor" />, bar(9, 13, 14)]}</>),
    right: () =>
      svg(<>{[<circle key="c" cx="25" cy="10" r="4" fill="currentColor" />, bar(5, 9, 14)]}</>),
  },
  footer_align: {
    left: () => svg(<>{lines('left')}</>),
    center: () => svg(<>{lines('center')}</>),
    right: () => svg(<>{lines('right')}</>),
  },
  heading_align: {
    left: () => svg(<>{lines('left')}</>),
    center: () => svg(<>{lines('center')}</>),
  },
  tile_ratio: {
    wide: () =>
      svg(<rect x="7" y="3" width="18" height="12" rx="1" fill="currentColor" opacity=".7" />),
    classic: () =>
      svg(<rect x="8" y="2" width="16" height="12" rx="1" fill="currentColor" opacity=".7" />),
    square: () =>
      svg(<rect x="9" y="2" width="14" height="14" rx="1" fill="currentColor" opacity=".7" />),
  },
  width: {
    narrow: () =>
      svg(<rect x="10" y="2" width="12" height="16" rx="1" fill="currentColor" opacity=".6" />),
    normal: () =>
      svg(<rect x="6" y="2" width="20" height="16" rx="1" fill="currentColor" opacity=".6" />),
    wide: () =>
      svg(<rect x="2" y="2" width="28" height="16" rx="1" fill="currentColor" opacity=".6" />),
  },
  hero_text: {
    top: () =>
      svg(
        <>
          <rect x="2" y="2" width="28" height="16" rx="1" fill="currentColor" opacity=".3" />
          {bar(5, 4.5, 14)}
        </>,
      ),
    center: () =>
      svg(
        <>
          <rect x="2" y="2" width="28" height="16" rx="1" fill="currentColor" opacity=".3" />
          {bar(9, 9, 14)}
        </>,
      ),
    band: () =>
      svg(
        <>
          <rect x="2" y="2" width="28" height="16" rx="1" fill="currentColor" opacity=".3" />
          <rect x="2" y="13" width="28" height="5" fill="currentColor" opacity=".8" />
        </>,
      ),
  },
  hero_shade: {
    none: () =>
      svg(
        <rect
          x="2"
          y="2"
          width="28"
          height="16"
          rx="1"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.5"
        />,
      ),
    light: () =>
      svg(<rect x="2" y="2" width="28" height="16" rx="1" fill="currentColor" opacity=".3" />),
    strong: () =>
      svg(<rect x="2" y="2" width="28" height="16" rx="1" fill="currentColor" opacity=".65" />),
  },
  hero_focus: {
    top: () =>
      svg(
        <>
          <rect
            x="2"
            y="1"
            width="28"
            height="18"
            rx="1"
            fill="none"
            stroke="currentColor"
            strokeWidth="1"
            opacity=".5"
          />
          <rect x="2" y="1" width="28" height="8" fill="currentColor" opacity=".6" />
        </>,
      ),
    center: () =>
      svg(
        <>
          <rect
            x="2"
            y="1"
            width="28"
            height="18"
            rx="1"
            fill="none"
            stroke="currentColor"
            strokeWidth="1"
            opacity=".5"
          />
          <rect x="2" y="6" width="28" height="8" fill="currentColor" opacity=".6" />
        </>,
      ),
    bottom: () =>
      svg(
        <>
          <rect
            x="2"
            y="1"
            width="28"
            height="18"
            rx="1"
            fill="none"
            stroke="currentColor"
            strokeWidth="1"
            opacity=".5"
          />
          <rect x="2" y="11" width="28" height="8" fill="currentColor" opacity=".6" />
        </>,
      ),
  },
  sections: {
    none: () => svg(<>{[bar(4, 4, 24, 4, 0.5), bar(4, 12, 24, 4, 0.5)]}</>),
    line: () => svg(<>{[bar(4, 3, 24, 4, 0.5), bar(4, 9.5, 24, 1), bar(4, 13, 24, 4, 0.5)]}</>),
    alternate: () =>
      svg(
        <>
          <rect x="2" y="9" width="28" height="9" rx="1" fill="currentColor" opacity=".25" />
          {[bar(4, 3, 24, 4, 0.5), bar(4, 11.5, 24, 4, 0.5)]}
        </>,
      ),
  },
  page_title: {
    plain: () => svg(<>{[bar(4, 5, 18, 4), bar(4, 13, 24, 2, 0.4)]}</>),
    band: () =>
      svg(
        <>
          <rect x="2" y="2" width="28" height="9" rx="1.5" fill="currentColor" opacity=".8" />
          {bar(4, 14, 24, 2, 0.4)}
        </>,
      ),
    image: () =>
      svg(
        <>
          <rect x="2" y="2" width="28" height="9" rx="1.5" fill="currentColor" opacity=".35" />
          <path d="M3 11 9 6l4 3 5-4 11 6Z" fill="currentColor" opacity=".7" />
          {bar(4, 14, 24, 2, 0.4)}
        </>,
      ),
  },
}

/** Bildzeichen für eine Stufe, sonst null (dann nur das Wort). */
export function styleIcon(key: string, option: string): ReactNode {
  return ICONS[key]?.[option]?.() ?? null
}
