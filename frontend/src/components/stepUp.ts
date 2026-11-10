// Frische Bestätigung vor heiklen Aktionen (Gesamtaudit 10.11., Frage 1): Code aus der
// Authenticator-App oder, solange noch keine Zwei-Faktor-Anmeldung eingerichtet ist,
// das Passwort. Hat das Konto für diese Adresse einen Passkey, wird zuerst er angeboten.
// Wird in boot.tsx als Dialog für api/client.ts eingetragen.
import { passkeyReauth, passkeyReauthOptions } from '../api/auth.ts'
import { request, setStepUpHandler, type StepUpKind } from '../api/client.ts'
import { cancelled, getPasskey, passkeysSupported } from '../auth/webauthn.ts'
import { t } from '../i18n/index.ts'
import { alertDialog, choiceDialog, promptDialog } from './dialog.ts'

let pending: Promise<boolean> | null = null

/** Mit Passkey bestätigen: true (bestätigt), false (abgebrochen) oder 'code' (lieber Code). */
async function askPasskey(): Promise<boolean | 'code'> {
  let hint = ''
  for (;;) {
    const choice = await choiceDialog({
      title: t('Aktion bestätigen'),
      message:
        (hint ? `${hint} ` : '') +
        t('Diese Aktion ist besonders geschützt. Bitte bestätige sie mit deinem Passkey.'),
      choices: [
        { value: 'passkey', label: t('Mit Passkey bestätigen'), primary: true },
        { value: 'code', label: t('Code eingeben') },
        { value: 'cancel', label: t('Abbrechen') },
      ],
      cancelValue: 'cancel',
    })
    if (choice === 'cancel') return false
    if (choice === 'code') return 'code'
    try {
      const result = await passkeyReauth(await getPasskey(await passkeyReauthOptions()))
      if (result.kind === 'ok') return true
      hint = result.kind === 'error' ? result.message : ''
    } catch (e) {
      hint = cancelled(e) ? '' : t('Die Bestätigung mit Passkey hat nicht geklappt.')
    }
  }
}

async function ask(kind: StepUpKind, passkey: boolean): Promise<boolean> {
  if (passkey && kind === 'code' && passkeysSupported()) {
    const result = await askPasskey()
    if (result !== 'code') return result
  }
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
export function confirmStepUp(kind: StepUpKind, passkey = false): Promise<boolean> {
  if (!pending) {
    pending = ask(kind, passkey).finally(() => {
      pending = null
    })
  }
  return pending
}

export function installStepUp() {
  setStepUpHandler(confirmStepUp)
}
