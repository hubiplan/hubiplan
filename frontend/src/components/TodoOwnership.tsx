import { useState } from 'react'
import { todoApi } from '../api/todos.ts'
import type { Todo } from '../api/todos.ts'
import { errorMessage } from './forms.ts'
import { SelectField } from './ui.tsx'
import { t } from '../i18n/index.ts'
import { confirmDialog } from './dialog.ts'
import { confirmLeave } from './leaveGuard.ts'

export function TodoOwnership({
  base,
  todo,
  onSaved,
}: {
  base: string
  todo: Todo
  onSaved: () => void
}) {
  const [owner, setOwner] = useState(String(todo.owner ?? ''))
  const [error, setError] = useState<string | null>(null)
  return (
    <div className="card">
      <SelectField
        label={t('Verantwortliches Konto')}
        value={owner}
        onChange={(event) => setOwner(event.target.value)}
      >
        {(todo.owners ?? []).map((user) => (
          <option key={user.id} value={user.id}>
            {user.name}
          </option>
        ))}
      </SelectField>
      <button
        className="button"
        disabled={!owner || Number(owner) === todo.owner}
        onClick={() => {
          void (async () => {
            if (!(await confirmLeave())) return
            if (
              todo.series &&
              !(await confirmDialog({
                title: t('Verantwortung für die Serie übertragen?'),
                message: t(
                  'Die Übertragung umfasst alle geteilten Ausgaben und die künftige Fortsetzung. Private frühere Ausgaben müssen zuerst ausdrücklich geprüft werden.',
                ),
              }))
            )
              return
            try {
              const current = await todoApi.get(base, todo.id)
              await todoApi.update(base, todo.id, {
                owner: Number(owner),
                version: current.version,
              })
              onSaved()
            } catch (err) {
              setError(errorMessage(err))
            }
          })()
        }}
      >
        {t('Verantwortung übertragen')}
      </button>
      {error && <p role="alert">{error}</p>}
    </div>
  )
}
