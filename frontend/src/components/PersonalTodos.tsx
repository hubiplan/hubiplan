import { useState } from 'react'
import { api } from '../api/client.ts'
import { confirmDialog } from './dialog.ts'
import { errorMessage, useLoad } from './forms.ts'
import { LoadError } from './ui.tsx'
import { t } from '../i18n/index.ts'

export function PersonalTodos() {
  const { data, error, reload } = useLoad(
    () =>
      api.get<{ tasks: { id: number; title: string; shared: boolean }[] }>('/api/me/todos/export/'),
    [],
  )
  const [actionError, setActionError] = useState<string | null>(null)
  async function erase(id: number) {
    if (
      !(await confirmDialog({
        title: t('Private Aufgabe endgültig löschen?'),
        message: t('Die Aufgabe und ihre gespeicherten Änderungen werden endgültig gelöscht.'),
        confirmLabel: t('Endgültig löschen'),
      }))
    )
      return
    try {
      await api.del(`/api/me/todos/${id}/`)
      await reload()
    } catch (err) {
      setActionError(errorMessage(err))
    }
  }
  return (
    <details className="card">
      <summary>{t('Meine privaten Aufgaben')}</summary>
      <p>
        {t(
          'Hier kannst du deine privaten Aufgaben auch nach dem Ende eines Zugangs exportieren oder endgültig löschen.',
        )}
      </p>
      <a className="button button-ghost" href="/api/me/todos/export/?files=1">
        {t('Eigene Aufgaben exportieren')}
      </a>
      {error && <LoadError message={error} onRetry={reload} />}
      {actionError && <p role="alert">{actionError}</p>}
      <ul className="plain-list">
        {data?.tasks
          .filter((task) => !task.shared)
          .map((task) => (
            <li key={task.id}>
              {task.title}{' '}
              <button className="button button-ghost" onClick={() => void erase(task.id)}>
                {t('Endgültig löschen')}
              </button>
            </li>
          ))}
      </ul>
    </details>
  )
}
