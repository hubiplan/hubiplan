import { Link } from 'react-router-dom'
import { historyApi } from '../../api/competitionHistory.ts'
import { PERM } from '../../api/orgs.ts'
import { useLoad } from '../../components/forms.ts'
import { Alert, LoadError } from '../../components/ui.tsx'
import { t, tn } from '../../i18n/index.ts'
import { PageHeader } from '../../components/PageHeader.tsx'
import { useActiveOrg } from '../../org/OrgContext.tsx'
import { TitlesList } from './TitlesList.tsx'

export function TitlesPage() {
  const org = useActiveOrg()
  const canManage = org.permissions.includes(PERM.competitionsManage)
  const { data, error, reload } = useLoad(() => historyApi.grants.list(org.id), [org.id])
  const proposals = (data ?? []).filter((g) => g.dignity_state === 'vorschlag')
  return (
    <section>
      <PageHeader name={t('Titel und Sieger')} />
      <p className="muted">
        {t('Alles, was in Wettbewerben vergeben wurde, und von Hand nachgetragene frühere Jahre.')}{' '}
        {t('Könige und andere Würden früherer Jahre:')}{' '}
        <Link to="/mitglieder/wuerdentraeger">{t('Mitglieder › Würdenträger')}</Link>
      </p>
      {error && <LoadError message={error} onRetry={reload} />}
      {proposals.length > 0 && (
        <Alert kind="info">
          {tn(
            '{n} Würdenvorschlag wartet auf eure Entscheidung (beim Wettbewerb unter „Auswertung“).',
            '{n} Würdenvorschläge warten auf eure Entscheidung (beim Wettbewerb unter „Auswertung“).',
            proposals.length,
          )}
        </Alert>
      )}
      {data && <TitlesList org={org.id} grants={data} canManage={canManage} onChanged={reload} />}
    </section>
  )
}
