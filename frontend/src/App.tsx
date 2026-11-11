import type { ReactNode } from 'react'
import { Navigate, Route, Routes, useLocation, useParams } from 'react-router-dom'
import { PERM } from './api/orgs.ts'
import { RequireAuth, RequireAuthOrOffline } from './auth/RequireAuth.tsx'
import { Layout } from './components/Layout.tsx'
import { PublicShell } from './components/ImprintFooter.tsx'
import { AccessibilityPage, ImprintPage, LicensePage, PrivacyPage } from './pages/ImprintPages.tsx'
import { useOrg } from './org/OrgContext.tsx'
import { LoginPage } from './pages/LoginPage.tsx'
import {
  VerbundConfirmPage,
  VerbundFinishPage,
  VerbundStartPage,
} from './pages/VerbundLoginPages.tsx'
import { AppPairNoticePage, NoAccessPage, NotFoundPage } from './pages/NoticePages.tsx'
import {
  EmailConfirmPage,
  LoginLinkRedeemPage,
  LoginLinkRequestPage,
} from './pages/LoginLinkPages.tsx'
import { PasswordRequestPage, PasswordResetPage } from './pages/PasswordPages.tsx'
import { PublicCardPage } from './pages/PublicCardPage.tsx'
import { PublicPhotoPage } from './pages/PublicPhotoPage.tsx'
import { PublicOptOutPage } from './pages/PublicOptOutPage.tsx'
import { PublicRsvpPage } from './pages/PublicRsvpPage.tsx'
import { PublicCircularConfirmPage } from './pages/PublicCircularConfirmPage.tsx'
import { NextcloudLoginPage } from './pages/NextcloudLoginPage.tsx'
import { lazyPage } from './lazyPages.ts'
import { NoLearningAids } from './learning/LearningContext.tsx'
import { LeaveGuard } from './components/leaveGuard.ts'
import { ColorSchemeSync } from './components/ColorSchemeSync.tsx'

const ImprintSettingsPage = lazyPage(
  () => import('./pages/settings/ImprintSettingsPage.tsx'),
  'ImprintSettingsPage',
)
const ModulesPage = lazyPage(() => import('./pages/settings/ModulesPage.tsx'), 'ModulesPage')
const SetupOverviewPage = lazyPage(
  () => import('./pages/settings/SetupOverviewPage.tsx'),
  'SetupOverviewPage',
)
const PrivacySettingsPage = lazyPage(
  () => import('./pages/settings/PrivacySettingsPage.tsx'),
  'PrivacySettingsPage',
)
const PlatformImprintPage = lazyPage(
  () => import('./pages/settings/ImprintSettingsPage.tsx'),
  'PlatformImprintPage',
)
const TodosPage = lazyPage(() => import('./pages/TodosPage.tsx'), 'TodosPage')
const MusicRemindersRoute = lazyPage(
  () => import('./pages/music/CustodyRemindersPage.tsx'),
  'MusicRemindersRoute',
)
const HomePage = lazyPage(() => import('./pages/HomePage.tsx'), 'HomePage')
const DepartmentArea = lazyPage(
  () => import('./pages/department/DepartmentArea.tsx'),
  'DepartmentArea',
)
const PortalPage = lazyPage(() => import('./pages/portal/PortalPage.tsx'), 'PortalPage')
const OutboxPage = lazyPage(() => import('./pages/settings/OutboxPage.tsx'), 'OutboxPage')
const PeeringPage = lazyPage(() => import('./pages/settings/PeeringPage.tsx'), 'PeeringPage')
const NextcloudPage = lazyPage(() => import('./pages/settings/NextcloudPage.tsx'), 'NextcloudPage')
const CircularsPage = lazyPage(() => import('./pages/circulars/CircularsPage.tsx'), 'CircularsPage')
const MembersPage = lazyPage(() => import('./pages/MembersPage.tsx'), 'MembersPage')
const FinanzenPage = lazyPage(() => import('./pages/finanzen/FinanzenPage.tsx'), 'FinanzenPage')
const MusicPage = lazyPage(() => import('./pages/music/MusicPage.tsx'), 'MusicPage')
const GuestMusicPage = lazyPage(() => import('./pages/music/GuestMusicPage.tsx'), 'GuestMusicPage')
const DocumentsPage = lazyPage(() => import('./pages/documents/DocumentsPage.tsx'), 'DocumentsPage')
const MaterialsPage = lazyPage<{ kind?: 'material' | 'facility' }>(
  () => import('./pages/materials/MaterialsPage.tsx'),
  'MaterialsPage',
)
const BookingsPage = lazyPage(() => import('./pages/bookings/BookingsPage.tsx'), 'BookingsPage')
const MeetingsPage = lazyPage(() => import('./pages/meetings/MeetingsPage.tsx'), 'MeetingsPage')
const ChronikPage = lazyPage(() => import('./pages/chronik/ChronikPage.tsx'), 'ChronikPage')
const PartnersPage = lazyPage(() => import('./pages/partners/PartnersPage.tsx'), 'PartnersPage')
const ScoresOnlyPage = lazyPage(() => import('./pages/music/MusicPage.tsx'), 'ScoresOnlyPage')
const HelpersPage = lazyPage(() => import('./pages/helpers/HelpersPage.tsx'), 'HelpersPage')
const WebsitePage = lazyPage(() => import('./pages/website/WebsitePage.tsx'), 'WebsitePage')
const EventsPage = lazyPage(() => import('./pages/events/EventsPage.tsx'), 'EventsPage')
const CompetitionsPage = lazyPage(
  () => import('./pages/competitions/CompetitionsPage.tsx'),
  'CompetitionsPage',
)
const EntriesPage = lazyPage(() => import('./pages/entries/EntriesPage.tsx'), 'EntriesPage')
const StandPage = lazyPage(() => import('./pages/competitions/StandPage.tsx'), 'StandPage')
const StandTokenPage = lazyPage(
  () => import('./pages/competitions/StandPage.tsx'),
  'StandTokenPage',
)
const PlatformLayout = lazyPage(
  () => import('./pages/platform/PlatformPages.tsx'),
  'PlatformLayout',
)
const PlatformMailPage = lazyPage(
  () => import('./pages/platform/PlatformPages.tsx'),
  'PlatformMailPage',
)
const PlatformOrgsPage = lazyPage(
  () => import('./pages/platform/PlatformPages.tsx'),
  'PlatformOrgsPage',
)
const PlatformSettingsPage = lazyPage(
  () => import('./pages/platform/PlatformPages.tsx'),
  'PlatformSettingsPage',
)
const PlatformTransferPage = lazyPage(
  () => import('./pages/platform/PlatformPages.tsx'),
  'PlatformTransferPage',
)
const PlatformVersionPage = lazyPage(
  () => import('./pages/platform/PlatformVersionPage.tsx'),
  'PlatformVersionPage',
)
const HelpPage = lazyPage<{ tab?: 'anleitungen' | 'seiten' | 'begriffe' | 'neuigkeiten' }>(
  () => import('./help/HelpPage.tsx'),
  'HelpPage',
)
const HelpEntryPage = lazyPage(() => import('./help/HelpPage.tsx'), 'HelpEntryPage')
const AccountPage = lazyPage(() => import('./pages/settings/AccountPage.tsx'), 'AccountPage')
const AccountNotificationsPage = lazyPage(
  () => import('./pages/settings/AccountPage.tsx'),
  'AccountNotificationsPage',
)
const AccountLoginPage = lazyPage(
  () => import('./pages/settings/AccountPage.tsx'),
  'AccountLoginPage',
)
const AccountAppPage = lazyPage(() => import('./pages/settings/AccountPage.tsx'), 'AccountAppPage')
const AccountTemplatesPage = lazyPage(
  () => import('./pages/settings/AccountPage.tsx'),
  'AccountTemplatesPage',
)
const LetterheadPage = lazyPage(() => import('./pages/LetterheadPage.tsx'), 'LetterheadPage')
const LetterheadSettingsPage = lazyPage(
  () => import('./pages/settings/LetterheadSettingsPage.tsx'),
  'LetterheadSettingsPage',
)
const PlacesPage = lazyPage(() => import('./pages/settings/PlacesPage.tsx'), 'PlacesPage')
const AppearancePage = lazyPage(
  () => import('./pages/settings/AppearancePage.tsx'),
  'AppearancePage',
)
const ColorSheetPage = lazyPage(
  () => import('./pages/settings/ColorSheetPage.tsx'),
  'ColorSheetPage',
)
const AuditPage = lazyPage(() => import('./pages/settings/AuditPage.tsx'), 'AuditPage')
const UnitsArea = lazyPage(() => import('./pages/settings/UnitsPage.tsx'), 'UnitsArea')
const UnitsRedirect = lazyPage(() => import('./pages/settings/UnitsPage.tsx'), 'UnitsRedirect')
const DataTransferPage = lazyPage(
  () => import('./pages/settings/DataTransferPage.tsx'),
  'DataTransferPage',
)
const OrganizationPage = lazyPage(
  () => import('./pages/settings/OrganizationPage.tsx'),
  'OrganizationPage',
)
const OrganizationTermsPage = lazyPage(
  () => import('./pages/settings/OrganizationPage.tsx'),
  'OrganizationTermsPage',
)
const OrganizationDocumentsPage = lazyPage(
  () => import('./pages/settings/OrganizationPage.tsx'),
  'OrganizationDocumentsPage',
)
const RolesPage = lazyPage(() => import('./pages/settings/RolesPage.tsx'), 'RolesPage')
const AccountsPage = lazyPage(() => import('./pages/settings/AccountsPage.tsx'), 'AccountsPage')
const SettingsLayout = lazyPage(
  () => import('./pages/settings/SettingsLayout.tsx'),
  'SettingsLayout',
)

/** Seite nur zeigen, wenn eine Organisation aktiv ist (und ggf. ein Recht vorliegt). */
function RequireOrg({
  permission,
  children,
}: {
  /** ein Recht oder mehrere (eines genügt) */
  permission?: string | string[]
  children: ReactNode
}) {
  const { active, can } = useOrg()
  if (!active) return <NoAccessPage reason="workspace" />
  const needed = typeof permission === 'string' ? [permission] : permission
  if (needed && !needed.some((p) => can(p))) return <NoAccessPage reason="right" />
  return <>{children}</>
}

function RequireDept({ children }: { children: ReactNode }) {
  const { activeDept } = useOrg()
  if (!activeDept) return <NoAccessPage reason="workspace" />
  return <>{children}</>
}

const LEGACY_KASSE: Record<string, string> = {
  '': '/finanzen',
  buchungen: '/finanzen/kassenbuch',
  konten: '/finanzen/einrichtung/konten',
  kategorien: '/finanzen/einrichtung/kategorien',
  abschluss: '/finanzen/abschluss',
}

const LEGACY_BEITRAEGE: Record<string, string> = {
  '': '/finanzen/rechnungen',
  laeufe: '/finanzen/rechnungen/beitragslaeufe',
  mahnungen: '/finanzen/rechnungen/mahnungen',
  dachverband: '/finanzen/rechnungen/dachverband',
  lastschrift: '/finanzen/lastschrift',
  regeln: '/finanzen/einrichtung',
}

/** Leitet alte Lesezeichen (/kasse/…, /beitraege/…) samt Filtern auf Finanzen um. */
function LegacyRedirect({ map }: { map: Record<string, string> }) {
  const rest = useParams()['*'] ?? ''
  const { search } = useLocation()
  const target = map[rest.replace(/\/$/, '')] ?? '/finanzen'
  return <Navigate to={`${target}${search}`} replace />
}

/** Weiterleitung, die Anker (#begriff-…) mitnimmt, etwa vom alten /glossar. */
function KeepHash({ to }: { to: string }) {
  const { hash } = useLocation()
  return <Navigate to={`${to}${hash}`} replace />
}

export default function App() {
  return (
    <>
      <LeaveGuard />
      <ColorSchemeSync />
      <Routes>
        <Route element={<PublicShell />}>
          <Route path="/musik-gast" element={<GuestMusicPage />} />
          <Route path="/anmelden" element={<LoginPage />} />
          <Route path="/anmelden/link" element={<LoginLinkRequestPage />} />
          <Route path="/anmelden/link/:token" element={<LoginLinkRedeemPage />} />
          <Route path="/konto/email/:token" element={<EmailConfirmPage />} />
          <Route path="/passwort-vergessen" element={<PasswordRequestPage />} />
          <Route path="/foto/:token" element={<PublicPhotoPage />} />
          <Route path="/app/verbinden" element={<AppPairNoticePage />} />
          <Route path="/verbund/start" element={<VerbundStartPage />} />
          <Route path="/verbund/angemeldet" element={<VerbundFinishPage />} />
          <Route
            path="/verbund/anmelden"
            element={
              <RequireAuth>
                <VerbundConfirmPage />
              </RequireAuth>
            }
          />
          <Route
            path="/oidc/anmelden"
            element={
              <RequireAuth>
                <NextcloudLoginPage />
              </RequireAuth>
            }
          />
          <Route path="/rundschreiben/abmelden/:token" element={<PublicOptOutPage />} />
          <Route path="/rueckmeldung/:token" element={<PublicRsvpPage />} />
          <Route path="/rundschreiben/bestaetigen/:token" element={<PublicCircularConfirmPage />} />
          <Route path="/ausweis/:token" element={<PublicCardPage />} />
          <Route path="/passwort-zuruecksetzen/:key" element={<PasswordResetPage />} />
          <Route path="/impressum" element={<ImprintPage />} />
          <Route path="/impressum/:key" element={<ImprintPage />} />
          <Route path="/datenschutz" element={<PrivacyPage />} />
          <Route path="/datenschutz/:key" element={<PrivacyPage />} />
          <Route path="/lizenz" element={<LicensePage />} />
          <Route path="/barrierefreiheit" element={<AccessibilityPage />} />
        </Route>
        {/* Standmodus: Vollbild ohne Menü (Tablet, Handy am Schießstand) */}
        <Route
          path="/stand/:org/:id"
          element={
            <RequireAuthOrOffline>
              <StandPage />
            </RequireAuthOrOffline>
          }
        />
        {/* Standzugang ohne Konto (Link bzw. QR-Code für ein geliehenes Gerät) */}
        <Route path="/stand/zugang/:token" element={<StandTokenPage />} />
        <Route
          element={
            <RequireAuth>
              <Layout />
            </RequireAuth>
          }
        >
          <Route index element={<HomePage />} />
          <Route
            path="mitglieder/*"
            element={
              <RequireOrg permission={PERM.membersView}>
                <MembersPage />
              </RequireOrg>
            }
          />
          <Route
            path="finanzen/*"
            element={
              <RequireOrg>
                <FinanzenPage />
              </RequireOrg>
            }
          />
          {/* alte Adressen von Kasse und Beiträge */}
          <Route path="kasse/*" element={<LegacyRedirect map={LEGACY_KASSE} />} />
          <Route path="beitraege/*" element={<LegacyRedirect map={LEGACY_BEITRAEGE} />} />
          <Route
            path="abteilung/*"
            element={
              <RequireDept>
                <DepartmentArea />
              </RequireDept>
            }
          />
          <Route path="rundschreiben/*" element={<CircularsPage />} />
          <Route path="aufgaben" element={<TodosPage />} />
          <Route path="aufgaben/erinnerungen" element={<MusicRemindersRoute />} />
          <Route path="material/*" element={<MaterialsPage />} />
          <Route path="infrastruktur/*" element={<MaterialsPage kind="facility" />} />
          <Route path="belegung" element={<BookingsPage />} />
          <Route path="versammlungen" element={<MeetingsPage />} />
          <Route path="chronik" element={<ChronikPage />} />
          <Route
            path="geschaeftspartner"
            element={
              <RequireOrg permission={[PERM.partnersView, PERM.financeView, PERM.billingView]}>
                <PartnersPage />
              </RequireOrg>
            }
          />
          <Route path="noten" element={<ScoresOnlyPage />} />
          <Route path="helferdienste" element={<HelpersPage />} />
          <Route path="termine/*" element={<EventsPage />} />
          <Route
            path="musik/*"
            element={
              <RequireOrg>
                <MusicPage />
              </RequireOrg>
            }
          />
          <Route
            path="wettbewerbe/*"
            element={
              <RequireOrg>
                <CompetitionsPage />
              </RequireOrg>
            }
          />
          <Route
            path="meldungen/*"
            element={
              <RequireOrg>
                <EntriesPage />
              </RequireOrg>
            }
          />
          <Route path="dokumente/*" element={<DocumentsPage />} />
          {/* Rückkehr von Meta: außerhalb von /webseite/, das Caddy an die Vereinswebseite gibt */}
          <Route path="social-rueckkehr" element={<SocialReturn />} />
          <Route
            path="webseite/*"
            element={
              <RequireOrg>
                <WebsitePage />
              </RequireOrg>
            }
          />
          <Route
            path="mein-bereich/*"
            element={
              <NoLearningAids>
                <PortalPage />
              </NoLearningAids>
            }
          />
          <Route path="mein-konto" element={<AccountPage />} />
          <Route path="mein-konto/benachrichtigungen" element={<AccountNotificationsPage />} />
          <Route path="mein-konto/anmeldung" element={<AccountLoginPage />} />
          <Route path="mein-konto/app" element={<AccountAppPage />} />
          <Route path="mein-konto/briefvorlage" element={<AccountTemplatesPage />} />
          <Route path="briefvorlage" element={<LetterheadPage />} />
          {/* Glossar und „Was ist neu“ stehen jetzt als Reiter in der Hilfe; alte Adressen leiten weiter */}
          <Route path="glossar" element={<KeepHash to="/hilfe/begriffe" />} />
          <Route path="hilfe/was-ist-neu" element={<Navigate to="/hilfe/neuigkeiten" replace />} />
          <Route path="hilfe" element={<HelpPage />} />
          <Route path="hilfe/anleitungen" element={<HelpPage tab="anleitungen" />} />
          <Route path="hilfe/seiten" element={<HelpPage tab="seiten" />} />
          <Route path="hilfe/begriffe" element={<HelpPage tab="begriffe" />} />
          <Route path="hilfe/neuigkeiten" element={<HelpPage tab="neuigkeiten" />} />
          <Route path="hilfe/*" element={<HelpEntryPage />} />
          <Route
            path="untereinheiten"
            element={
              <RequireOrg>
                <UnitsArea />
              </RequireOrg>
            }
          />
          {/* alte Adresse von „Mein Konto“ */}
          <Route path="einstellungen/konto" element={<Navigate to="/mein-konto" replace />} />
          <Route path="einstellungen" element={<SettingsLayout />}>
            <Route
              path="einrichtung"
              element={
                <RequireOrg>
                  <SetupOverviewPage />
                </RequireOrg>
              }
            />
            <Route
              path="organisation"
              element={
                <RequireOrg>
                  <OrganizationPage />
                </RequireOrg>
              }
            />
            <Route
              path="bezeichnungen"
              element={
                <RequireOrg>
                  <OrganizationTermsPage />
                </RequireOrg>
              }
            />
            <Route
              path="vereinsdokumente"
              element={
                <RequireOrg>
                  <OrganizationDocumentsPage />
                </RequireOrg>
              }
            />
            <Route
              path="module"
              element={
                <RequireOrg>
                  <ModulesPage />
                </RequireOrg>
              }
            />
            <Route
              path="impressum"
              element={
                <RequireOrg>
                  <ImprintSettingsPage />
                </RequireOrg>
              }
            />
            <Route
              path="datenschutz"
              element={
                <RequireOrg>
                  <PrivacySettingsPage />
                </RequireOrg>
              }
            />
            <Route
              path="briefbogen"
              element={
                <RequireOrg>
                  <LetterheadSettingsPage />
                </RequireOrg>
              }
            />
            <Route
              path="orte"
              element={
                <RequireOrg>
                  <PlacesPage />
                </RequireOrg>
              }
            />
            {/* Untereinheiten stehen jetzt im Hauptmenü; frühere Adressen */}
            <Route path="untereinheiten" element={<UnitsRedirect />} />
            <Route path="abteilungen" element={<UnitsRedirect />} />
            <Route path="vereine" element={<UnitsRedirect />} />
            {/* Mitgliedsarten und Zusatzfelder stehen unter Mitglieder › Einrichtung */}
            <Route
              path="zusatzfelder"
              element={<Navigate to="/mitglieder/einrichtung/zusatzfelder" replace />}
            />
            <Route
              path="mitgliedsarten"
              element={<Navigate to="/mitglieder/einrichtung/mitgliedsarten" replace />}
            />
            <Route
              path="rollen"
              element={
                <RequireOrg permission={[PERM.rolesView, PERM.rolesManage]}>
                  <RolesPage />
                </RequireOrg>
              }
            />
            <Route
              path="konten"
              element={
                <RequireOrg permission={[PERM.rolesView, PERM.loginsView]}>
                  <AccountsPage />
                </RequireOrg>
              }
            />
            <Route
              path="erscheinungsbild"
              element={
                <RequireOrg>
                  <AppearancePage />
                </RequireOrg>
              }
            />
            <Route
              path="erscheinungsbild/farbblatt"
              element={
                <RequireOrg>
                  <ColorSheetPage />
                </RequireOrg>
              }
            />
            <Route
              path="protokoll"
              element={
                <RequireOrg permission={PERM.auditView}>
                  <AuditPage />
                </RequireOrg>
              }
            />
            <Route
              path="postausgang"
              element={
                <RequireOrg permission={PERM.auditView}>
                  <OutboxPage />
                </RequireOrg>
              }
            />
            <Route
              path="verbund"
              element={
                <RequireOrg permission={PERM.peeringManage}>
                  <PeeringPage />
                </RequireOrg>
              }
            />
            <Route
              path="nextcloud"
              element={
                <RequireOrg permission={PERM.rolesManage}>
                  <NextcloudPage />
                </RequireOrg>
              }
            />
            <Route
              path="datenuebernahme"
              element={
                <RequireOrg>
                  <DataTransferPage />
                </RequireOrg>
              }
            />
          </Route>
          <Route
            path="plattform"
            element={
              <RequireOrg permission={PERM.platformManage}>
                <PlatformLayout />
              </RequireOrg>
            }
          >
            <Route path="organisationen" element={<PlatformOrgsPage />} />
            <Route path="einstellungen" element={<PlatformSettingsPage />} />
            <Route path="impressum" element={<PlatformImprintPage />} />
            <Route path="postfach" element={<PlatformMailPage />} />
            <Route path="datenuebernahme" element={<PlatformTransferPage />} />
            <Route path="version" element={<PlatformVersionPage />} />
          </Route>
          <Route path="*" element={<NotFoundPage />} />
        </Route>
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </>
  )
}

/** Rückkehr nach dem Verbinden mit Meta: weiter zur Seite „Social Media“. */
function SocialReturn() {
  const { search } = useLocation()
  return <Navigate to={`/webseite/beitraege${search}`} replace />
}
