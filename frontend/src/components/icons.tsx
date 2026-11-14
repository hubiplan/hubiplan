// Kleine Strich-Icons und Icon-Knöpfe für Tabellenzeilen (Bearbeiten, Löschen …).
import type { ButtonHTMLAttributes, ReactNode } from 'react'

function Svg({ children }: { children: ReactNode }) {
  return (
    <svg
      viewBox="0 0 24 24"
      width="18"
      height="18"
      aria-hidden="true"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      {children}
    </svg>
  )
}

export const EditIcon = () => (
  <Svg>
    <path d="M15 4l5 5L9 20H4v-5Z" />
    <path d="M12.5 6.5l5 5" />
  </Svg>
)

export const DeleteIcon = () => (
  <Svg>
    <path d="M4 7h16" />
    <path d="M9 7V4.5h6V7" />
    <path d="M6.5 7l1 13h9l1-13" />
    <path d="M10.5 10.5v6M13.5 10.5v6" />
  </Svg>
)

export const ViewIcon = () => (
  <Svg>
    <path d="M2.5 12C5 7.5 8.3 5.5 12 5.5s7 2 9.5 6.5c-2.5 4.5-5.8 6.5-9.5 6.5S5 16.5 2.5 12Z" />
    <circle cx="12" cy="12" r="2.5" />
  </Svg>
)

export const RestoreIcon = () => (
  <Svg>
    <path d="M5 8.2A8 8 0 1 1 4.1 13.3" />
    <path d="M4 4v4.5h4.5" />
  </Svg>
)

const TILE_ICONS = {
  calendar: 'M4 6.5h16v13.5H4zM4 10.5h16M8.5 4v4M15.5 4v4',
  check: 'M4 5h16v15H4zM8 12l3 3 5-7',
  bell: 'M6 16v-5a6 6 0 0 1 12 0v5l1.5 2h-15zM10 20.5a2 2 0 0 0 4 0',
  bolt: 'M13 3 5 13.5h6L10 21l8-10.5h-6z',
  cake: 'M4 21h16v-7H4zM4 17c2.7 1.6 5.3 1.6 8 0 2.7 1.6 5.3 1.6 8 0M12 14V9.5M12 6.6v.1',
  star: 'm12 3.5 2.6 5.4 5.9.8-4.3 4.1 1 5.9-5.2-2.8-5.2 2.8 1-5.9-4.3-4.1 5.9-.8z',
  inbox: 'M4 13.5 6.5 5h11L20 13.5V19H4zM4 13.5h4.5a3.5 3.5 0 0 0 7 0H20',
} as const

export type TileIconName = keyof typeof TILE_ICONS

/**
 * Symbol im getönten Kästchen für Kartenköpfe und Leerzustände (Design „Frisch“ 3.5).
 * Immer Schmuck: der Text daneben trägt die Bedeutung.
 */
export function TileIcon({ name, round = false }: { name: TileIconName; round?: boolean }) {
  return (
    <span className={`tile-icon${round ? ' tile-icon-round' : ''}`} aria-hidden="true">
      <Svg>
        <path d={TILE_ICONS[name]} />
      </Svg>
    </span>
  )
}

/** Knopf nur mit Icon; `label` ist Tooltip und Name für Screenreader. */
export function IconButton({
  label,
  icon,
  danger = false,
  className,
  ...rest
}: {
  label: string
  icon: ReactNode
  danger?: boolean
} & Omit<ButtonHTMLAttributes<HTMLButtonElement>, 'children'>) {
  return (
    <button
      type="button"
      className={`icon-button${danger ? ' icon-button-danger' : ''}${className ? ` ${className}` : ''}`}
      aria-label={label}
      title={label}
      {...rest}
    >
      {icon}
    </button>
  )
}
