import { useState } from 'react'
import { todoApi } from '../api/todos.ts'
import type { Todo } from '../api/todos.ts'
import { errorMessage } from './forms.ts'
import { SelectField } from './ui.tsx'
import { t } from '../i18n/index.ts'

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
          void todoApi
            .update(base, todo.id, { owner: Number(owner), version: todo.version })
            .then(onSaved)
            .catch((err: unknown) => setError(errorMessage(err)))
        }}
      >
        {t('Verantwortung übertragen')}
      </button>
      {error && <p role="alert">{error}</p>}
    </div>
  )
}
