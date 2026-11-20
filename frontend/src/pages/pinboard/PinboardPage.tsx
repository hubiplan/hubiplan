// Pinnwand in der Verwaltung (Verein und Untereinheit): kurze Beiträge an die Mitglieder.
import { PERM } from '../../api/orgs.ts'
import { pinboardApi } from '../../api/pinboard.ts'
import { PageHeader } from '../../components/PageHeader.tsx'
import { useLoad } from '../../components/forms.ts'
import { LoadError, Loading } from '../../components/ui.tsx'
import { t } from '../../i18n/index.ts'
import { useOrg } from '../../org/OrgContext.tsx'
import { NoAccessPage } from '../NoticePages.tsx'
import { PinboardList } from './Pinboard.tsx'

export function PinboardPage() {
  const { active, activeDept } = useOrg()
  const permissions = active?.permissions ?? activeDept?.permissions ?? []
  const enabled = active ? active.modules.includes('pinboard') : !!activeDept?.pinboard_enabled
  if (
    !enabled ||
    !(permissions.includes(PERM.pinboardView) || permissions.includes(PERM.pinboardEdit))
  ) {
    return <NoAccessPage reason="right" />
  }
  const base = active
    ? `/api/orgs/${active.id}/pinboard/`
    : `/api/depts/${activeDept!.id}/pinboard/`
  return <Pinboard key={base} base={base} />
}

function Pinboard({ base }: { base: string }) {
  const { data, error, reload } = useLoad(() => pinboardApi.list(base), [base])
  return (
    <div className="stack">
      <PageHeader
        subtitle={t(
          'Kurze Neuigkeiten für die Mitglieder im Mitgliederbereich und in der App, etwa „Der Bus fährt 10 Minuten später“ oder Bilder vom Fest. Kein Chat: Mitglieder lesen nur.',
        )}
      />
      {error ? (
        <LoadError message={error} onRetry={reload} />
      ) : !data ? (
        <Loading />
      ) : (
        <PinboardList
          base={base}
          list={data}
          writable={!!data.can_edit}
          showUnit={false}
          reload={reload}
          emptyText={t('Neue Beiträge erscheinen hier und bei den Mitgliedern.')}
        />
      )}
    </div>
  )
}
