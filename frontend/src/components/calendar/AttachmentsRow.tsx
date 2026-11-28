import { NextcloudPick } from '../NextcloudFiles.tsx'
import { useRef } from 'react'
import { eventApi } from '../../api/events.ts'
import type { CalendarBase, EventDetail } from '../../api/events.ts'
import { errorMessage } from '../forms.ts'
import { Checkbox } from '../ui.tsx'
import { useEventDocumentLink } from './EventDocumentLink.tsx'
import { EventRow } from './EventRow.tsx'
import { confirmDialog } from '../dialog.ts'
import { Modal } from '../Modal.tsx'
import { t } from '../../i18n/index.ts'

export { Modal }

function formatSize(bytes: number): string {
  return bytes >= 1024 * 1024
    ? t('{x} MB', { x: (bytes / 1024 / 1024).toFixed(1).replace('.', ',') })
    : t('{x} KB', { x: Math.max(1, Math.round(bytes / 1024)) })
}

/** Zeile „Anhänge“: Liste, Hochladen und Verknüpfen aus der Ablage als Knöpfe nebeneinander. */
export function AttachmentsRow({
  base,
  event,
  busy,
  inputKey,
  onUpload,
  onChanged,
  onError,
  setBusy,
}: {
  base: CalendarBase
  event: EventDetail
  busy: boolean
  inputKey: number
  onUpload: (file: File) => void
  onChanged: (event: EventDetail) => void
  onError: (text: string) => void
  setBusy: (busy: boolean) => void
}) {
  const input = useRef<HTMLInputElement>(null)
  const documents = useEventDocumentLink({ base, event, disabled: busy, onChanged }, true)
  const items = event.attachments
  return (
    <EventRow
      label={t('Anhänge')}
      actions={
        event.can_edit && (
          <>
            <button
              type="button"
              className="button button-ghost"
              disabled={busy}
              aria-describedby={`event-${event.id}-file-hint`}
              onClick={() => input.current?.click()}
            >
              <span aria-hidden="true">+</span> {t('Datei hinzufügen')}
            </button>
            <input
              key={inputKey}
              ref={input}
              type="file"
              hidden
              aria-label={t('Anhang hinzufügen (PDF, JPEG oder PNG, höchstens 15 MB)')}
              accept="application/pdf,image/jpeg,image/png"
              disabled={busy}
              onChange={(e) => {
                const file = e.target.files?.[0]
                if (file) onUpload(file)
              }}
            />
            {!busy && (
              <NextcloudPick accept={['.pdf', 'image/jpeg', 'image/png']} onFile={onUpload} />
            )}
            {documents.button}
          </>
        )
      }
      extra={documents.panel}
    >
      {items.length === 0 && <span className="muted small">{t('keine')}</span>}
      {items.length > 0 && (
        <ul className="plain-list">
          {items.map((a) => (
            <li key={a.id}>
              {a.available === false ? (
                <span className="muted">{a.name}</span>
              ) : (
                <a href={a.url} target="_blank" rel="noreferrer">
                  {a.name}
                </a>
              )}{' '}
              {a.available !== false && <span className="muted small">{formatSize(a.size)}</span>}
              {a.kind === 'document' && (
                <span className="muted small"> · {t('aus der Ablage')}</span>
              )}
              {event.can_edit && (
                <button
                  type="button"
                  className="link-button"
                  disabled={busy}
                  onClick={async () => {
                    if (
                      !(await confirmDialog({
                        final: false,
                        title: t('Anhang „{name}“ entfernen?', { name: a.name }),
                        message:
                          a.kind === 'document'
                            ? t('Das Dokument bleibt in der Ablage.')
                            : undefined,
                        confirmLabel: t('Entfernen'),
                      }))
                    )
                      return
                    try {
                      await eventApi.removeAttachment(a.url)
                      onChanged(await eventApi.get(base, event.id))
                    } catch (err) {
                      onError(errorMessage(err))
                    }
                  }}
                >
                  {t('entfernen')}
                </button>
              )}
              {event.can_edit && event.visibility === 'public' && a.available !== false && (
                <Checkbox
                  label={t('auf der Webseite zeigen')}
                  checked={!!a.on_website}
                  busy={busy}
                  onChange={async (value) => {
                    setBusy(true)
                    try {
                      onChanged(await eventApi.showOnWebsite(a.url, value))
                    } catch (err) {
                      onError(errorMessage(err))
                    } finally {
                      setBusy(false)
                    }
                  }}
                />
              )}
            </li>
          ))}
        </ul>
      )}
      {event.can_edit && (
        <div id={`event-${event.id}-file-hint`} className="muted small">
          {t('PDF, JPEG oder PNG, höchstens 15 MB')}
        </div>
      )}
    </EventRow>
  )
}
