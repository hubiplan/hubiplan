import { useActiveOrg } from '../../org/OrgContext.tsx'
import { MusicLayout } from './MusicLayout.tsx'
import { NoAccessPage } from '../NoticePages.tsx'
import { MusicRoute } from './MusicRoute.tsx'

export function MusicPage() {
  const org = useActiveOrg()
  if (!org.modules.includes('music') || !org.permissions.includes('music.view'))
    return <NoAccessPage reason="right" />
  return (
    <MusicLayout>
      <MusicRoute />
    </MusicLayout>
  )
}
