import { useState } from 'react'
import type { WebsiteImage } from '../../api/website.ts'
import { imageLabel } from './imageTools.ts'
import { t } from '../../i18n/index.ts'
import { ImagePicker } from './ImagePicker.tsx'
import { type Unit } from './imagesHelpers.ts'
import { ImageEditDialog } from './ImageEditDialog.tsx'

/** Ein Bild am Text: Vorschau mit Ändern, Bearbeiten und Entfernen statt einer Liste. */
export function ImageChoice({
  label,
  value,
  images,
  unit,
  units,
  onChange,
  onImagesChanged,
}: {
  label: string
  value: number | null
  images: WebsiteImage[]
  unit?: Unit | null
  units: Unit[]
  onChange: (id: number | null) => void
  onImagesChanged: () => void
}) {
  const [picking, setPicking] = useState(false)
  const [editing, setEditing] = useState(false)
  const image = images.find((i) => i.id === value) ?? null
  return (
    <fieldset className="image-choice">
      <legend>{label}</legend>
      {image ? (
        <div className="image-choice-row">
          <img src={image.small_url} alt="" />
          <span>{imageLabel(image)}</span>
          <span className="button-row">
            <button type="button" className="button button-ghost" onClick={() => setPicking(true)}>
              {t('Ändern')}
            </button>
            <button type="button" className="button button-ghost" onClick={() => setEditing(true)}>
              {t('Bearbeiten')}
            </button>
            <button type="button" className="button button-ghost" onClick={() => onChange(null)}>
              {t('Entfernen')}
            </button>
          </span>
        </div>
      ) : (
        <div className="button-row">
          <button type="button" className="button button-ghost" onClick={() => setPicking(true)}>
            {t('Bild wählen')}
          </button>
        </div>
      )}
      {picking && (
        <ImagePicker
          images={images}
          unit={unit}
          title={label}
          onUploaded={onImagesChanged}
          onPick={(picked) => {
            setPicking(false)
            if (picked[0]) onChange(picked[0].id)
          }}
          onCancel={() => setPicking(false)}
        />
      )}
      {editing && image && (
        <ImageEditDialog
          id={image.id}
          units={units}
          onChanged={onImagesChanged}
          onClose={() => setEditing(false)}
        />
      )}
    </fieldset>
  )
}
