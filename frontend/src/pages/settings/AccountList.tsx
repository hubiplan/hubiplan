import { useState } from 'react'
import { nextcloudApi } from '../../api/nextcloud.ts'
import type { NextcloudAccount, NextcloudClient } from '../../api/nextcloud.ts'
import { confirmDialog } from '../../components/dialog.ts'
import { errorMessage, useLoad } from '../../components/forms.ts'
import { Alert, LoadError } from '../../components/ui.tsx'
import { formatDayTime } from '../../i18n/format.ts'
import { t } from '../../i18n/index.ts'

export function AccountList({
  org,
  client,
  onChanged,
}: {
  org: number
  client: NextcloudClient
  onChanged: (c: NextcloudClient) => void
}) {
  const { data, error, reload } = useLoad(
    () => nextcloudApi.accounts(org, client.id),
    [org, client.id, client.synced_at, client.manage_accounts],
  )
  const [message, setMessage] = useState<{ kind: 'success' | 'error'; text: string } | null>(null)

  async function check() {
    setMessage(null)
    try {
      const r = await nextcloudApi.check(org, client.id)
      setMessage({ kind: 'success', text: r.detail })
    } catch (e) {
      setMessage({ kind: 'error', text: errorMessage(e) })
    }
  }

  async function sync(rows: NextcloudAccount[]) {
    const disabling = rows.filter((r) => r.planned === 'disable').length
    if (
      disabling &&
      !(await confirmDialog({
        title: t('Jetzt abgleichen?'),
        message: t(
          '{count} Konten werden in der Nextcloud deaktiviert. Dateien bleiben erhalten, Sitzungen und Sync-Apps werden abgemeldet.',
          { count: disabling },
        ),
        confirmLabel: t('Jetzt abgleichen'),
        danger: false,
      }))
    )
      return
    setMessage(null)
    try {
      const r = await nextcloudApi.sync(org, client.id, true)
      onChanged(r.client)
      setMessage({
        kind: r.result.errors ? 'error' : 'success',
        text: t('Deaktiviert: {disabled}, wieder aktiviert: {enabled}, Fehler: {errors}', {
          disabled: r.result.disabled,
          enabled: r.result.enabled,
          errors: r.result.errors,
        }),
      })
      reload()
    } catch (e) {
      setMessage({ kind: 'error', text: errorMessage(e) })
    }
  }

  const label = (r: NextcloudAccount) => {
    if (r.planned === 'disable') return t('wird deaktiviert')
    if (r.planned === 'enable') return t('wird wieder aktiviert')
    if (r.disabled_by_hubiplan) return t('deaktiviert')
    return t('aktiv')
  }

  return (
    <>
      <h3>{t('Konten über HUBIplan')}</h3>
      {client.sync_error && <Alert kind="error">{client.sync_error}</Alert>}
      {error && <LoadError message={error} onRetry={reload} />}
      {data && !data.length && (
        <p className="muted small">{t('Noch hat sich niemand über HUBIplan angemeldet.')}</p>
      )}
      {data && data.length > 0 && (
        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr>
                <th>{t('Person')}</th>
                <th>{t('Benutzername in der Nextcloud')}</th>
                <th>{t('Zuletzt angemeldet')}</th>
                <th>{t('Zustand')}</th>
              </tr>
            </thead>
            <tbody>
              {data.map((r) => (
                <tr key={r.id}>
                  <td>
                    {r.name}
                    <div className="muted small">{r.email}</div>
                  </td>
                  <td>
                    <code className="break-all">{r.nc_user}</code>
                  </td>
                  <td>{formatDayTime(r.last_login_at)}</td>
                  <td>
                    {label(r)}
                    {r.reason && (r.planned === 'disable' || r.disabled_by_hubiplan) && (
                      <div className="muted small">{r.reason}</div>
                    )}
                    {r.error && <div className="error small">{r.error}</div>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {client.synced_at && (
        <p className="muted small">
          {t('Zuletzt abgeglichen: {when}', { when: formatDayTime(client.synced_at) })}
        </p>
      )}
      {message && <Alert kind={message.kind}>{message.text}</Alert>}
      <div className="button-row">
        <button type="button" className="button" onClick={() => void check()}>
          {t('Verbindung prüfen')}
        </button>
        {client.manage_accounts && data && (
          <button type="button" className="button" onClick={() => void sync(data)}>
            {t('Jetzt abgleichen')}
          </button>
        )}
      </div>
    </>
  )
}
