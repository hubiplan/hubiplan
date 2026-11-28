import { EngagementPage } from './EngagementPage.tsx'
import { Navigate, useLocation, useSearchParams } from 'react-router-dom'
import { useActiveOrg } from '../../org/OrgContext.tsx'
import { ScoresPage } from './ScoresPage.tsx'
import { ProgramPanel } from './ProgramPanel.tsx'
import { PracticePage } from './PracticePage.tsx'
import { EnsembleTemplatesPage } from './EnsembleTemplatesPage.tsx'
import { StaffingPage } from './StaffingPage.tsx'
import { AvailabilityPage } from './AvailabilityPage.tsx'
import { PerformanceOverview } from './PerformanceOverview.tsx'
import { NoAccessPage } from '../NoticePages.tsx'
import { UniformsKindsPage } from './UniformsKindsPage.tsx'
import { InstrumentsPage } from './InstrumentsPage.tsx'
import { musicArea } from './musicHelpers.ts'
import { MusicWorkspace } from './MusicWorkspace.tsx'

/** Frühere Adressen /musik/noten … → /musik/noten (Menüprüfung M-08) */
const OLD_AREAS: Record<string, string> = {
  uebersicht: 'uebersicht',
  noten: 'noten',
  proben: 'proben',
  verfuegbarkeit: 'verfuegbarkeit',
  vorlagen: 'vorlagen',
  erinnerungen: 'erinnerungen',
  auszahlungen: 'auszahlungen',
  ausstattung: 'ausstattung',
}

const MOVED: Record<string, string> = {
  erinnerungen: '/aufgaben/erinnerungen',
  ausstattung: '/material/musik',
  auszahlungen: '/finanzen/sammelauszahlungen',
}

export function MusicRoute() {
  const org = useActiveOrg()
  const [params] = useSearchParams()
  const { pathname } = useLocation()
  const old = Object.keys(OLD_AREAS).find((k) => params.get(k))
  if (old) {
    const rest = new URLSearchParams(params)
    rest.delete(old)
    const query = rest.toString()
    return <Navigate to={`/musik/${OLD_AREAS[old]}${query ? `?${query}` : ''}`} replace />
  }
  const area = musicArea(pathname)
  // Umgezogen (Menüprüfung 2, N-05); Abfragen wie ?ausleihe= bleiben erhalten
  const moved = MOVED[area]
  if (moved) {
    const query = params.toString()
    return <Navigate to={`${moved}${query ? `?${query}` : ''}`} replace />
  }
  if (/^\d+$/.test(params.get('vereinbarung') || ''))
    return (
      <EngagementPage
        key={`${org.id}-${params.get('vereinbarung')}`}
        performance={Number(params.get('vereinbarung'))}
      />
    )
  if (area === 'uebersicht') return <PerformanceOverview key={org.id} />
  if (area === 'noten')
    return org.modules.includes('scores') && org.permissions.includes('scores.view') ? (
      <ScoresPage key={org.id} />
    ) : (
      <NoAccessPage reason="right" embedded />
    )
  if (area === 'proben') return <PracticePage key={org.id} />
  if (area === 'vorlagen') return <EnsembleTemplatesPage key={org.id} />
  if (area === 'uniformen') return <UniformsKindsPage key={org.id} />
  if (area === 'instrumente') return <InstrumentsPage key={org.id} />
  if (area === 'verfuegbarkeit') return <AvailabilityPage key={org.id} />
  if (/^\d+$/.test(params.get('besetzung') || ''))
    return (
      <StaffingPage
        key={`${org.id}-${params.get('besetzung')}`}
        performance={Number(params.get('besetzung'))}
      />
    )
  if (/^\d+$/.test(params.get('programm') || ''))
    return (
      <ProgramPanel
        key={`${org.id}-${params.get('programm')}`}
        performance={Number(params.get('programm'))}
      />
    )
  if (area !== '' && area !== 'musiker') return <Navigate to="/musik" replace />
  return <MusicWorkspace key={org.id} />
}
