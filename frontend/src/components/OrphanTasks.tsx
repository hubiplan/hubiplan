import { useState } from 'react'
import { api } from '../api/client.ts'
import { errorMessage, useLoad } from './forms.ts'
import { LoadError } from './ui.tsx'
import { t } from '../i18n/index.ts'

export function OrphanTasks({ base, onSaved }: { base: string; onSaved: () => void }) {
  const { data, error, reload } = useLoad(
    () => api.get<{ items: { id: number }[] }>(`${base}orphans/`),
    [base],
  )
  const [actionError, setActionError] = useState<string | null>(null)
  if (!data?.items.length && !error && !actionError) return null
  return (
    <details className="todo-notice" open={!!error || !!actionError || undefined}>
      <summary>
        {t('Aufgaben ohne verantwortliches Konto')}
        {!!data?.items.length && <span className="badge">{data.items.length}</span>}
      </summary>
      <p>
        {t(
          'Hier kannst du die Verantwortung für verwaiste geteilte Aufgaben übernehmen. Private Aufgaben erscheinen hier nicht.',
        )}
      </p>
      {error && <LoadError message={error} onRetry={reload} />}
      {actionError && <p role="alert">{actionError}</p>}
      {data?.items.map((row) => (
        <p key={row.id}>
          {t('Aufgabe')} {row.id}{' '}
          <button
            className="button button-ghost"
            onClick={() => {
              void api
                .post(`${base}${row.id}/take-over/`, {})
                .then(() => {
                  void reload()
                  onSaved()
                })
                .catch((err: unknown) => setActionError(errorMessage(err)))
            }}
          >
            {t('Verantwortung übernehmen')}
          </button>
        </p>
      ))}
    </details>
  )
}
