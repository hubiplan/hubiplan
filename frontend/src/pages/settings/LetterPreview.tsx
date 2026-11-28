import { useEffect, useRef, useState } from 'react'
import { errorMessage } from '../../components/forms.ts'
import { Alert } from '../../components/ui.tsx'
import { t } from '../../i18n/index.ts'

/** Vorschau der ersten Seite als PDF; lädt neu, wenn sich ``version`` ändert. */
export function LetterPreview({ load, version }: { load: () => Promise<Blob>; version: string }) {
  const [url, setUrl] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const loader = useRef(load)
  useEffect(() => {
    loader.current = load
  })
  useEffect(() => {
    let current: string | null = null
    let cancelled = false
    loader
      .current()
      .then((blob) => {
        if (cancelled) return
        current = URL.createObjectURL(blob)
        setUrl(current)
        setError(null)
      })
      .catch((err: unknown) => {
        if (!cancelled) setError(errorMessage(err))
      })
    return () => {
      cancelled = true
      if (current) URL.revokeObjectURL(current)
    }
  }, [version])
  if (error)
    return (
      <Alert kind="error">
        {t('Vorschau nicht verfügbar:')} {error}
      </Alert>
    )
  if (!url) return <p className="muted">{t('Vorschau lädt …')}</p>
  return (
    <>
      {/* view=Fit (Chrome/Edge) bzw. zoom=page-fit (Firefox): ganze Seite einpassen, kein Querscrollen */}
      <iframe
        className="letter-preview"
        src={`${url}#view=Fit&zoom=page-fit`}
        title={t('Vorschau der ersten Seite')}
      />
      <p className="small">
        <a href={url} target="_blank" rel="noreferrer">
          {t('Vorschau in neuem Fenster öffnen')}
        </a>
      </p>
    </>
  )
}
