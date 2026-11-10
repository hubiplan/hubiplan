// Frische Bestätigung vor heiklen Aktionen (Gesamtaudit 10.11., Frage 1): Code aus der
// Authenticator-App oder, solange noch keine Zwei-Faktor-Anmeldung eingerichtet ist,
// das Passwort. Wird in boot.tsx als Dialog für api/client.ts eingetragen.
import { request, setStepUpHandler, type StepUpKind } from '../api/client.ts'
import { t } from '../i18n/index.ts'
import { alertDialog, promptDialog } from './dialog.ts'

let pending: Promise<boolean> | null = null

async function ask(kind: StepUpKind): Promise<boolean> {
  let hint = ''
  for (;;) {
    const intro =
      kind === 'code'
        ? t(
            'Diese Aktion ist besonders geschützt. Bitte gib zur Bestätigung den aktuellen Code aus deiner Authenticator-App ein (oder einen Wiederherstellungscode).',
          )
        : t(
            'Diese Aktion ist besonders geschützt. Bitte bestätige sie mit deinem Passwort. Mit eingerichteter Zwei-Faktor-Anmeldung fragen wir stattdessen nach einem Code.',
          )
    const value = await promptDialog({
      title: t('Aktion bestätigen'),
      message: hint ? `${hint} ${intro}` : intro,
      label: kind === 'code' ? t('Code') : t('Passwort'),
      confirmLabel: t('Bestätigen'),
      danger: false,
      inputType: kind === 'password' ? 'password' : 'text',
      inputMode: kind === 'code' ? 'numeric' : undefined,
      autoComplete: kind === 'code' ? 'one-time-code' : 'current-password',
    })
    if (value === null) return false
    if (!value.trim()) continue
    const { status, body } = await request<{ detail?: string }>(
      'POST',
      '/api/me/confirm/',
      kind === 'code' ? { code: value } : { password: value },
    )
    if (status === 200) return true
    if (status === 429) {
      await alertDialog(t('Zu viele Versuche. Bitte einen Moment warten.'))
      return false
    }
    if (status === 0) return false
    hint =
      (typeof body?.detail === 'string' && body.detail) ||
      (kind === 'code' ? t('Der Code stimmt nicht.') : t('Das Passwort stimmt nicht.'))
  }
}

/** Mehrere Anfragen gleichzeitig: nur ein Dialog, alle warten auf dieselbe Antwort. */
export function confirmStepUp(kind: StepUpKind): Promise<boolean> {
  if (!pending) {
    pending = ask(kind).finally(() => {
      pending = null
    })
  }
  return pending
}

export function installStepUp() {
  setStepUpHandler(confirmStepUp)
}
