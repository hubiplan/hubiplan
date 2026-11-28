import { useState } from 'react'
import type { FormEvent } from 'react'
import { Link } from 'react-router-dom'
import { historyApi, type Series } from '../../api/competitionHistory.ts'
import { PERM } from '../../api/orgs.ts'
import { errorMessage, useLoad } from '../../components/forms.ts'
import { Alert, Field, LoadError } from '../../components/ui.tsx'
import { t, tn } from '../../i18n/index.ts'
import { PageHeader } from '../../components/PageHeader.tsx'
import { useActiveOrg } from '../../org/OrgContext.tsx'

export function SeriesListPage() {
  const org = useActiveOrg()
  const canManage = org.permissions.includes(PERM.competitionsManage)
  const { data, error, reload } = useLoad(() => historyApi.series.list(org.id), [org.id])
  const [name, setName] = useState('')
  const [message, setMessage] = useState<string | null>(null)

  async function add(e: FormEvent) {
    e.preventDefault()
    try {
      await historyApi.series.create(org.id, { name })
      setName('')
      reload()
    } catch (err) {
      setMessage(errorMessage(err))
    }
  }

  return (
    <section>
      <PageHeader name={t('Reihen')} />
      <p className="muted">
        {t(
          'Eine Reihe verbindet denselben Wettbewerb über die Jahre, z. B. „Vereinsmeisterschaft“: Sieger je Jahr, Titel, Bestenliste und eure Untereinheiten im Vergleich.',
        )}
      </p>
      {error && <LoadError message={error} onRetry={reload} />}
      {data && data.length === 0 && <p className="muted">{t('Noch keine Reihen.')}</p>}
      {data && data.length > 0 && (
        <ul className="plain-list">
          {data.map((s: Series) => (
            <li key={s.id}>
              <Link to={`/wettbewerbe/reihen/${s.id}`}>{s.name}</Link>{' '}
              <span className="muted">
                · {tn('{n} Wettbewerb', '{n} Wettbewerbe', s.competition_count)}
              </span>
            </li>
          ))}
        </ul>
      )}
      {canManage && (
        <form onSubmit={add} className="card">
          <Field
            label={t('Neue Reihe')}
            placeholder={t('z. B. Vereinsmeisterschaft')}
            value={name}
            required
            onChange={(e) => setName(e.target.value)}
          />
          {message && <Alert kind="error">{message}</Alert>}
          <div className="button-row">
            <button type="submit" className="button">
              {t('Anlegen')}
            </button>
          </div>
        </form>
      )}
    </section>
  )
}
