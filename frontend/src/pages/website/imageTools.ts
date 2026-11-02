// Hilfen für die Bilder der Webseite (Übersicht, Bearbeiten, Auswahl in images.tsx).
import { useEffect, useRef, useState } from 'react'
import { ApiError } from '../../api/client.ts'
import { contentApi } from '../../api/website.ts'
import type { WebsiteImage } from '../../api/website.ts'
import { confirmDialog } from '../../components/dialog.ts'
import { errorMessage } from '../../components/forms.ts'
import { useImageCrop } from '../../components/ImageCrop.tsx'
import { useActiveOrg } from '../../org/OrgContext.tsx'
import { t } from '../../i18n/index.ts'

export function imageLabel(i: WebsiteImage): string {
  return i.caption || i.alt_text || t('ohne Beschriftung')
}

export function needsAlt(i: WebsiteImage): boolean {
  return !i.alt_text && !i.decorative
}

/** Bilder hochladen: je Datei Zuschnitt, dann mit Original und Ausschnitt speichern. */
export function useImageUpload() {
  const org = useActiveOrg()
  const crop = useImageCrop()
  const [busy, setBusy] = useState(false)
  // auch während des Zuschneidens, damit Strg+V nicht ein zweites Fenster öffnet
  const [working, setWorking] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function upload(
    files: File[],
    extra: { department?: number | null; alt_text?: string } = {},
  ): Promise<WebsiteImage[]> {
    setError(null)
    setWorking(true)
    const done: WebsiteImage[] = []
    try {
      for (const file of files) {
        const result = await crop.pickArea(file)
        if (!result) continue
        setBusy(true)
        try {
          done.push(
            await contentApi.upload(org.id, {
              file: result.file,
              original: result.crop ? file : null,
              crop: result.crop,
              department: extra.department ?? null,
              alt_text: extra.alt_text,
            }),
          )
        } catch (err) {
          setError(t('{name}: {x}', { name: file.name, x: errorMessage(err) }))
        } finally {
          setBusy(false)
        }
      }
    } finally {
      setWorking(false)
    }
    return done
  }

  return { upload, busy, working, error, dialog: crop.dialog }
}

/** Löschen mit Rückfrage; wird das Bild verwendet, nennt die zweite Rückfrage die Stellen. */
export async function removeImage(orgId: number, image: WebsiteImage): Promise<boolean> {
  const ok = await confirmDialog({ title: t('Bild löschen?'), confirmLabel: t('Löschen') })
  if (!ok) return false
  try {
    await contentApi.removeImage(orgId, image.id)
    return true
  } catch (err) {
    if (!(err instanceof ApiError) || err.status !== 409) throw err
    const again = await confirmDialog({
      title: t('Bild trotzdem löschen?'),
      message: err.message,
      confirmLabel: t('Trotzdem löschen'),
    })
    if (!again) return false
    await contentApi.removeImage(orgId, image.id, true)
    return true
  }
}

export type ImageOrder = 'newest' | 'oldest' | 'name' | 'changed'

export const IMAGE_ORDERS: { value: ImageOrder; label: string }[] = [
  { value: 'newest', label: t('neueste zuerst') },
  { value: 'oldest', label: t('älteste zuerst') },
  { value: 'name', label: t('nach Name') },
  { value: 'changed', label: t('zuletzt bearbeitet') },
]

const byName = new Intl.Collator('de', { sensitivity: 'base', numeric: true })

/** Bilder sortiert (Hochladedatum, Name oder letzte Änderung); bei Gleichstand neueste zuerst. */
export function sortImages(images: WebsiteImage[], order: ImageOrder): WebsiteImage[] {
  const time = (value?: string) => (value ? Date.parse(value) || 0 : 0)
  const newest = (a: WebsiteImage, b: WebsiteImage) =>
    time(b.uploaded_at) - time(a.uploaded_at) || b.id - a.id
  const compare: Record<ImageOrder, (a: WebsiteImage, b: WebsiteImage) => number> = {
    newest,
    oldest: (a, b) => -newest(a, b),
    name: (a, b) => byName.compare(imageLabel(a), imageLabel(b)) || newest(a, b),
    changed: (a, b) =>
      time(b.updated_at ?? b.uploaded_at) - time(a.updated_at ?? a.uploaded_at) || newest(a, b),
  }
  return [...images].sort(compare[order])
}

const PASTE_TYPES = ['image/jpeg', 'image/png', 'image/webp']

/** Bilder aus der Zwischenablage (Ralf 02.11.: Strg+V), z. B. ein kopiertes Bildschirmfoto.
 * Kopierte Bilder haben meist den Namen „image.png“; sie bekommen einen sprechenden. */
export function pastedImages(data: DataTransfer | null): File[] {
  const files = Array.from(data?.files ?? []).filter((f) => PASTE_TYPES.includes(f.type))
  const stamp = new Date().toISOString().slice(0, 19).replace(/[T:]/g, '-')
  return files.map((f, i) =>
    f.name && f.name !== 'image.png'
      ? f
      : new File(
          [f],
          `${t('zwischenablage')}-${stamp}${files.length > 1 ? `-${i + 1}` : ''}.${f.type.split('/')[1].replace('jpeg', 'jpg')}`,
          {
            type: f.type,
          },
        ),
  )
}

/** Strg+V lädt kopierte Bilder hoch, solange `enabled`; Text einfügen bleibt unberührt. */
export function usePasteImages(enabled: boolean, onFiles: (files: File[]) => void) {
  const handler = useRef(onFiles)
  useEffect(() => {
    handler.current = onFiles
  })
  useEffect(() => {
    if (!enabled) return
    function paste(e: ClipboardEvent) {
      const files = pastedImages(e.clipboardData)
      if (!files.length) return
      e.preventDefault()
      handler.current(files)
    }
    document.addEventListener('paste', paste)
    return () => document.removeEventListener('paste', paste)
  }, [enabled])
}
