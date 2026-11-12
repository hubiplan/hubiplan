// Mitglieder: Liste, Entwicklung, Jubiläen, Anfragen, Import und Einrichtung.
// Unterpunkte stehen in der Seitenleiste (siehe members/access.ts), innerhalb
// eines Unterpunkts führen Reiter weiter.
import type { ReactNode } from 'react'
import { Navigate, Route, Routes, useLocation } from 'react-router-dom'
import { PERM } from '../api/orgs.ts'
import { Tabs } from '../components/ui.tsx'
import { PageHeader } from '../components/PageHeader.tsx'
import { useActiveOrg } from '../org/OrgContext.tsx'
import { FieldsPage } from './settings/FieldsPage.tsx'
import { MemberTypesPage } from './settings/MemberTypesPage.tsx'
import { ownMembers, requestTabs, setupTabs } from './members/access.ts'
import type { NavItem } from './members/access.ts'
import { AdmitPage } from './members/AdmitPage.tsx'
import { ApplicationsPage } from './members/ApplicationsPage.tsx'
import { ApplicationSettings } from './members/ApplicationSettings.tsx'
import { HonoraryTitlesPage } from './members/HonoraryTitlesPage.tsx'
import { HouseholdsPage } from './members/HouseholdsPage.tsx'
import { MemberFilePage } from './members/MemberFilePage.tsx'
import { MemberListPage } from './members/MemberListPage.tsx'
import { MemberPortalSettings, MemberDurationSettings } from './members/SetupPages.tsx'
import { TransfersPage } from './members/TransfersPage.tsx'
import { JubileesPage } from './members/JubileesPage.tsx'
import { ImportPage } from './members/ImportPage.tsx'
import { FederationMembersPage } from './members/FederationMembersPage.tsx'
import { ChangeRequestsPage } from './members/ChangeRequestsPage.tsx'
import { CancellationsPage } from './members/CancellationsPage.tsx'
import { ChroniclePage } from './members/ChroniclePage.tsx'
import { OfficesPage } from './members/OfficesPage.tsx'
import { MembersDevelopmentPage } from './members/DevelopmentPage.tsx'
import { MovedCirculars } from './circulars/CircularsPage.tsx'
import { t } from '../i18n/index.ts'

/** Rahmen eines Mitglieder-Bereichs: Seitenkopf mit h1 und Pfad aus dem Menü (S-05). */
export function MembersSection({
  tabs,
  children,
}: {
  /** Name des Bereichs (nur noch zur Lesbarkeit; h1 und Pfad kommen aus dem Menü) */
  title: string
  tabs?: NavItem[]
  children: ReactNode
}) {
  return (
    <section>
      <PageHeader />
      {tabs && tabs.length > 1 && <Tabs items={tabs} />}
      {children}
    </section>
  )
}

/** Alte Adressen (/mitglieder/wechsel, /mitglieder/aenderungen) samt Filtern weiterleiten. */
function Moved({ to }: { to: string }) {
  const { search } = useLocation()
  return <Navigate to={`${to}${search}`} replace />
}

export function MembersPage() {
  const org = useActiveOrg()
  if (org.type !== 'club' && org.type !== 'federation') return <Navigate to="/" replace />
  return (
    <Routes>
      <Route path="rundschreiben/*" element={<MovedCirculars />} />
      <Route path="einrichtung/*" element={<SetupArea />} />
      {ownMembers(org) && (
        <Route path="verbund/*" element={<FederationMembersPage prefix="/mitglieder/verbund" />} />
      )}
      <Route
        path="*"
        element={
          org.type === 'federation' && !ownMembers(org) ? (
            <FederationMembersPage />
          ) : (
            <ClubMembers />
          )
        }
      />
    </Routes>
  )
}

function ClubMembers() {
  const org = useActiveOrg()
  const canEdit = org.permissions.includes(PERM.membersEdit)
  const list = <Navigate to="/mitglieder" replace />
  return (
    <Routes>
      <Route index element={<MemberListPage />} />
      <Route path="neu" element={canEdit ? <AdmitPage /> : list} />
      {org.type === 'club' && <Route path="antraege/*" element={<ApplicationsPage />} />}
      {org.type === 'club' && (
        <Route
          path="haushalte"
          element={
            <MembersSection title={t('Haushalte und Firmen')}>
              <HouseholdsPage />
            </MembersSection>
          }
        />
      )}
      <Route
        path="anfragen"
        element={
          <MembersSection title={t('Wechselanfragen')} tabs={requestTabs()}>
            <TransfersPage />
          </MembersSection>
        }
      />
      <Route
        path="anfragen/aenderungen"
        element={
          <MembersSection title={t('Datenänderungen')} tabs={requestTabs()}>
            <ChangeRequestsPage />
          </MembersSection>
        }
      />
      <Route
        path="anfragen/kuendigungen"
        element={
          <MembersSection title={t('Kündigungen')} tabs={requestTabs()}>
            <CancellationsPage />
          </MembersSection>
        }
      />
      <Route path="wechsel" element={<Moved to="/mitglieder/anfragen" />} />
      <Route path="aenderungen" element={<Moved to="/mitglieder/anfragen/aenderungen" />} />
      <Route
        path="jubilaeen"
        element={
          org.modules.includes('awards') ? (
            <MembersSection title={t('Jubiläen')}>
              <JubileesPage />
            </MembersSection>
          ) : (
            list
          )
        }
      />
      <Route path="entwicklung" element={<MembersDevelopmentPage />} />
      <Route
        path="wuerdentraeger/*"
        element={org.modules.includes('honors') ? <ChroniclePage /> : list}
      />
      <Route path="aemter/*" element={<OfficesPage />} />
      <Route path="chronik" element={<Moved to="/mitglieder/wuerdentraeger" />} />
      <Route path="chronik/wuerden" element={<Moved to="/mitglieder/wuerdentraeger/wuerden" />} />
      <Route path="chronik/import" element={<Moved to="/mitglieder/wuerdentraeger/import" />} />
      <Route
        path="import"
        element={
          canEdit ? (
            <MembersSection title={t('Mitglieder importieren')}>
              <ImportPage />
            </MembersSection>
          ) : (
            list
          )
        }
      />
      <Route path=":id" element={<MemberFilePage />} />
    </Routes>
  )
}

function SetupArea() {
  const org = useActiveOrg()
  const tabs = setupTabs(org)
  const club = org.type === 'club'
  const types = club || ownMembers(org)
  const awards = org.modules.includes('awards')
  const page = (title: string, body: ReactNode) => (
    <MembersSection title={title} tabs={tabs}>
      {body}
    </MembersSection>
  )
  return (
    <Routes>
      <Route index element={<Navigate to={tabs[0].to} replace />} />
      {types && (
        <Route path="mitgliedsarten" element={page(t('Einrichtung'), <MemberTypesPage />)} />
      )}
      {awards && <Route path="ehrungen" element={page(t('Einrichtung'), <HonoraryTitlesPage />)} />}
      {/* frühere Adresse (Lesezeichen) */}
      <Route
        path="ehrentitel"
        element={<Navigate to="/mitglieder/einrichtung/ehrungen" replace />}
      />
      <Route path="zusatzfelder" element={page(t('Einrichtung'), <FieldsPage />)} />
      {club && <Route path="antrag" element={page(t('Einrichtung'), <ApplicationSettings />)} />}
      {awards && (
        <Route path="jubilaeen" element={page(t('Einrichtung'), <MemberDurationSettings />)} />
      )}
      {club && (
        <Route
          path="mitgliederbereich"
          element={page(t('Einrichtung'), <MemberPortalSettings />)}
        />
      )}
      <Route path="*" element={<Navigate to={tabs[0].to} replace />} />
    </Routes>
  )
}
