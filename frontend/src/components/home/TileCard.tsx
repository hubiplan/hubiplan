// Kachel bei Anlass (backend/hometiles): Kennzahlen, Zeilen und Verweis kommen fertig vom
// Server, damit Browser, Android und iOS dasselbe zeigen.
import { Link } from 'react-router-dom'
import type { ReactNode } from 'react'
import type { HomeTile, HomeTilesData } from '../../api/homeTiles.ts'
import { t } from '../../i18n/index.ts'
import { TileIcon } from '../icons.tsx'
import type { HomeBlock } from './homeLayout.ts'
import '../../pages/todos.css'
import './tiles.css'

const tone = (value: string | null) => (value ? ` tile-tone-${value}` : '')

/** Verweise im Programm als Link, sonst (sollte nicht vorkommen) als Text */
function To({ to, children }: { to: string | null; children: ReactNode }) {
  return to && to.startsWith('/') ? <Link to={to}>{children}</Link> : <>{children}</>
}

export function TileCard({ tile }: { tile: HomeTile }) {
  const c = tile.content
  return (
    <div className="card tile home-auto-tile" data-tile={tile.key}>
      <div className="task-overview-head">
        <h2>
          <TileIcon name={tile.urgent ? 'bell' : 'inbox'} />
          {tile.title}
        </h2>
      </div>
      {!c && <p className="muted small">{tile.description}</p>}
      {c?.reason && <p className="tile-reason">{c.reason}</p>}
      {c && c.figures.length > 0 && (
        <dl className="tile-figures">
          {c.figures.map((f) => (
            <div key={f.label} className={'tile-figure' + tone(f.tone)}>
              <dt>{f.label}</dt>
              <dd>{f.value}</dd>
            </div>
          ))}
        </dl>
      )}
      {c && c.rows.length > 0 && (
        <ul className="plain-list tile-rows">
          {c.rows.map((r, i) => (
            <li key={`${r.title}-${i}`} className={tone(r.tone).trim() || undefined}>
              <To to={r.link}>
                <span className="tile-row-title">{r.title}</span>
              </To>
              {r.detail && <span className="muted small">{r.detail}</span>}
            </li>
          ))}
        </ul>
      )}
      {c?.text && <p className="muted small">{c.text}</p>}
      {c?.link && (
        <div className="home-tile-actions">
          <To to={c.link}>{c.link_label || t('Öffnen')}</To>
        </div>
      )}
    </div>
  )
}

/** Blöcke für die Startseite aus der Antwort des Servers; der Schlüssel ist der der Kachel */
export function tileBlocks(data: HomeTilesData | null): HomeBlock[] {
  return (data?.tiles ?? []).map((tile) => ({
    key: tile.key,
    label: tile.title,
    optional: true,
    urgent: tile.urgent,
    render: () => <TileCard tile={tile} />,
  }))
}
