import { Link } from 'react-router-dom'
import { todoApi, todoBase } from '../api/todos.ts'
import { useLoad } from './forms.ts'
import { LoadError } from './ui.tsx'
import { t } from '../i18n/index.ts'

export function DepartmentTodosTile({ department }: { department: number }) {
  const { data, error, reload } = useLoad(
    () => todoApi.list(todoBase(null, department)),
    [department],
  )
  const open = (data?.items ?? []).filter((item) => item.status === 'open')
  return (
    <div className="card tile">
      <h2>
        {t('Offene Aufgaben')} <span className="badge">{open.length}</span>
      </h2>
      {error && <LoadError message={error} onRetry={reload} />}
      <Link to="/aufgaben">{t('Alle Aufgaben')}</Link>
      <ul className="plain-list">
        {open.slice(0, 5).map((item) => (
          <li key={item.id}>
            <Link to={`/aufgaben?aufgabe=${item.id}`}>{item.title}</Link>
          </li>
        ))}
      </ul>
    </div>
  )
}
