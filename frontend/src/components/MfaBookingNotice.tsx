// Buchen ruht ohne Zwei-Faktor-Anmeldung (Pflicht-2FA für heikle Rechte): Die Buchungsseite
// nennt den Grund an Ort und Stelle und führt zur Einrichtung, statt nur das Banner oben.
import { Link } from 'react-router-dom'
import { useAuthOptional } from '../auth/AuthContext.tsx'
import { t } from '../i18n/index.ts'

/** Fehlt dem Konto die Zwei-Faktor-Anmeldung? Dann zieht der Server das Recht zu buchen ab. */
export function useBookingPaused(): boolean {
  const user = useAuthOptional()?.user
  return !!user?.mfa_required_by
}

export function MfaBookingNotice() {
  return (
    <div className="alert alert-info" role="status" data-testid="buchen-ruht">
      <p>
        {t(
          'Ohne Zwei-Faktor-Anmeldung ruht das Buchen in der Kasse: Sie schützt die Kasse, falls ein Passwort in falsche Hände gerät. Das Einrichten dauert zwei Minuten; wer buchen darf, kann danach sofort loslegen.',
        )}
      </p>
      <div className="button-row">
        <Link to="/mein-konto/anmeldung#zwei-faktor" className="button button-primary">
          {t('Zwei-Faktor-Anmeldung einrichten')}
        </Link>
      </div>
    </div>
  )
}
