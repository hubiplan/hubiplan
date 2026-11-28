import { platformApi } from '../../api/orgs.ts'
import { LoadError } from '../../components/ui.tsx'
import { useLoad } from '../../components/forms.ts'
import { ExportSection } from '../../components/ExportSection.tsx'
import { ImportSection } from '../../components/ImportSection.tsx'
import { t } from '../../i18n/index.ts'

export function PlatformTransferPage() {
  const { data, error, reload } = useLoad(() => platformApi.orgs(), [])
  return (
    <>
      {error && (
        <LoadError
          message={t('Die Einheiten zur Auswahl konnten nicht geladen werden: {error}', { error })}
          onRetry={() => void reload()}
        />
      )}
      <ExportSection base={{ platform: true }} organizations={data ?? []} />
      <ImportSection base={{ platform: true }} target="platform" onImported={() => void reload()} />
    </>
  )
}
