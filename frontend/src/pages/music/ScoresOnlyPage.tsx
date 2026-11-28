import { useActiveOrg } from '../../org/OrgContext.tsx'
import { ScoresPage } from './ScoresPage.tsx'
import { MusicLayout } from './MusicLayout.tsx'
import { NoAccessPage } from '../NoticePages.tsx'

/** Menüpunkt „Noten“ (Modul Notenarchiv ohne Musik), Adresse /noten */
export function ScoresOnlyPage() {
  const org = useActiveOrg()
  if (!org.modules.includes('scores') || !org.permissions.includes('scores.view'))
    return <NoAccessPage reason="right" />
  return (
    <MusicLayout>
      <ScoresPage key={org.id} />
    </MusicLayout>
  )
}
