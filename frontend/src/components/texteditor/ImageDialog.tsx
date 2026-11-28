import { useState } from 'react'
import 'prosemirror-view/style/prosemirror.css'
import type { WebsiteImage } from '../../api/website.ts'
import { Modal } from '../Modal.tsx'
import { useImageCrop } from '../ImageCrop.tsx'
import { RightsHint } from '../RightsHint.tsx'
import { Alert, Field } from '../ui.tsx'
import { errorMessage } from '../forms.ts'
import { t } from '../../i18n/index.ts'
import { imageLabel } from './textEditorHelpers.ts'

export function ImageDialog({
  images,
  onUpload,
  onCancel,
  onPick,
}: {
  images: WebsiteImage[]
  onUpload?: (file: File, alt: string) => Promise<WebsiteImage>
  onCancel: () => void
  onPick: (image: WebsiteImage) => void
}) {
  const [file, setFile] = useState<File | null>(null)
  const crop = useImageCrop()
  const [alt, setAlt] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function upload() {
    if (!file || !onUpload) return
    setBusy(true)
    setError(null)
    try {
      onPick(await onUpload(file, alt.trim()))
    } catch (err) {
      setError(errorMessage(err))
      setBusy(false)
    }
  }

  return (
    <Modal title={t('Bild einfügen')} onClose={onCancel}>
      {images.length === 0 ? (
        <p className="muted">{t('Noch keine Bilder hochgeladen.')}</p>
      ) : (
        <ul className="texteditor-images">
          {images.map((i) => (
            <li key={i.id}>
              <button type="button" onClick={() => onPick(i)}>
                <img src={i.small_url} alt="" width={120} />
                <span>{imageLabel(i)}</span>
                {!i.alt_text && !i.decorative && (
                  <small className="field-error">{t('ohne Beschreibung')}</small>
                )}
              </button>
            </li>
          ))}
        </ul>
      )}
      {onUpload && (
        <fieldset className="texteditor-upload">
          <legend>{t('Neues Bild hochladen')}</legend>
          <label className="field">
            <span>{t('Datei')}</span>
            <input
              type="file"
              accept="image/jpeg,image/png,image/webp"
              onChange={(e) => crop.choose(e, setFile)}
            />
            {crop.dialog}
            <RightsHint />
          </label>
          <Field
            label={t('Was ist zu sehen? (Alternativtext)')}
            value={alt}
            maxLength={300}
            hint={
              file && !alt.trim()
                ? t(
                    'Ohne Beschreibung erfahren blinde Besucher nicht, was auf dem Bild zu sehen ist.',
                  )
                : undefined
            }
            onChange={(e) => setAlt(e.target.value)}
          />
          {error && <Alert kind="error">{error}</Alert>}
          <div className="button-row">
            <button
              type="button"
              className="button"
              disabled={!file || busy}
              onClick={() => void upload()}
            >
              {t('Hochladen und einfügen')}
            </button>
          </div>
        </fieldset>
      )}
    </Modal>
  )
}
