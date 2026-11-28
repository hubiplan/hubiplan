import { Navigate, Outlet, useLocation } from 'react-router-dom'
import { Tabs } from '../../components/ui.tsx'
import { t } from '../../i18n/index.ts'
import { PageHeader } from '../../components/PageHeader.tsx'

const PLATFORM_TABS = [
  { to: '/plattform/organisationen', label: t('Einheiten') },
  { to: '/plattform/einstellungen', label: t('Einstellungen') },
  { to: '/plattform/impressum', label: t('Impressum') },
  { to: '/plattform/postfach', label: t('Postfach') },
  { to: '/plattform/datenuebernahme', label: t('Datenübernahme') },
  { to: '/plattform/version', label: t('Version') },
  { to: '/plattform/sicherheit', label: t('Sicherheit') },
  { to: '/plattform/hilfe', label: t('Hilfe') },
]

export function PlatformLayout() {
  const location = useLocation()
  if (location.pathname.replace(/\/$/, '') === '/plattform') {
    return <Navigate to="/plattform/organisationen" replace />
  }
  return (
    <section>
      {/* h1 = gewählte Unterseite, Pfad „Plattform › …“ (W-02, Seitenkopf S-05) */}
      <PageHeader />
      <Tabs items={PLATFORM_TABS} />
      <Outlet />
    </section>
  )
}
