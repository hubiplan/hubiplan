import { useState } from 'react'
import type { ChangeEvent } from 'react'
import { api } from '../../api/client.ts'
import { orgApi } from '../../api/orgs.ts'
import { Alert, Checkbox } from '../../components/ui.tsx'
import { errorMessage } from '../../components/forms.ts'
import { useImageCrop } from '../../components/ImageCrop.tsx'
import { RightsHint } from '../../components/RightsHint.tsx'
import { t } from '../../i18n/index.ts'

export function LogoUpload({
  uploadUrl,
  logoUrl,
  onChange,
  dark = false,
}: {
  uploadUrl: string
  logoUrl: string | null
  onChange: () => void | Promise<void>
  /** Logo für den Dunkelmodus: Vorschau auf dunklem Grund */
  dark?: boolean
}) {
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  // Wappen kommen oft mit weißem Hintergrund; der wird standardmäßig entfernt. Dunkle
  // Fassungen haben eher helle Ränder, die bleiben sollen
  const [removeBackground, setRemoveBackground] = useState(!dark)
  const crop = useImageCrop({
    title: dark ? t('Ausschnitt für das Logo im Dunkelmodus') : t('Ausschnitt für Logo/Wappen'),
    maxSide: 1024,
  })

  async function upload(e: ChangeEvent<HTMLInputElement>) {
    const chosen = e.target.files?.[0]
    e.target.value = ''
    if (!chosen) return
    const file = await crop.pick(chosen)
    if (!file) return
    setBusy(true)
    setError(null)
    try {
      await orgApi.uploadLogo(uploadUrl, file, removeBackground)
      await onChange()
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setBusy(false)
    }
  }

  async function remove() {
    setBusy(true)
    try {
      await api.del(uploadUrl)
      await onChange()
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="logo-upload-box">
      {logoUrl && (
        <img
          src={logoUrl}
          alt={dark ? t('Logo für den Dunkelmodus') : t('Logo')}
          className={`logo-preview ${dark ? 'logo-preview-dark' : 'logo-preview-checker'}`}
        />
      )}
      <div className="button-row">
        <label className="button button-ghost">
          {logoUrl ? t('Anderes Bild wählen') : t('Bild hochladen')}
          <input
            type="file"
            accept="image/png,image/jpeg,image/webp"
            className="file-input"
            disabled={busy}
            onChange={upload}
          />
        </label>
        {crop.dialog}
        <RightsHint />
        {logoUrl && (
          <button type="button" className="button button-ghost" onClick={remove} disabled={busy}>
            {t('Entfernen')}
          </button>
        )}
      </div>
      <Checkbox
        label={t('Weißen Hintergrund entfernen')}
        hint={t('Weiß am Rand wird durchsichtig, Weiß im Wappen bleibt')}
        checked={removeBackground}
        onChange={setRemoveBackground}
        disabled={busy}
      />
      <p className="muted small">{t('PNG, JPG oder WebP, höchstens 2 MB.')}</p>
      {error && <Alert kind="error">{error}</Alert>}
    </div>
  )
}
