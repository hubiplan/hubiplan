// Finanzen: Kasse und Beiträge/Rechnungen unter einem Menüpunkt.
// Unterpunkte stehen in der Seitenleiste (siehe access.ts), innerhalb eines
// Unterpunkts führen Reiter weiter.
import type { ReactNode } from 'react'
import { Navigate, Route, Routes, useLocation } from 'react-router-dom'
import { Tabs, useSubHeading } from '../../components/ui.tsx'
import { useActiveOrg } from '../../org/OrgContext.tsx'
import { DebitsPage, MandatesPage } from '../billing/DebitsPage.tsx'
import { DunningsPage } from '../billing/DunningsPage.tsx'
import { InvoicesPage } from '../billing/InvoicesPage.tsx'
import { EInvoicesPage } from '../billing/EInvoicesPage.tsx'
import { IncomingInvoicesPage } from '../billing/IncomingInvoicesPage.tsx'
import { PartnersPage } from '../billing/PartnersPage.tsx'
import { ReceivedPage } from '../billing/ReceivedPage.tsx'
import { BillingSettingsPage, DunningLevelsPage, FeeRulesPage } from '../billing/RulesPage.tsx'
import { RunsPage } from '../billing/RunsPage.tsx'
import { BankStatementsPage } from '../finance/BankStatementsPage.tsx'
import { BookingsPage } from '../finance/BookingsPage.tsx'
import { CashCountsPage } from '../finance/CashCountsPage.tsx'
import { CashReceiptsArea } from '../finance/CashReceiptsPage.tsx'
import { ReservesPage } from '../finance/ReservesPage.tsx'
import { ClosingsPage } from '../finance/ClosingsPage.tsx'
import { DonationSettingsForm, DonationsArea } from '../finance/DonationsPage.tsx'
import { ProjectsArea } from '../finance/ProjectsPage.tsx'
import { AccountsPage, CategoriesPage } from '../finance/MasterDataPages.tsx'
import { financeAccess, financeSections, sectionsUnder } from './access.ts'
import type { FinanceAccess, NavItem } from './access.ts'
import { FinanceDevelopment } from './DevelopmentPage.tsx'
import { EvaluationPage, FinanceOverview } from './OverviewPages.tsx'
import { TaxPage } from './TaxPage.tsx'
import { AuditPage } from './AuditPage.tsx'
import { NetAssetsPage } from './NetAssetsPage.tsx'
import { UseOfFundsPage } from './UseOfFundsPage.tsx'
import { ArtistFeesPage } from './ArtistFeesPage.tsx'
import { AllowancesPage } from './AllowancesPage.tsx'
import { VatPage } from './VatPage.tsx'
import { AssetsPage } from './AssetsPage.tsx'
import { PayoutRunsPage } from '../music/PayoutRunsPage.tsx'
import { t } from '../../i18n/index.ts'

function Section({
  title,
  readOnly,
  tabs,
  children,
}: {
  title: string
  readOnly?: boolean
  tabs?: NavItem[]
  children: ReactNode
}) {
  // Dritte Ebene (z. B. Steuern › Umsatzsteuer): H1 wie der gewählte Unterpunkt, der Weg
  // steht darüber (UX-Audit 08.11., W-02); dazu die Arbeitsgruppe des Eintrags (S-01)
  const sub = useSubHeading(title, tabs)
  const org = useActiveOrg()
  const { pathname } = useLocation()
  const group = financeSections(financeAccess(org))
    .filter((i) => pathname === i.to || pathname.startsWith(`${i.to}/`))
    .sort((x, y) => y.to.length - x.to.length)[0]?.group?.label
  const trail = [t('Finanzen'), group, sub ? title : null].filter((p): p is string => !!p)
  return (
    <section>
      <div className="page-head">
        <div>
          {/* Auf der Übersicht heißt die H1 wie der Bereich (UX-Audit 05.11. W-04) */}
          {title !== t('Übersicht') && (
            <p className="muted small eyebrow">
              {trail.reduce((parent, label) => t('{parent} › {label}', { parent, label }))}
            </p>
          )}
          <h1>{sub ?? (title === t('Übersicht') ? t('Finanzen') : title)}</h1>
        </div>
        {readOnly && <span className="muted small push-right">{t('nur lesen')}</span>}
      </div>
      {tabs && tabs.length > 1 && <Tabs items={tabs} />}
      {children}
    </section>
  )
}

const home = <Navigate to="/finanzen" replace />

export function FinanzenPage() {
  const org = useActiveOrg()
  const a = financeAccess(org)
  if (!a.finance && !a.billing) return <Navigate to="/" replace />
  return (
    <Routes>
      <Route
        index
        element={
          <Section title={t('Übersicht')}>
            <FinanceOverview access={a} />
          </Section>
        }
      />
      <Route
        path="entwicklung"
        element={
          a.finance ? (
            <Section title={t('Entwicklung')}>
              <FinanceDevelopment canEdit={a.financeEdit} />
            </Section>
          ) : (
            home
          )
        }
      />
      <Route
        path="rechnungen/*"
        element={
          a.billing || a.received || a.finance ? <InvoicesArea key={org.id} access={a} /> : home
        }
      />
      <Route
        path="geschaeftspartner"
        element={
          <Section title={t('Geschäftspartner')}>
            <PartnersPage key={org.id} canEdit={a.billingEdit || a.financeEdit} />
          </Section>
        }
      />
      <Route path="lastschrift/*" element={a.sepa ? <DebitsArea access={a} /> : home} />
      <Route
        path="kassenbuch"
        element={
          a.finance ? (
            <Section title={t('Kassenbuch')} readOnly={!a.financeEdit}>
              <BookingsPage />
            </Section>
          ) : (
            home
          )
        }
      />
      <Route
        path="kontoauszuege"
        element={
          a.finance ? (
            <Section title={t('Kontoauszüge')} readOnly={!a.financeEdit}>
              <BankStatementsPage canEdit={a.financeEdit} />
            </Section>
          ) : (
            home
          )
        }
      />
      <Route
        path="quittungen/*"
        element={
          a.finance ? (
            <Section title={t('Quittungen')} readOnly={!a.financeEdit}>
              <CashReceiptsArea canEdit={a.financeEdit} />
            </Section>
          ) : (
            home
          )
        }
      />
      <Route
        path="kassenzaehlung"
        element={
          a.cashCounts ? (
            <Section title={t('Kassenzählung')} readOnly={!a.financeEdit}>
              <CashCountsPage canEdit={a.financeEdit} />
            </Section>
          ) : (
            home
          )
        }
      />
      <Route
        path="ruecklagen"
        element={
          a.reserves ? (
            <Section title={t('Rücklagen')} readOnly={!a.financeEdit}>
              <ReservesPage canEdit={a.financeEdit} />
            </Section>
          ) : (
            home
          )
        }
      />
      <Route
        path="zuwendungen/*"
        element={
          a.donations ? (
            <Section
              title={t('Zuwendungsbestätigungen')}
              readOnly={!a.financeEdit}
              tabs={[
                { to: '/finanzen/zuwendungen', label: t('Zuwendungen') },
                { to: '/finanzen/zuwendungen/bestaetigungen', label: t('Bestätigungen') },
                { to: '/finanzen/zuwendungen/zweckbindungen', label: t('Zweckbindungen') },
              ]}
            >
              <DonationsArea canEdit={a.financeEdit} />
            </Section>
          ) : (
            home
          )
        }
      />
      <Route
        path="veranstaltungen/*"
        element={
          a.finance ? (
            <Section
              title={t('Veranstaltungen')}
              readOnly={!a.financeEdit}
              tabs={[
                { to: '/finanzen/veranstaltungen', label: t('Veranstaltungen') },
                { to: '/finanzen/veranstaltungen/reihen', label: t('Reihen') },
              ]}
            >
              <ProjectsArea />
            </Section>
          ) : (
            home
          )
        }
      />
      <Route path="auswertung/*" element={a.finance ? <EvaluationArea /> : home} />
      <Route path="steuern/*" element={a.tax ? <TaxArea access={a} /> : home} />
      <Route
        path="anlagen"
        element={
          a.tax ? (
            <Section title={t('Anlagen')} readOnly={!a.financeEdit}>
              <AssetsPage canEdit={a.financeEdit} />
            </Section>
          ) : (
            home
          )
        }
      />
      <Route
        path="pauschalen"
        element={
          a.tax ? (
            <Section title={t('Pauschalen')} readOnly={!a.financeEdit}>
              <AllowancesPage canEdit={a.financeEdit} />
            </Section>
          ) : (
            home
          )
        }
      />
      <Route path="sammelauszahlungen" element={a.payouts ? <PayoutRunsPage /> : home} />
      <Route path="abschluss/*" element={a.finance ? <ClosingArea access={a} /> : home} />
      <Route path="einrichtung/*" element={<SettingsArea access={a} />} />
      {/* Frühere Adresse der Einrichtung leitet weiter (Menüprüfung M-01) */}
      <Route path="einstellungen/*" element={<OldSetupRedirect />} />
      <Route path="*" element={home} />
    </Routes>
  )
}

/** Eintrag der Seitenleiste zur aktuellen Seite: liefert die Überschrift (keine Reiter mehr). */
function useCurrent(items: NavItem[], fallback: string): string {
  const { pathname } = useLocation()
  const path = pathname.replace(/(.)\/$/, '$1')
  return (
    items
      .filter((i) => path === i.to || path.startsWith(`${i.to}/`))
      .sort((x, y) => y.to.length - x.to.length)[0]?.label ?? fallback
  )
}

// Rechnungen und Einrichtung: die früheren Reiter sind Einträge der Arbeitsgruppen in der
// Seitenleiste (Konzept S-01); jede Seite trägt ihren eigenen Namen als Überschrift
function InvoicesArea({ access: a }: { access: FinanceAccess }) {
  const tabs = sectionsUnder(a, '/finanzen/rechnungen')
  const title = useCurrent(tabs, t('Rechnungen'))
  if (tabs.length === 0) return home
  return (
    <Section title={title} readOnly={a.billing && !a.billingEdit}>
      <Routes>
        <Route
          index
          element={a.billing ? <InvoicesPage /> : <Navigate to={tabs[0].to} replace />}
        />
        {a.feeRuns && <Route path="beitragslaeufe" element={<RunsPage />} />}
        {a.billing && <Route path="mahnungen" element={<DunningsPage />} />}
        {a.billing && (
          <Route path="leistungen" element={<EInvoicesPage canEdit={a.billingEdit} />} />
        )}
        {a.finance && (
          <Route path="eingang" element={<IncomingInvoicesPage canEdit={a.financeEdit} />} />
        )}
        {a.received && <Route path="dachverband" element={<ReceivedPage />} />}
        <Route path="*" element={<Navigate to={tabs[0].to} replace />} />
      </Routes>
    </Section>
  )
}

function DebitsArea({ access: a }: { access: FinanceAccess }) {
  return (
    <Section
      title={t('Lastschriften')}
      readOnly={!a.billingEdit}
      tabs={[
        { to: '/finanzen/lastschrift', label: t('Lastschriftläufe') },
        { to: '/finanzen/lastschrift/mandate', label: t('SEPA-Mandate') },
      ]}
    >
      <Routes>
        <Route index element={<DebitsPage />} />
        <Route path="mandate" element={<MandatesPage />} />
        <Route path="*" element={<Navigate to="/finanzen/lastschrift" replace />} />
      </Routes>
    </Section>
  )
}

/** Frühere Adressen unter „Abschluss & Berichte“ leiten weiter (Menüprüfung 2, N-04). */
function Moved({ to }: { to: string }) {
  const { search } = useLocation()
  return <Navigate to={`${to}${search}`} replace />
}

function EvaluationArea() {
  return (
    <Section
      title={t('Auswertung')}
      tabs={[
        { to: '/finanzen/auswertung', label: t('Auswertung') },
        { to: '/finanzen/auswertung/vermoegen', label: t('Vermögen') },
      ]}
    >
      <Routes>
        <Route index element={<EvaluationPage />} />
        <Route path="vermoegen" element={<NetAssetsPage />} />
        <Route path="*" element={<Navigate to="/finanzen/auswertung" replace />} />
      </Routes>
    </Section>
  )
}

function TaxArea({ access: a }: { access: FinanceAccess }) {
  return (
    <Section
      title={t('Steuern')}
      tabs={[
        { to: '/finanzen/steuern', label: t('Steuern') },
        { to: '/finanzen/steuern/umsatzsteuer', label: t('Umsatzsteuer') },
        { to: '/finanzen/steuern/kuenstlersozialabgabe', label: t('Künstlersozialabgabe') },
        { to: '/finanzen/steuern/mittelverwendung', label: t('Mittelverwendung') },
      ]}
    >
      <Routes>
        <Route index element={<TaxPage />} />
        <Route path="umsatzsteuer" element={<VatPage canEdit={a.financeEdit} />} />
        <Route path="kuenstlersozialabgabe" element={<ArtistFeesPage />} />
        <Route path="mittelverwendung" element={<UseOfFundsPage />} />
        <Route path="*" element={<Navigate to="/finanzen/steuern" replace />} />
      </Routes>
    </Section>
  )
}

function ClosingArea({ access: a }: { access: FinanceAccess }) {
  return (
    <Section
      title={t('Jahresabschluss')}
      readOnly={!a.financeEdit}
      tabs={[
        { to: '/finanzen/abschluss', label: t('Jahresabschluss') },
        { to: '/finanzen/abschluss/kassenpruefung', label: t('Kassenprüfung') },
      ]}
    >
      <Routes>
        <Route index element={<ClosingsPage />} />
        <Route path="kassenpruefung" element={<AuditPage canEdit={a.financeEdit} />} />
        <Route path="jahresabschluss" element={<Moved to="/finanzen/abschluss" />} />
        <Route path="vermoegen" element={<Moved to="/finanzen/auswertung/vermoegen" />} />
        <Route path="steuern" element={<Moved to="/finanzen/steuern" />} />
        <Route path="umsatzsteuer" element={<Moved to="/finanzen/steuern/umsatzsteuer" />} />
        <Route
          path="kuenstlersozialabgabe"
          element={<Moved to="/finanzen/steuern/kuenstlersozialabgabe" />}
        />
        <Route
          path="mittelverwendung"
          element={<Moved to="/finanzen/steuern/mittelverwendung" />}
        />
        <Route path="anlagen" element={<Moved to="/finanzen/anlagen" />} />
        <Route path="pauschalen" element={<Moved to="/finanzen/pauschalen" />} />
        <Route path="*" element={<Navigate to="/finanzen/abschluss" replace />} />
      </Routes>
    </Section>
  )
}

function SettingsArea({ access: a }: { access: FinanceAccess }) {
  const tabs = sectionsUnder(a, '/finanzen/einrichtung')
  const title = useCurrent(tabs, t('Einrichtung'))
  if (tabs.length === 0) return <Navigate to="/finanzen/geschaeftspartner" replace />
  const first = <Navigate to={tabs[0].to} replace />
  const readOnly = !a.billingEdit && !a.financeEdit
  return (
    <Section title={title} readOnly={readOnly}>
      <Routes>
        <Route index element={first} />
        {a.feeRuns && <Route path="beitraege" element={<FeeRulesPage />} />}
        {a.billing && <Route path="mahnstufen" element={<DunningLevelsPage />} />}
        {a.billing && <Route path="rechnung" element={<BillingSettingsPage />} />}
        {a.finance && <Route path="konten" element={<AccountsPage />} />}
        {a.finance && <Route path="kategorien" element={<CategoriesPage />} />}
        {a.donations && (
          <Route path="zuwendungen" element={<DonationSettingsForm canEdit={a.financeEdit} />} />
        )}
        <Route path="*" element={first} />
      </Routes>
    </Section>
  )
}

/** /finanzen/einstellungen/… → /finanzen/einrichtung/… */
function OldSetupRedirect() {
  const { pathname, search } = useLocation()
  return (
    <Navigate
      to={pathname.replace('/finanzen/einstellungen', '/finanzen/einrichtung') + search}
      replace
    />
  )
}
