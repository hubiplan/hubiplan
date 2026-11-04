import { useCallback, useMemo, useRef, useState } from 'react'
import { Modal } from './Modal.tsx'
import { TodoEditor } from './TodoEditor.tsx'
import { TodoSharing } from './TodoSharing.tsx'
import { TodoSeries } from './TodoSeries.tsx'
import { TodoReminders } from './TodoReminders.tsx'
import { TodoAttachments } from './TodoAttachments.tsx'
import { TodoEventLink } from './TodoEventLink.tsx'
import { TodoPortal } from './TodoPortal.tsx'
import { todoApi } from '../api/todos.ts'
import type { Todo, TodoShare } from '../api/todos.ts'
import { useOrg } from '../org/OrgContext.tsx'
import { confirmLeave } from './leaveGuard.ts'
import { errorMessage } from './forms.ts'
import { t } from '../i18n/index.ts'

export function NewTodoDialog({
  base,
  initialEvent,
  onClose,
  onSaved,
}: {
  base: string
  initialEvent?: number
  onClose: () => void
  onSaved: () => void
}) {
  const { active, activeDept } = useOrg()
  const canShare = (active?.permissions ?? activeDept?.permissions ?? []).includes('todos.edit')
  const [task, setTask] = useState<Todo | null>(null)
  const [shares, setShares] = useState<TodoShare[]>([])
  const [perUnit, setPerUnit] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const generation = useRef(0)
  const draft = useMemo<Todo>(
    () => ({
      id: 0,
      organization: active?.id ?? activeDept?.club_id,
      department: activeDept?.id ?? null,
      title: '',
      description: '',
      due_date: null,
      due_time: null,
      timezone: 'Europe/Berlin',
      status: 'open',
      shared: false,
      created_by: null,
      owner: null,
      version: 1,
      created_at: '',
      updated_at: '',
      deleted_at: null,
      can_edit: true,
      can_delete: true,
      shares: [],
    }),
    [active?.id, activeDept?.club_id, activeDept?.id],
  )
  const sharing = useCallback((values: TodoShare[], mode: boolean) => {
    setShares(values)
    setPerUnit(mode)
  }, [])
  const foreign = shares.some(
    (entry) =>
      (entry.target_org ?? draft.organization) !== draft.organization ||
      (entry.target_department ?? null) !== (draft.department ?? null),
  )
  async function refresh() {
    if (!task) return
    const current = ++generation.current
    try {
      const updated = await todoApi.get(base, task.id)
      if (current === generation.current) setTask(updated)
      onSaved()
    } catch (err) {
      setError(errorMessage(err))
    }
  }
  return (
    <Modal
      title={task ? t('Aufgabe angelegt') : t('Neue Aufgabe')}
      onClose={onClose}
      beforeClose={confirmLeave}
    >
      <div className="todo-workspace todo-dialog stack">
        {error && <p role="alert">{error}</p>}
        <TodoEditor
          key={task?.id ?? 'draft'}
          base={base}
          todo={task ?? undefined}
          initialEvent={initialEvent}
          extraValues={canShare ? { shares, ...(foreign ? { per_unit: perUnit } : {}) } : undefined}
          onCreated={setTask}
          onSaved={() => {
            if (task) void refresh()
            else onSaved()
          }}
        />
        {canShare && (
          <TodoSharing
            key={task?.id ?? 'draft'}
            base={base}
            todo={task ?? draft}
            onSaved={() => void refresh()}
            onDraftChange={task ? undefined : sharing}
          />
        )}
        {task ? (
          <>
            <TodoEventLink base={base} todo={task} onSaved={() => void refresh()} />
            {(task.due_date || task.series) && (
              <TodoSeries base={base} todo={task} trash={false} onSaved={() => void refresh()} />
            )}
            {task.due_date && <TodoReminders base={base} id={task.id} />}
            <TodoAttachments
              base={base}
              id={task.id}
              writable={task.can_edit}
              recurring={!!task.series}
              onSaved={() => void refresh()}
            />
            {canShare && !task.per_unit && (
              <TodoPortal base={base} todo={task} onSaved={() => void refresh()} />
            )}
            <div className="button-row">
              <button
                className="button button-primary"
                onClick={async () => {
                  if (await confirmLeave()) onClose()
                }}
              >
                {t('Fertig')}
              </button>
            </div>
          </>
        ) : (
          <p className="muted">
            {t(
              'Nach dem Anlegen kannst du Anhänge, Erinnerungen und Wiederholung direkt in diesem Dialog ergänzen.',
            )}
          </p>
        )}
      </div>
    </Modal>
  )
}
