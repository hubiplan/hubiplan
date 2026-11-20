// Pinnwand im Mitgliederbereich: Neuigkeiten des Vereins und der eigenen Untereinheiten.
// Wer in der Verwaltung schreiben darf, schreibt auch hier.
import { pinboardApi, portalPinboardBase } from '../../api/pinboard.ts'
import { useLoad } from '../../components/forms.ts'
import { LoadError, Loading } from '../../components/ui.tsx'
import { t } from '../../i18n/index.ts'
import { PinboardList } from '../pinboard/Pinboard.tsx'

export function PortalPinboard({ accessId }: { accessId: number }) {
  const base = portalPinboardBase(accessId)
  const { data, error, reload } = useLoad(() => pinboardApi.list(base), [base])
  if (error) return <LoadError message={error} onRetry={reload} />
  if (!data) return <Loading />
  return (
    <PinboardList
      base={base}
      list={data}
      writable={!!data.targets?.length}
      reload={reload}
      emptyText={t('Hier erscheinen kurze Neuigkeiten deines Vereins und deiner Untereinheiten.')}
    />
  )
}
