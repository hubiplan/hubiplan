// Dateien mit der Nextcloud der Einheit (Einstellungen › Nextcloud):
// - „In Nextcloud ablegen“ neben Downloads: Datei in einen Ordner legen, der nur lesend an eine
//   Gruppe freigegeben ist (Vorstand, Kasse, Mitglieder), mit Frist je Art.
// - „Aus Nextcloud“ in Hochladen-Dialogen: Datei aus dem freigegebenen Ordner wählen; sie geht
//   danach denselben Weg wie eine Datei vom eigenen Rechner.
// Ohne eingerichtete Nextcloud zeigen beide nichts an.
import { useEffect, useState } from 'react'
import { requestBlob } from '../api/client.ts'
import { nextcloudFilesApi } from '../api/nextcloud.ts'
import type {
  NextcloudCategory,
  NextcloudEntry,
  NextcloudFilesStatus,
  NextcloudTarget,
} from '../api/nextcloud.ts'
import { formatDay } from '../i18n/format.ts'
import { t } from '../i18n/index.ts'
import { useActiveOrg } from '../org/OrgContext.tsx'
import { errorMessage } from './forms.ts'
import { Modal } from './Modal.tsx'
import { Alert, Checkbox, SelectField } from './ui.tsx'

const cache = new Map<number, Promise<NextcloudFilesStatus | null>>()

/** Stand je Einheit, einmal je Seitenaufruf geladen. */
export function useNextcloudFiles(org: number): NextcloudFilesStatus | null {
  const [status, setStatus] = useState<NextcloudFilesStatus | null>(null)
  useEffect(() => {
    let alive = true
    let promise = cache.get(org)
    if (!promise) {
      promise = nextcloudFilesApi.status(org).catch(() => null)
      cache.set(org, promise)
    }
    void promise.then((s) => {
      if (alive) setStatus(s)
    })
    return () => {
      alive = false
    }
  }, [org])
  return status
}

/** Nur für Tests: zwischengespeicherten Stand vergessen. */
export function forgetNextcloudFiles() {
  cache.clear()
}

function retentionText(years: number | null): string {
  if (years === null) return t('bleibt dauerhaft')
  if (years < 1) return t('wird nach 3 Monaten gelöscht')
  return t('wird nach {years} Jahren gelöscht', { years })
}

/** Knopf „In Nextcloud ablegen“ neben einem Download. */
export function NextcloudSave({
  source,
  filename,
  category,
  target,
}: {
  /** Adresse der Datei in HUBIplan oder eine Funktion, die sie liefert */
  source: string | (() => Promise<Blob>)
  filename: string
  category: NextcloudCategory
  target?: NextcloudTarget
}) {
  const org = useActiveOrg()
  const status = useNextcloudFiles(org.id)
  const [open, setOpen] = useState(false)
  if (!status?.store || !status.targets.length) return null
  return (
    <>
      <button type="button" className="button button-ghost" onClick={() => setOpen(true)}>
        {t('In Nextcloud ablegen')}
      </button>
      {open && (
        <SaveDialog
          org={org.id}
          status={status}
          source={source}
          filename={filename}
          category={category}
          target={target}
          onClose={() => setOpen(false)}
        />
      )}
    </>
  )
}

function SaveDialog({
  org,
  status,
  source,
  filename,
  category,
  target,
  onClose,
}: {
  org: number
  status: NextcloudFilesStatus
  source: string | (() => Promise<Blob>)
  filename: string
  category: NextcloudCategory
  target?: NextcloudTarget
  onClose: () => void
}) {
  const fallback =
    status.targets.find((x) => x.key === (category === 'finance' ? 'finance' : 'board')) ??
    status.targets[0]
  const [where, setWhere] = useState<NextcloudTarget>(
    status.targets.find((x) => x.key === target)?.key ?? fallback.key,
  )
  const [kind, setKind] = useState<NextcloudCategory>(category)
  const [personal, setPersonal] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [done, setDone] = useState<string | null>(null)
  const chosen = status.targets.find((x) => x.key === where)
  const rule = status.categories.find((c) => c.key === kind)
  const blocked = kind === 'personal' && where === 'members'

  async function save() {
    setError(null)
    setBusy(true)
    try {
      const blob = typeof source === 'string' ? await requestBlob('GET', source) : await source()
      const data = new FormData()
      data.append('file', blob, filename)
      data.append('filename', filename)
      data.append('target', where)
      data.append('category', kind)
      if (personal) data.append('personal', '1')
      const r = await nextcloudFilesApi.store(org, data)
      setDone(
        r.delete_after
          ? t('Abgelegt unter {path}. Löschen am {date}.', {
              path: r.path,
              date: formatDay(r.delete_after),
            })
          : t('Abgelegt unter {path}. Bleibt dauerhaft.', { path: r.path }),
      )
    } catch (e) {
      setError(errorMessage(e))
    } finally {
      setBusy(false)
    }
  }

  return (
    <Modal title={t('In Nextcloud ablegen')} onClose={onClose} guard={false}>
      <p className="muted small">
        {t(
          'Die Datei liegt danach auch in der Nextcloud „{name}“, nur zum Lesen für die Gruppe des Ordners. Dort gelten Verschlüsselung, Rechte und Protokoll von HUBIplan nicht mehr.',
          { name: status.name },
        )}
      </p>
      <p>
        <code className="break-all">{filename}</code>
      </p>
      <SelectField
        label={t('Ordner')}
        value={where}
        onChange={(e) => setWhere(e.target.value as NextcloudTarget)}
        hint={
          chosen?.group
            ? t('{folder}, lesen darf die Gruppe „{group}“', {
                folder: chosen.folder,
                group: chosen.group,
              })
            : chosen?.folder
        }
      >
        {status.targets.map((x) => (
          <option key={x.key} value={x.key}>
            {x.label}
          </option>
        ))}
      </SelectField>
      <SelectField
        label={t('Art der Unterlage')}
        value={kind}
        onChange={(e) => setKind(e.target.value as NextcloudCategory)}
        hint={rule ? retentionText(rule.years) : undefined}
      >
        {status.categories.map((c) => (
          <option key={c.key} value={c.key}>
            {c.label}
          </option>
        ))}
      </SelectField>
      {kind === 'personal' && (
        <Checkbox
          label={t('Ich weiß, dass die Datei Personendaten enthält, und lege sie bewusst ab.')}
          checked={personal}
          onChange={setPersonal}
        />
      )}
      {blocked && (
        <Alert kind="error">{t('Listen mit Personendaten nie in den Ordner „Mitglieder“.')}</Alert>
      )}
      {error && <Alert kind="error">{error}</Alert>}
      {done && <Alert kind="success">{done}</Alert>}
      <div className="button-row">
        {!done && (
          <button
            type="button"
            className="button button-primary"
            disabled={busy || blocked || (kind === 'personal' && !personal)}
            onClick={() => void save()}
          >
            {t('Ablegen')}
          </button>
        )}
        <button type="button" className="button" onClick={onClose}>
          {done ? t('Fertig') : t('Abbrechen')}
        </button>
      </div>
    </Modal>
  )
}

function matches(entry: NextcloudEntry, accept: string[]): boolean {
  if (!accept.length) return true
  const name = entry.name.toLowerCase()
  return accept.some((a) =>
    a.startsWith('.') ? name.endsWith(a.toLowerCase()) : entry.content_type.startsWith(a),
  )
}

/** Knopf „Aus Nextcloud“ in einem Hochladen-Dialog. */
export function NextcloudPick({
  onFile,
  accept = [],
  multiple = false,
}: {
  onFile: (file: File) => void | Promise<void>
  /** z. B. ['image/', '.pdf'] */
  accept?: string[]
  multiple?: boolean
}) {
  const org = useActiveOrg()
  const status = useNextcloudFiles(org.id)
  const [open, setOpen] = useState(false)
  if (!status?.pick) return null
  return (
    <>
      <button type="button" className="button" onClick={() => setOpen(true)}>
        {t('Aus Nextcloud')}
      </button>
      {open && (
        <PickDialog
          org={org.id}
          accept={accept}
          multiple={multiple}
          onFile={onFile}
          onClose={() => setOpen(false)}
        />
      )}
    </>
  )
}

function PickDialog({
  org,
  accept,
  multiple,
  onFile,
  onClose,
}: {
  org: number
  accept: string[]
  multiple: boolean
  onFile: (file: File) => void | Promise<void>
  onClose: () => void
}) {
  const [path, setPath] = useState('')
  const [entries, setEntries] = useState<NextcloudEntry[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState<string | null>(null)
  const [taken, setTaken] = useState<string[]>([])

  useEffect(() => {
    let alive = true
    setEntries(null)
    setError(null)
    nextcloudFilesApi
      .list(org, path)
      .then((list) => alive && setEntries(list))
      .catch((e: unknown) => alive && setError(errorMessage(e)))
    return () => {
      alive = false
    }
  }, [org, path])

  async function take(entry: NextcloudEntry) {
    setError(null)
    setBusy(entry.path)
    try {
      const blob = await requestBlob('GET', nextcloudFilesApi.fileUrl(org, entry.path))
      const file = new File([blob], entry.name, {
        type: entry.content_type || blob.type || 'application/octet-stream',
      })
      await onFile(file)
      if (multiple) setTaken((list) => [...list, entry.path])
      else onClose()
    } catch (e) {
      setError(errorMessage(e))
    } finally {
      setBusy(null)
    }
  }

  const up = path.split('/').slice(0, -1).join('/')
  const shown = (entries ?? []).filter((e) => e.is_dir || matches(e, accept))
  return (
    <Modal title={t('Aus Nextcloud übernehmen')} onClose={onClose} guard={false}>
      <p className="muted small">
        {t(
          'HUBIplan holt eine Kopie und prüft sie wie jede hochgeladene Datei. In der Nextcloud bleibt alles, wie es ist.',
        )}
      </p>
      <p className="small">
        <strong>{path ? `/${path}` : '/'}</strong>
      </p>
      {error && <Alert kind="error">{error}</Alert>}
      {entries && !shown.length && (
        <p className="muted small">{t('Hier liegt nichts Passendes.')}</p>
      )}
      <ul className="plain-list">
        {path && (
          <li>
            <button type="button" className="button button-ghost" onClick={() => setPath(up)}>
              {t('Eine Ebene höher')}
            </button>
          </li>
        )}
        {shown.map((e) => (
          <li key={e.path}>
            {e.is_dir ? (
              <button type="button" className="button button-ghost" onClick={() => setPath(e.path)}>
                {t('Ordner')}: {e.name}
              </button>
            ) : (
              <button
                type="button"
                className="button button-ghost"
                disabled={busy !== null || taken.includes(e.path)}
                onClick={() => void take(e)}
              >
                {e.name}
                {taken.includes(e.path) ? ` (${t('übernommen')})` : ''}
              </button>
            )}
          </li>
        ))}
      </ul>
      <div className="button-row">
        <button type="button" className="button" onClick={onClose}>
          {multiple && taken.length ? t('Fertig') : t('Abbrechen')}
        </button>
      </div>
    </Modal>
  )
}
