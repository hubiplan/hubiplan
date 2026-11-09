// Verbindung verloren: sofort ein Band zeigen statt lange „Wird gespeichert …“ (UX-Audit 08.11. W-10).
// Automatisches Speichern holt Offenes nach, sobald der Browser wieder online ist (useAutoSave).
import { useEffect, useState } from 'react'
import { t } from '../i18n/index.ts'

export function useOnline(): boolean {
  const [online, setOnline] = useState(() =>
    typeof navigator === 'undefined' ? true : navigator.onLine !== false,
  )
  useEffect(() => {
    const on = () => setOnline(true)
    const off = () => setOnline(false)
    window.addEventListener('online', on)
    window.addEventListener('offline', off)
    return () => {
      window.removeEventListener('online', on)
      window.removeEventListener('offline', off)
    }
  }, [])
  return online
}

export function OfflineBanner() {
  const online = useOnline()
  if (online) return null
  return (
    <div className="alert alert-error offline-banner" role="status">
      {t('Keine Verbindung. Änderungen werden gespeichert, sobald die Verbindung wieder da ist.')}
    </div>
  )
}
