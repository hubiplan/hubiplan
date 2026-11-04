import '../todos.css'
import { useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { api } from '../../api/client.ts'
import { errorMessage, useLoad } from '../../components/forms.ts'
import { LoadError } from '../../components/ui.tsx'
import { t } from '../../i18n/index.ts'

export interface MemberTodo {
  id: number
  title: string
  description: string
  status: 'open' | 'done'
  version: number
  due_label: string
  can_complete: boolean
  can_claim: boolean
  claimed_by_me: boolean
  attachments: { id: number; name: string; available: boolean }[]
}

export function PortalTodos({ accessId }: { accessId: number }) {
  const base = `/api/portal/${accessId}/todos/`
  const { data, error, reload, setData } = useLoad(
    () => api.get<{ items: MemberTodo[] }>(base),
    [base],
  )
  const [params, setParams] = useSearchParams()
  const [done, setDone] = useState(false)
  const [busy, setBusy] = useState(false)
  const [actionError, setActionError] = useState<string | null>(null)
  const selected = data?.items.find((row) => String(row.id) === params.get('aufgabe'))
  async function change(item: MemberTodo, values: object) {
    setBusy(true)
    setActionError(null)
    try {
      await api.patch(`${base}${item.id}/`, { version: item.version, ...values })
      await reload()
    } catch (err) {
      setActionError(errorMessage(err))
      setData(null)
      await reload()
    } finally {
      setBusy(false)
    }
  }
  return (
    <section className="todo-workspace stack">
      <p>
        {t(
          'Hier stehen Aufgaben, die für dich freigegeben sind, und offene Angebote deiner Einheit.',
        )}
      </p>
      <div className="button-row" role="group" aria-label={t('Aufgaben')}>
        <button className="button button-ghost" aria-pressed={!done} onClick={() => setDone(false)}>
          {t('Offen')}
        </button>
        <button className="button button-ghost" aria-pressed={done} onClick={() => setDone(true)}>
          {t('Erledigt')}
        </button>
        <button
          className="button button-ghost"
          onClick={() => {
            setData(null)
            void reload()
          }}
        >
          {t('Aktualisieren')}
        </button>
      </div>
      {error && <LoadError message={error} onRetry={reload} />}
      {actionError && <p role="alert">{actionError}</p>}
      {selected && (
        <article className="card stack">
          <h2>{selected.title}</h2>
          <p className="todo-description">{selected.description}</p>
          <p>{selected.due_label || t('ohne Frist')}</p>
          <ul>
            {selected.attachments?.map((file) => (
              <li key={file.id}>
                {file.available ? (
                  <a href={`${base}${selected.id}/attachments/${file.id}/`}>{file.name}</a>
                ) : (
                  file.name
                )}
              </li>
            ))}
          </ul>
          <div className="button-row">
            {selected.can_claim && (
              <button
                className="button"
                disabled={busy}
                onClick={() => void change(selected, { action: 'claim' })}
              >
                {t('Aufgabe übernehmen')}
              </button>
            )}
            {selected.can_complete && (
              <button
                className="button"
                disabled={busy}
                onClick={() =>
                  void change(selected, { status: selected.status === 'done' ? 'open' : 'done' })
                }
              >
                {t(selected.status === 'done' ? 'Wieder öffnen' : 'Erledigen')}
              </button>
            )}
            {selected.claimed_by_me && selected.status === 'open' && (
              <button
                className="button button-ghost"
                disabled={busy}
                onClick={() => void change(selected, { action: 'release' })}
              >
                {t('Übernahme zurückgeben')}
              </button>
            )}
            <button
              className="button button-ghost"
              disabled={busy}
              onClick={() => {
                const next = new URLSearchParams(params)
                next.delete('aufgabe')
                setParams(next)
              }}
            >
              {t('Schließen')}
            </button>
          </div>
        </article>
      )}
      <ul className="plain-list task-list">
        {data?.items
          .filter((row) => (row.status === 'done') === done)
          .map((item) => (
            <li key={item.id}>
              <button
                className="button button-ghost"
                onClick={() => {
                  const next = new URLSearchParams(params)
                  next.set('aufgabe', String(item.id))
                  setParams(next)
                }}
              >
                {item.title}
              </button>
              <span>{item.due_label || t('ohne Frist')}</span>
            </li>
          ))}
      </ul>
      {data && !data.items.filter((row) => (row.status === 'done') === done).length && (
        <p>{t('Keine Aufgaben vorhanden.')}</p>
      )}
    </section>
  )
}
