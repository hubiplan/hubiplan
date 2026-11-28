import type { ReactNode } from 'react'
import type { WebsiteImage } from '../../api/website.ts'
import { imageLabel, needsAlt } from './imageTools.ts'
import { t } from '../../i18n/index.ts'

/** Kachelraster; mit ``selected`` zum Ankreuzen, sonst zum Öffnen */
export function ImageTiles({
  images,
  selected,
  onClick,
  before,
}: {
  images: WebsiteImage[]
  selected?: number[]
  onClick: (image: WebsiteImage) => void
  before?: ReactNode
}) {
  return (
    <ul className="image-tiles">
      {before}
      {images.map((i) => {
        const index = selected?.indexOf(i.id) ?? -1
        return (
          <li key={i.id}>
            <button
              type="button"
              className="image-tile"
              aria-pressed={selected ? index >= 0 : undefined}
              onClick={() => onClick(i)}
            >
              <img src={i.small_url} alt="" loading="lazy" />
              {index >= 0 && <span className="image-tile-mark">{index + 1}</span>}
              <span className="image-tile-label">{imageLabel(i)}</span>
              <span className="image-tile-tags">
                {i.department_name && <small className="tag">{i.department_name}</small>}
                {i.used === false && (
                  <small className="tag tag-muted">{t('nicht verwendet')}</small>
                )}
                {needsAlt(i) && <small className="tag tag-warn">{t('ohne Beschreibung')}</small>}
              </span>
            </button>
          </li>
        )
      })}
    </ul>
  )
}

// --- Übersicht ---
