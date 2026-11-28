import { useState } from 'react'
import { nextcloudApi } from '../../api/nextcloud.ts'
import type { NextcloudClient, NextcloudGroupReport } from '../../api/nextcloud.ts'
import { confirmDialog } from '../../components/dialog.ts'
import { errorMessage } from '../../components/forms.ts'
import { Alert } from '../../components/ui.tsx'
import { formatDayTime } from '../../i18n/format.ts'
import { t } from '../../i18n/index.ts'

// Soll und Ist der abgeglichenen Gruppen: erst auf Knopfdruck, weil HUBIplan dafür jedes Konto
// in der Nextcloud abfragt
export function GroupStatus({
  org,
  client,
  onChanged,
}: {
  org: number
  client: NextcloudClient
  onChanged: (c: NextcloudClient) => void
}) {
  const [report, setReport] = useState<NextcloudGroupReport | null>(null)
  const [message, setMessage] = useState<{ kind: 'success' | 'error'; text: string } | null>(null)
  const [busy, setBusy] = useState(false)
  if (!(client.sync_groups_list ?? '').trim() && !client.sync_groups) return null

  async function load() {
    setMessage(null)
    setBusy(true)
    try {
      setReport(await nextcloudApi.groups(org, client.id))
    } catch (e) {
      setMessage({ kind: 'error', text: errorMessage(e) })
    } finally {
      setBusy(false)
    }
  }

  async function run() {
    const losing = report?.accounts.filter((a) => a.remove.length).length ?? 0
    if (
      losing > 0 &&
      !(await confirmDialog({
        final: false,
        title: t('Gruppen jetzt abgleichen?'),
        message: t(
          '{count} Konten verlieren dabei Gruppen und damit den Zugriff auf deren Ordner und Kalender. Dateien bleiben erhalten.',
          { count: losing },
        ),
        confirmLabel: t('Abgleichen'),
      }))
    )
      return
    setMessage(null)
    setBusy(true)
    try {
      const r = await nextcloudApi.syncGroups(org, client.id, true)
      onChanged(r.client)
      setMessage({
        kind: r.result.errors ? 'error' : 'success',
        text: t('Aufgenommen: {added}, entfernt: {removed}, Fehler: {errors}', {
          added: r.result.added,
          removed: r.result.removed,
          errors: r.result.errors,
        }),
      })
      setReport(await nextcloudApi.groups(org, client.id))
    } catch (e) {
      setMessage({ kind: 'error', text: errorMessage(e) })
    } finally {
      setBusy(false)
    }
  }

  const changes = report?.accounts.filter((a) => a.add.length || a.remove.length || a.error) ?? []
  return (
    <>
      <h3>{t('Gruppen in der Nextcloud')}</h3>
      {client.groups_error && <Alert kind="error">{client.groups_error}</Alert>}
      <p className="muted small">
        {client.groups_synced_at
          ? t('Zuletzt abgeglichen: {when}', { when: formatDayTime(client.groups_synced_at) })
          : t('Noch nicht abgeglichen.')}
      </p>
      {report && report.missing_admin.length > 0 && (
        <Alert kind="error">
          {t('Das Dienstkonto ist nicht Gruppen-Admin von: {groups}', {
            groups: report.missing_admin.join(', '),
          })}
        </Alert>
      )}
      {report && !changes.length && (
        <Alert kind="success">{t('Alle Konten sind in den richtigen Gruppen.')}</Alert>
      )}
      {changes.length > 0 && (
        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr>
                <th>{t('Person')}</th>
                <th>{t('Heute in')}</th>
                <th>{t('Kommt hinzu')}</th>
                <th>{t('Fällt weg')}</th>
              </tr>
            </thead>
            <tbody>
              {changes.map((a) => (
                <tr key={a.id}>
                  <td>
                    {a.name}
                    <div className="muted small">
                      <code className="break-all">{a.nc_user}</code>
                    </div>
                  </td>
                  <td>{a.current.join(', ') || '–'}</td>
                  <td>{a.add.join(', ') || '–'}</td>
                  <td>
                    {a.remove.join(', ') || '–'}
                    {a.error && (
                      <div className={a.missing ? 'muted small' : 'error small'}>{a.error}</div>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {message && <Alert kind={message.kind}>{message.text}</Alert>}
      <div className="button-row">
        <button type="button" className="button" disabled={busy} onClick={() => void load()}>
          {t('Gruppen vergleichen')}
        </button>
        {client.sync_groups && report && (
          <button type="button" className="button" disabled={busy} onClick={() => void run()}>
            {t('Gruppen jetzt abgleichen')}
          </button>
        )}
      </div>
    </>
  )
}
