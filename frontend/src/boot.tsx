// Start der Oberfläche; main.tsx lädt diese Datei erst nach dem Sprachkatalog.
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import App from './App.tsx'
import { AuthProvider } from './auth/AuthContext.tsx'
import { OrgProvider } from './org/OrgContext.tsx'
import './theme/theme.css'
import './index.css'
import { watchTableSemantics } from './components/tableSemantics.ts'
import { watchFormValidation } from './components/formValidation.ts'
import { loadPlatform } from './theme/platform.ts'
import { t } from './i18n/index.ts'
import { installStepUp } from './components/stepUp.ts'

watchTableSemantics()
// Fehler am Feld statt Browserblase (UX-Audit 08.11., W-08)
watchFormValidation()
// Frischer Code vor heiklen Aktionen (Gesamtaudit 10.11.)
installStepUp()
document.documentElement.style.setProperty('--pflicht-text', JSON.stringify(` (${t('Pflicht')})`))
// Name, Farben und Logo der Instanz (White Label); die Oberfläche wartet nicht darauf
void loadPlatform()

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <BrowserRouter>
      <AuthProvider>
        <OrgProvider>
          <App />
        </OrgProvider>
      </AuthProvider>
    </BrowserRouter>
  </StrictMode>,
)
