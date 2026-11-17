// Sitzungsablauf mit Vorwarnung und ohne Verlust der Eingaben (UX-Audit 16.11. VW-04).
//
// Zehn Minuten vor dem Ablauf fragt HUBIplan „Angemeldet bleiben?“. Ist die Anmeldung schon
// abgelaufen, bleibt die Seite mit allen Eingaben stehen: Die Person meldet sich in einem
// zweiten Tab neu an (dort gehen alle Wege: Passwort, zweiter Faktor, Passkey, Link, Verbund)
// und macht hier weiter.
import { useEffect, useRef } from 'react'
import * as authApi from '../api/auth.ts'
import { sessionApi } from '../api/session.ts'
import { choiceDialog } from '../components/dialog.ts'
import { t } from '../i18n/index.ts'
import { useAuth } from './AuthContext.tsx'

/** So viele Sekunden vor dem Ablauf kommt die Vorwarnung */
export const SESSION_WARN_SECONDS = 600
// setTimeout nimmt höchstens 2^31 − 1 Millisekunden
const MAX_DELAY = 2_000_000_000

export function SessionWatch() {
  const { user, expired, resumeSession, leaveExpired, markExpired } = useAuth()
  const userId = user?.id ?? null
  const asking = useRef(false)

  // Vorwarnung und Prüfung zum Ablaufzeitpunkt
  useEffect(() => {
    if (userId === null || expired) return
    let alive = true
    let timer: ReturnType<typeof setTimeout> | undefined
    const later = (seconds: number, run: () => void) => {
      clearTimeout(timer)
      timer = setTimeout(run, Math.min(Math.max(seconds, 0) * 1000, MAX_DELAY))
    }
    const atExpiry = async () => {
      const current = await authApi.getSession().catch(() => undefined)
      if (alive && current === null) markExpired()
    }
    const warn = async () => {
      if (!alive || asking.current) return
      asking.current = true
      const pick = await choiceDialog({
        title: t('Deine Anmeldung läuft in wenigen Minuten ab'),
        message: t(
          'Danach musst du dich neu anmelden. Mit „Angemeldet bleiben“ arbeitest du ohne Unterbrechung weiter.',
        ),
        choices: [
          { value: 'stay', label: t('Angemeldet bleiben'), primary: true },
          { value: 'later', label: t('Später') },
        ],
        cancelValue: 'later',
      })
      asking.current = false
      if (!alive) return
      if (pick === 'stay') {
        try {
          plan((await sessionApi.extend()).expires_in)
          return
        } catch {
          // Verlängern ging nicht: unten neu einplanen, die Prüfung zum Ablauf fängt es auf
        }
      }
      const rest = await sessionApi.get().catch(() => null)
      if (alive && rest) later(rest.expires_in + 2, () => void atExpiry())
    }
    const plan = (expiresIn: number) => {
      if (expiresIn > SESSION_WARN_SECONDS)
        later(expiresIn - SESSION_WARN_SECONDS, () => void warn())
      else void warn()
    }
    const load = () => {
      if (asking.current) return
      sessionApi
        .get()
        .then((info) => alive && plan(info.expires_in))
        // ältere Server ohne diese Auskunft: keine Vorwarnung, der Ablauf wird wie bisher erkannt
        .catch(() => undefined)
    }
    load()
    // Zeitgeber laufen im Ruhezustand des Geräts nicht weiter: beim Zurückkommen neu rechnen
    const visible = () => {
      if (document.visibilityState === 'visible') load()
    }
    document.addEventListener('visibilitychange', visible)
    return () => {
      alive = false
      clearTimeout(timer)
      document.removeEventListener('visibilitychange', visible)
    }
  }, [userId, expired, markExpired])

  // Abgelaufen: Seite bleibt stehen, neu anmelden in einem zweiten Tab
  useEffect(() => {
    if (!expired || userId === null) return
    let alive = true
    void (async () => {
      while (alive) {
        const pick = await choiceDialog({
          title: t('Deine Anmeldung ist abgelaufen'),
          message: t(
            'Melde dich in einem neuen Tab erneut an und komm dann hierher zurück. Deine Eingaben bleiben erhalten.',
          ),
          choices: [
            {
              value: 'tab',
              label: t('In neuem Tab anmelden'),
              hint: t('Die Seite hier bleibt offen.'),
              primary: true,
            },
            {
              value: 'check',
              label: t('Ich bin wieder angemeldet'),
              hint: t('Prüft die Anmeldung und macht hier weiter.'),
            },
            {
              value: 'leave',
              label: t('Zur Anmeldung wechseln'),
              hint: t('Nicht gespeicherte Eingaben auf dieser Seite gehen verloren.'),
            },
          ],
          cancelValue: 'check',
        })
        if (!alive) return
        if (pick === 'leave') {
          leaveExpired()
          return
        }
        if (pick === 'tab') {
          window.open('/anmelden', '_blank', 'noopener')
          continue
        }
        const current = await authApi.getSession().catch(() => undefined)
        if (!alive) return
        if (current && current.id === userId) {
          resumeSession()
          return
        }
        if (current) {
          // inzwischen ein anderes Konto: nichts von dieser Seite darf dorthin geraten
          window.location.assign('/')
          return
        }
      }
    })()
    return () => {
      alive = false
    }
  }, [expired, userId, leaveExpired, resumeSession])

  return null
}
