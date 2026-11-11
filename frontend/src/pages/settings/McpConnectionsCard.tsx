import { useState } from 'react'
import { mcpApi } from '../../api/mcp.ts'
import type { McpConnection } from '../../api/mcp.ts'
import { confirmDialog } from '../../components/dialog.ts'
import { useQueryLoad } from '../../components/forms.ts'
import { LoadError, Loading } from '../../components/ui.tsx'
import { locale, t } from '../../i18n/index.ts'

function formatDate(value: string): string {
  return new Date(value).toLocaleString(locale(), { dateStyle: 'medium', timeStyle: 'short' })
}

// Mein Konto: verbundene KI-Assistenten ansehen und trennen (docs/mcp.md, Stufe 1a).
export function McpConnectionsCard() {
  const list = useQueryLoad(() => mcpApi.connections(), [])
  const [error, setError] = useState<string | null>(null)
  const data = list.data

  if (list.error)
    return (
      <section className="card">
        <h2>{t('KI-Assistenten')}</h2>
        <LoadError message={list.error} onRetry={() => void list.reload()} />
      </section>
    )
  if (!data) return list.loading ? <Loading /> : null
  if (!data.enabled) return null

  async function disconnect(c: McpConnection) {
    if (!(await confirmDialog(t('Verbindung zu „{name}“ trennen?', { name: c.client })))) return
    setError(null)
    try {
      await mcpApi.disconnect(c.id)
      await list.reload()
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    }
  }

  return (
    <section className="card">
      <h2>{t('KI-Assistenten')}</h2>
      <p className="muted small">
        {t(
          'KI-Assistenten wie Claude oder ChatGPT können die Webseite deiner Einheit lesen und als Entwurf bearbeiten. Trage dazu im Assistenten diese Adresse als Verbindung (MCP-Server) ein:',
        )}
      </p>
      <p>
        <code>{data.address}</code>
      </p>
      {error && (
        <p className="alert alert-error" role="alert">
          {error}
        </p>
      )}
      <h3>{t('Verbundene Assistenten')}</h3>
      {data.connections.length === 0 ? (
        <p className="muted">{t('Noch kein Assistent verbunden.')}</p>
      ) : (
        <ul className="item-list">
          {data.connections.map((c) => (
            <li key={c.id} className="item-row">
              <div className="item-row-info">
                <span>
                  <strong>{c.client}</strong> · {c.organization}
                </span>
                <span className="muted small">
                  {t('zuletzt benutzt {x}, gilt bis {y}', {
                    x: formatDate(c.last_used_at),
                    y: formatDate(c.expires_at),
                  })}
                </span>
              </div>
              <div className="button-row">
                <button
                  type="button"
                  className="button button-ghost"
                  onClick={() => void disconnect(c)}
                >
                  {t('Trennen')}
                </button>
              </div>
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}
