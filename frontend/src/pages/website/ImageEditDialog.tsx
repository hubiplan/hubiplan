import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { contentApi } from '../../api/website.ts'
import type { WebsiteImage, WebsiteImageDetail } from '../../api/website.ts'
import {
  errorMessage,
  formatDateTime,
  useAutoSave,
  useForm,
  useLoad,
} from '../../components/forms.ts'
import { useImageCrop } from '../../components/ImageCrop.tsx'
import type { CropArea } from '../../components/ImageCrop.tsx'
import { Modal } from '../../components/Modal.tsx'
import {
  Alert,
  Checkbox,
  Field,
  LoadError,
  SaveStatus,
  SelectField,
  Loading,
} from '../../components/ui.tsx'
import { useActiveOrg } from '../../org/OrgContext.tsx'
import { removeImage } from './imageTools.ts'
import { t } from '../../i18n/index.ts'
import { type Unit } from './imagesHelpers.ts'
import { UploadButton } from './UploadButton.tsx'

const FULL: CropArea = { x: 0, y: 0, width: 100, height: 100, rotation: 0, aspect: 'original' }

async function loadFile(url: string, name: string): Promise<File> {
  const res = await fetch(url, { credentials: 'same-origin' })
  if (!res.ok) throw new Error(t('Das Original ließ sich nicht laden.'))
  const blob = await res.blob()
  return new File([blob], name, { type: blob.type || 'image/jpeg' })
}

export function ImageEditDialog({
  id,
  units,
  onChanged,
  onOpen,
  onClose,
}: {
  id: number
  units: Unit[]
  onChanged: () => void
  /** anderes Bild öffnen (nach „Als Kopie bearbeiten“) */
  onOpen?: (id: number) => void
  onClose: () => void
}) {
  const org = useActiveOrg()
  const { data, error, reload, setData } = useLoad(() => contentApi.image(org.id, id), [org.id, id])
  // „Schließen“ oben im Fenster wartet, bis die Angaben gespeichert sind
  const flush = useRef<(() => Promise<boolean>) | null>(null)
  return (
    <Modal
      title={t('Bild bearbeiten')}
      onClose={onClose}
      beforeClose={() => flush.current?.() ?? true}
    >
      {error && <LoadError message={error} onRetry={() => void reload()} />}
      {!data && !error && <Loading />}
      {data && (
        <ImageEditForm
          key={data.id}
          image={data}
          units={units}
          onChanged={(image) => {
            setData({ ...data, ...image })
            onChanged()
          }}
          onCopied={(copy) => {
            onChanged()
            onOpen?.(copy.id)
          }}
          onDeleted={() => {
            onChanged()
            onClose()
          }}
          onClose={onClose}
          flushRef={flush}
        />
      )}
    </Modal>
  )
}

function ImageEditForm({
  image,
  units,
  onChanged,
  onCopied,
  onDeleted,
  onClose,
  flushRef,
}: {
  image: WebsiteImageDetail
  units: Unit[]
  onChanged: (image: WebsiteImage) => void
  onCopied: (copy: WebsiteImage) => void
  onDeleted: () => void
  onClose: () => void
  /** zum Speichern vor dem Schließen des Fensters */
  flushRef: { current: (() => Promise<boolean>) | null }
}) {
  const org = useActiveOrg()
  const form = useForm({
    caption: image.caption,
    alt_text: image.alt_text,
    credit: image.credit ?? '',
    decorative: !!image.decorative,
    department: image.department ?? null,
  })
  const { values: v, set, errors } = form
  const auto = useAutoSave(form, (changes) => contentApi.saveImage(org.id, image.id, changes), {
    onSaved: (saved) => onChanged(saved as WebsiteImage),
  })
  useEffect(() => {
    flushRef.current = auto.flush
    return () => {
      flushRef.current = null
    }
  }, [flushRef, auto.flush])
  const crop = useImageCrop({ title: t('Ausschnitt ändern') })
  const replace = useImageCrop({ title: t('Neues Bild zuschneiden') })
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState<string | null>(null)
  const [copied, setCopied] = useState(false)

  async function run(action: () => Promise<void>) {
    setMessage(null)
    setBusy(true)
    try {
      await action()
    } catch (err) {
      setMessage(errorMessage(err))
    } finally {
      setBusy(false)
    }
  }

  async function original(): Promise<File> {
    return loadFile(image.original_url ?? image.url, `bild-${image.key}.jpg`)
  }

  const recrop = () =>
    run(async () => {
      const file = await original()
      const result = await crop.pickArea(file, image.crop as CropArea)
      if (!result) return
      onChanged(await contentApi.cropImage(org.id, image.id, result.file, result.crop ?? FULL))
    })

  const copy = () =>
    run(async () => {
      const file = await original()
      const result = await crop.pickArea(file, image.crop as CropArea)
      if (!result) return
      onCopied(await contentApi.copyImage(org.id, image.id, result.file, result.crop ?? FULL))
    })

  const replaceWith = (file: File) =>
    run(async () => {
      const result = await replace.pickArea(file)
      if (!result) return
      onChanged(
        await contentApi.replaceImage(org.id, image.id, {
          file: result.file,
          original: result.crop ? file : null,
          crop: result.crop,
        }),
      )
    })

  const remove = () =>
    run(async () => {
      if (!(await auto.flush())) return
      if (await removeImage(org.id, image)) onDeleted()
    })

  return (
    <form
      className="image-edit"
      onSubmit={(e) => e.preventDefault()}
      aria-label={t('Bild bearbeiten')}
    >
      <div className="image-edit-preview">
        <img src={image.url} alt={image.alt_text} />
        <div className="button-row">
          <button type="button" className="button" disabled={busy} onClick={() => void recrop()}>
            {t('Ausschnitt ändern')}
          </button>
        </div>
        <p className="muted small">
          {t(
            'Der Ausschnitt wird aus dem Original neu gewählt; „Unverändert übernehmen“ zeigt wieder das ganze Bild.',
          )}
        </p>
      </div>
      <div className="image-edit-fields">
        <SaveStatus auto={auto} />
        <Field
          label={t('Bildunterschrift')}
          value={v.caption}
          maxLength={300}
          error={errors.caption}
          onChange={(e) => set('caption', e.target.value)}
        />
        <Field
          label={t('Alternativtext (was zu sehen ist)')}
          value={v.alt_text}
          maxLength={300}
          disabled={v.decorative}
          error={errors.alt_text}
          hint={
            !v.alt_text.trim() && !v.decorative
              ? t(
                  'Ohne Beschreibung erfahren blinde Besucher nicht, was auf dem Bild zu sehen ist.',
                )
              : undefined
          }
          onChange={(e) => set('alt_text', e.target.value)}
        />
        <Field
          label={t('Urheber/in')}
          value={v.credit}
          maxLength={200}
          error={errors.credit}
          hint={t(
            'Wer das Foto gemacht oder bereitgestellt hat, z. B. „Max Mustermann“, bei freien Bildern mit Lizenz. Die Webseite zeigt „Foto: …“ am Bild und im Impressum.',
          )}
          onChange={(e) => set('credit', e.target.value)}
        />
        <Checkbox
          label={t('Nur Schmuck, das Bild zeigt nichts Wichtiges')}
          hint={t('dann ohne Beschreibung')}
          checked={v.decorative}
          onChange={(on) => set('decorative', on)}
        />
        {units.length > 0 && (
          <SelectField
            label={t('Gehört zu')}
            value={v.department ?? ''}
            error={errors.department}
            hint={t('Bei der Bildauswahl einer Untereinheit stehen ihre Bilder vorn.')}
            onChange={(e) => set('department', e.target.value ? Number(e.target.value) : null)}
          >
            <option value="">{t('Verein allgemein')}</option>
            {units.map((u) => (
              <option key={u.id} value={u.id}>
                {u.name}
              </option>
            ))}
          </SelectField>
        )}
        <h3>{t('Verwendet in')}</h3>
        {image.usage.length === 0 ? (
          <p className="muted small">{t('Noch in keinem Text.')}</p>
        ) : (
          <>
            <ul className="plain-list small">
              {image.usage.map((u) => (
                <li key={u.album ? `a${u.album}` : u.header ? 'kopf' : `t${u.text}`}>
                  <Link
                    to={
                      u.album
                        ? `/webseite/galerie?album=${u.album}`
                        : u.header
                          ? '/webseite/gestaltung'
                          : `/webseite/inhalte?text=${u.text}`
                    }
                    onClick={onClose}
                  >
                    {u.label}
                  </Link>
                  : {u.places.join(', ')}
                </li>
              ))}
            </ul>
            <p className="muted small">
              {t(
                'Änderungen am Bild wirken sofort an allen Stellen, auch auf der veröffentlichten Webseite.',
              )}
            </p>
          </>
        )}
        {message && <Alert kind="error">{message}</Alert>}
        {crop.dialog}
        {replace.dialog}
        <details className="image-edit-more">
          <summary>{t('Mehr')}</summary>
          <div className="button-row">
            <UploadButton
              label={t('Datei ersetzen')}
              multiple={false}
              disabled={busy}
              onFiles={(files) => void replaceWith(files[0])}
            />
            <button
              type="button"
              className="button button-ghost"
              disabled={busy}
              onClick={() => void copy()}
            >
              {t('Als Kopie bearbeiten')}
            </button>
            <button
              type="button"
              className="button button-ghost"
              onClick={() => {
                void navigator.clipboard?.writeText(image.markdown)
                setCopied(true)
              }}
            >
              {copied ? t('Schnipsel kopiert') : t('Schnipsel kopieren')}
            </button>
          </div>
          <p className="muted small">
            {t(
              '„Datei ersetzen“ behält alle Stellen und Angaben. „Als Kopie bearbeiten“ legt ein zweites Bild aus demselben Original an, z. B. breit für den Seitenkopf und quadratisch fürs Karussell.',
            )}
          </p>
          <p className="muted small">
            {image.width} {t('× {height} Pixel · hochgeladen am', { height: image.height })}{' '}
            {formatDateTime(image.uploaded_at)}
            <br />
            <code>{image.markdown}</code>
          </p>
        </details>
        <div className="button-row">
          <button
            type="button"
            className="button button-danger"
            disabled={busy}
            onClick={() => void remove()}
          >
            {t('Löschen')}
          </button>
        </div>
      </div>
    </form>
  )
}

// --- Auswahl ---
