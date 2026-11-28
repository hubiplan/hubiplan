import { NextcloudPick } from '../../components/NextcloudFiles.tsx'
import { useRef } from 'react'
import { t } from '../../i18n/index.ts'
import { ACCEPT } from './imagesHelpers.ts'

/** Knopf „Bilder hochladen“ (mehrere Dateien) samt Ziehen auf die Fläche */
export function UploadButton({
  label = t('Bilder hochladen'),
  multiple = true,
  disabled,
  onFiles,
}: {
  label?: string
  multiple?: boolean
  disabled?: boolean
  onFiles: (files: File[]) => void
}) {
  const input = useRef<HTMLInputElement>(null)
  return (
    <>
      <button
        type="button"
        className="button"
        disabled={disabled}
        onClick={() => input.current?.click()}
      >
        {label}
      </button>
      <input
        ref={input}
        type="file"
        accept={ACCEPT}
        multiple={multiple}
        hidden
        aria-label={label}
        onChange={(e) => {
          const files = Array.from(e.target.files ?? [])
          e.target.value = ''
          if (files.length) onFiles(files)
        }}
      />
      {!disabled && (
        <NextcloudPick accept={['image/']} multiple={multiple} onFile={(f) => onFiles([f])} />
      )}
    </>
  )
}

// --- Filter ---
