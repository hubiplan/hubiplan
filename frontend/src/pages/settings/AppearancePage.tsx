import { orgApi } from '../../api/orgs.ts'
import { LoadError, Loading } from '../../components/ui.tsx'
import { useLoad } from '../../components/forms.ts'
import { useActiveOrg } from '../../org/OrgContext.tsx'
import { ThemeForm } from './ThemeForm.tsx'

export function AppearancePage() {
  const org = useActiveOrg()
  const { data, error, setData, reload } = useLoad(() => orgApi.theme(org.id), [org.id])
  if (error) return <LoadError message={error} onRetry={() => void reload()} />
  if (!data) return <Loading />
  return (
    <ThemeForm
      key={org.id}
      orgId={org.id}
      isPlatform={org.type === 'platform'}
      theme={data}
      onSaved={setData}
      reload={reload}
    />
  )
}
