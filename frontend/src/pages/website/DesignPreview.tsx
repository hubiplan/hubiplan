// Webseite › Gestaltung (Konzept webseite-baukasten G2, Ralf 10.11.2026): Änderungen an Design,
// Farben, Stilreglern, Kopfbild und Startseite landen erst in einem Entwurf. Daneben zeigt ein
// Rahmen die echte Webseite in der Vorschau (Handy, Tablet, Bildschirm); „Veröffentlichen“
// macht den Entwurf öffentlich, frühere Fassungen lassen sich als Entwurf zurückholen.
import { useEffect, useLayoutEffect, useRef, useState } from 'react'
import { hasDraft, websiteApi } from '../../api/website.ts'
import type { Website, WebsiteData } from '../../api/website.ts'
import { confirmDialog } from '../../components/dialog.ts'
import { errorMessage, formatDateTime } from '../../components/forms.ts'
import type { AutoSave } from '../../components/forms.ts'
import { Alert } from '../../components/ui.tsx'
import { useActiveOrg } from '../../org/OrgContext.tsx'
import { t } from '../../i18n/index.ts'

/** Hinweis „Nicht veröffentlichte Änderungen · Veröffentlichen · Verwerfen“ */
export function DraftBar({
  website,
  auto,
  canManage,
  onReset,
}: {
  website: Website
  auto: AutoSave
  canManage: boolean
  onReset: (data: WebsiteData) => void
}) {
  const org = useActiveOrg()
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  if (!canManage || website.draft === undefined) return null
  const open = hasDraft(website)

  async function run(action: () => Promise<WebsiteData>) {
    setBusy(true)
    setError(null)
    try {
      // Erst alles Offene speichern, damit die letzte Änderung dabei ist
      if (!(await auto.flush())) return
      onReset(await action())
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setBusy(false)
    }
  }

  // Schmaler Bildschirm: statt geteilter Ansicht die Vorschau in einem neuen Fenster
  async function preview() {
    setError(null)
    try {
      const result = await websiteApi.openPreview(org.id)
      if (result.url) window.open(result.url, '_blank', 'noopener')
      else setError(t('Für die Vorschau fehlt noch eine Domain.'))
    } catch (err) {
      setError(errorMessage(err))
    }
  }

  async function discard() {
    const ok = await confirmDialog({
      title: t('Entwurf verwerfen?'),
      message: t('Die Gestaltung bleibt, wie sie veröffentlicht ist.'),
      confirmLabel: t('Verwerfen'),
    })
    if (ok) await run(() => websiteApi.discardDesign(org.id))
  }

  return (
    <div className={`draft-bar${open ? ' draft-bar-open' : ''}`} role="status">
      <span>
        {open
          ? t('Nicht veröffentlichte Änderungen. Besucher sehen noch den bisherigen Stand.')
          : t('Alles veröffentlicht.')}
      </span>
      {open && (
        <span className="draft-bar-actions">
          <button
            type="button"
            className="button button-ghost draft-bar-preview"
            onClick={() => void preview()}
          >
            {t('Vorschau')}
          </button>
          <button
            type="button"
            className="button"
            disabled={busy}
            onClick={() => void run(() => websiteApi.publishDesign(org.id))}
          >
            {t('Veröffentlichen')}
          </button>
          <button
            type="button"
            className="button button-ghost"
            disabled={busy}
            onClick={() => void discard()}
          >
            {t('Verwerfen')}
          </button>
        </span>
      )}
      {error && <Alert kind="error">{error}</Alert>}
    </div>
  )
}

/** Frühere Fassungen: zurückholen legt sie als Entwurf an */
export function DesignVersions({
  website,
  auto,
  canManage,
  onReset,
}: {
  website: Website
  auto: AutoSave
  canManage: boolean
  onReset: (data: WebsiteData) => void
}) {
  const org = useActiveOrg()
  const [error, setError] = useState<string | null>(null)
  const versions = website.design_versions ?? []
  if (versions.length === 0) return null

  async function restore(id: number) {
    if (hasDraft(website)) {
      const ok = await confirmDialog({
        title: t('Fassung zurückholen?'),
        message: t('Der jetzige Entwurf wird dabei ersetzt.'),
        confirmLabel: t('Zurückholen'),
      })
      if (!ok) return
    }
    setError(null)
    try {
      if (!(await auto.flush())) return
      onReset(await websiteApi.restoreDesign(org.id, id))
    } catch (err) {
      setError(errorMessage(err))
    }
  }

  return (
    <>
      <p className="muted small">
        {t(
          'Die letzten fünf veröffentlichten Fassungen. Zurückholen legt eine Fassung als Entwurf an; öffentlich wird sie erst mit „Veröffentlichen“.',
        )}
      </p>
      {error && <Alert kind="error">{error}</Alert>}
      <ul className="design-versions">
        {versions.map((v, i) => (
          <li key={v.id}>
            <span>
              {formatDateTime(v.published_at)}
              {v.published_by && <span className="muted"> · {v.published_by}</span>}
              {i === 0 && <span className="muted"> · {t('jetzt öffentlich')}</span>}
            </span>
            {canManage && i > 0 && (
              <button
                type="button"
                className="button button-ghost"
                onClick={() => void restore(v.id)}
              >
                {t('Zurückholen')}
              </button>
            )}
          </li>
        ))}
      </ul>
    </>
  )
}

const DEVICES = {
  phone: { label: () => t('Handy'), width: 390 },
  tablet: { label: () => t('Tablet'), width: 820 },
  desktop: { label: () => t('Bildschirm'), width: 1280 },
} as const
type Device = keyof typeof DEVICES

// Vorschau-Cookie der Webseite gilt 8 Stunden; danach neu verbinden
const CONNECTED_MS = 7 * 60 * 60 * 1000

function connectedKey(website: Website) {
  return `hubiplan.webseite.vorschau.${website.public_key}`
}

function isConnected(website: Website): boolean {
  try {
    const at = Number(sessionStorage.getItem(connectedKey(website)) ?? 0)
    return at > 0 && Date.now() - at < CONNECTED_MS
  } catch {
    return false
  }
}

function markConnected(website: Website) {
  try {
    sessionStorage.setItem(connectedKey(website), String(Date.now()))
  } catch {
    // ohne Speicher verbindet die Vorschau beim nächsten Öffnen neu
  }
}

/** Was die Vorschau neu laden lässt: Entwurf und veröffentlichte Gestaltung */
function stampOf(website: Website): string {
  return JSON.stringify([
    website.draft,
    website.design,
    website.style,
    website.color_roles,
    website.header_image,
    website.home_sections,
  ])
}

/** Die echte Webseite in der Vorschau, umschaltbar Handy / Tablet / Bildschirm */
export function PreviewFrame({ website }: { website: Website }) {
  const org = useActiveOrg()
  const [device, setDevice] = useState<Device>('desktop')
  const [src, setSrc] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [paneWidth, setPaneWidth] = useState(0)
  const pane = useRef<HTMLDivElement>(null)
  const count = useRef(0)
  const stamp = stampOf(website)
  const base = website.url

  async function connect() {
    setError(null)
    try {
      const result = await websiteApi.openPreview(org.id)
      if (!result.url) {
        setError(t('Für die Vorschau fehlt noch eine Domain.'))
        return
      }
      markConnected(website)
      setSrc(result.url)
    } catch (err) {
      setError(errorMessage(err))
    }
  }

  // Beim ersten Mal den Vorschau-Schlüssel tauschen; danach reicht das Cookie der Webseite
  useEffect(() => {
    if (!base) return
    if (isConnected(website)) setSrc(`${base}vorschau/design/`)
    else void connect()
    // nur beim Öffnen der Seite
    // oxlint-disable-next-line react-hooks/exhaustive-deps
  }, [base])

  // Nach jeder gespeicherten Änderung neu laden (zurück auf die Startseite)
  const first = useRef(true)
  useEffect(() => {
    if (first.current) {
      first.current = false
      return
    }
    if (!base || !isConnected(website)) return
    count.current += 1
    setSrc(`${base}vorschau/design/?neu=${count.current}`)
    // oxlint-disable-next-line react-hooks/exhaustive-deps
  }, [stamp])

  useLayoutEffect(() => {
    const el = pane.current
    if (!el || typeof ResizeObserver === 'undefined') return
    const observer = new ResizeObserver(() => setPaneWidth(el.clientWidth))
    observer.observe(el)
    setPaneWidth(el.clientWidth)
    return () => observer.disconnect()
  }, [])

  const width = DEVICES[device].width
  const scale = paneWidth > 0 ? Math.min(1, paneWidth / width) : 1

  return (
    <div className="preview-pane">
      <div className="preview-toolbar">
        <div className="style-segments style-n3" role="group" aria-label={t('Bildschirmgröße')}>
          {(Object.keys(DEVICES) as Device[]).map((key) => (
            <button
              key={key}
              type="button"
              aria-pressed={device === key}
              onClick={() => setDevice(key)}
            >
              {DEVICES[key].label()}
            </button>
          ))}
        </div>
        <button type="button" className="button button-ghost" onClick={() => void connect()}>
          {t('Neu laden')}
        </button>
        {src && (
          <a href={src} target="_blank" rel="noopener noreferrer">
            {t('In neuem Fenster')}
          </a>
        )}
      </div>
      {!base && <Alert kind="info">{t('Für die Vorschau fehlt noch eine Domain.')}</Alert>}
      {error && <Alert kind="error">{error}</Alert>}
      <div className="preview-frame" ref={pane}>
        {src && (
          <iframe
            title={t('Vorschau der Webseite')}
            src={src}
            sandbox="allow-same-origin allow-scripts allow-forms allow-popups allow-popups-to-escape-sandbox"
            style={{
              width,
              height: `${Math.round(100 / scale)}%`,
              transform: scale < 1 ? `scale(${scale})` : undefined,
            }}
          />
        )}
      </div>
    </div>
  )
}
