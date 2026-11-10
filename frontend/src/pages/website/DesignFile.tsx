// Webseite › Gestaltung › „Gestaltung als Datei“ (Konzept webseite-baukasten G6, Ralf
// 10.11.2026): Design, Farbzuordnung, Feinabstimmung und Darstellung der Bereiche sind nur
// Werte, kein CSS. Wer die Webseite verwaltet, speichert sie als Datei und lädt sie bei einer
// anderen Einheit oder Installation wieder. Geladenes landet im Entwurf (G2); HUBIplan prüft
// jeden Wert wie bei einer Änderung von Hand.
import { useState } from 'react'
import { saveBlob } from '../../api/client.ts'
import type { ColorRoles, StyleValues } from '../../api/website.ts'
import { Alert } from '../../components/ui.tsx'
import { t } from '../../i18n/index.ts'

export const DESIGN_FILE_FORMAT = 'hubiplan-gestaltung'
const MAX_BYTES = 100_000

export interface DesignValues {
  design: string
  color_roles: ColorRoles
  style: StyleValues
  layouts: Record<string, string>
}

/** Inhalt der Datei: nur das gewählte Design mit seiner Farbzuordnung */
export function designFile(values: DesignValues) {
  const roles = values.color_roles[values.design]
  return {
    format: DESIGN_FILE_FORMAT,
    version: 1,
    design: values.design,
    color_roles: roles ? { [values.design]: roles } : {},
    style: values.style,
    layouts: values.layouts,
  }
}

const isObject = (x: unknown): x is Record<string, unknown> =>
  typeof x === 'object' && x !== null && !Array.isArray(x)

/** Datei lesen; wirft einen Fehler mit lesbarer Meldung */
export function readDesignFile(text: string): Partial<DesignValues> {
  let data: unknown
  try {
    data = JSON.parse(text)
  } catch {
    throw new Error(t('Die Datei ist keine Gestaltung aus HUBIplan.'))
  }
  if (!isObject(data) || data.format !== DESIGN_FILE_FORMAT) {
    throw new Error(t('Die Datei ist keine Gestaltung aus HUBIplan.'))
  }
  if (typeof data.version !== 'number' || data.version > 1) {
    throw new Error(t('Diese Datei stammt aus einer neueren Fassung von HUBIplan.'))
  }
  const result: Partial<DesignValues> = {}
  if (typeof data.design === 'string') result.design = data.design
  if (isObject(data.color_roles)) result.color_roles = data.color_roles as ColorRoles
  if (isObject(data.style)) result.style = data.style as StyleValues
  if (isObject(data.layouts)) result.layouts = data.layouts as Record<string, string>
  return result
}

export function DesignFile({
  values,
  designs,
  onLoad,
}: {
  values: DesignValues
  /** Designs, die diese Webseite wählen kann: Schlüssel → Name */
  designs: Record<string, string>
  onLoad: (values: Partial<DesignValues>) => void
}) {
  const [message, setMessage] = useState<{ kind: 'success' | 'error' | 'info'; text: string }>()
  const [inputKey, setInputKey] = useState(0)

  function save() {
    const blob = new Blob([JSON.stringify(designFile(values), null, 2)], {
      type: 'application/json',
    })
    saveBlob(blob, `gestaltung-${values.design}.json`)
  }

  async function load(file: File | undefined) {
    setMessage(undefined)
    setInputKey((k) => k + 1)
    if (!file) return
    if (file.size > MAX_BYTES) {
      setMessage({ kind: 'error', text: t('Die Datei ist keine Gestaltung aus HUBIplan.') })
      return
    }
    let loaded: Partial<DesignValues>
    try {
      loaded = readDesignFile(await file.text())
    } catch (err) {
      setMessage({ kind: 'error', text: (err as Error).message })
      return
    }
    // Ein Design, das es hier nicht gibt, bleibt außen vor; der Rest gilt trotzdem
    const unknown = loaded.design !== undefined && !(loaded.design in designs)
    const next: Partial<DesignValues> = { ...loaded }
    if (unknown) delete next.design
    if (loaded.color_roles) next.color_roles = { ...values.color_roles, ...loaded.color_roles }
    onLoad(next)
    setMessage(
      unknown
        ? {
            kind: 'info',
            text: t(
              'Das Design „{x}“ gibt es auf dieser Webseite nicht. Feinabstimmung und Darstellung sind trotzdem im Entwurf.',
              { x: loaded.design! },
            ),
          }
        : {
            kind: 'success',
            text: t(
              'Die Gestaltung ist geladen und steht im Entwurf. Prüfe die Vorschau und veröffentliche sie.',
            ),
          },
    )
  }

  return (
    <>
      <p className="muted small">
        {t(
          'Speichert Design, Farbzuordnung, Feinabstimmung und Darstellung der Bereiche als Datei. Bei einer anderen Einheit oder auf einem anderen Server lädst du sie hier wieder. Wappen, Texte, Bilder und die Startseite gehören nicht dazu; die Farben richten sich nach der Palette der Einheit, die die Datei lädt.',
        )}
      </p>
      {message && <Alert kind={message.kind}>{message.text}</Alert>}
      <div className="button-row">
        <button type="button" className="button button-ghost" onClick={save}>
          {t('Gestaltung speichern')}
        </button>
        <label className="button button-ghost file-button">
          {t('Gestaltung laden')}
          <input
            key={inputKey}
            type="file"
            className="file-input"
            accept=".json,application/json"
            onChange={(e) => void load(e.target.files?.[0])}
          />
        </label>
      </div>
    </>
  )
}
