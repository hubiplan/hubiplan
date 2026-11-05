import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from 'react'
import type { ReactNode } from 'react'
import * as api from '../api/auth.ts'
import type { User } from '../api/auth.ts'
import { bindUndoToUser, clearUndo } from '../components/undo.ts'
import { lang, switchLanguage, t } from '../i18n/index.ts'
import {
  bindStandUser,
  clearStandCache,
  isStandNetworkError,
  pendingStandInputs,
  removeLegacyStandCache,
  suspendStandUser,
} from '../api/standCache.ts'
import { alertDialog, confirmDialog } from '../components/dialog.ts'

interface AuthState {
  user: User | null
  loading: boolean
  /** Server beim Start nicht erreichbar (z. B. Standmodus ohne Empfang) */
  offline: boolean
  setUser: (user: User | null) => void
  logout: () => Promise<boolean>
}

const AuthContext = createContext<AuthState | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, putUser] = useState<User | null>(null)
  const [loading, setLoading] = useState(true)
  const [offline, setOffline] = useState(false)
  const revision = useRef(0)
  const setUser = useCallback((next: User | null) => {
    revision.current += 1
    bindStandUser(next?.id ?? null)
    setOffline(false)
    setLoading(false)
    putUser(next)
  }, [])

  useEffect(() => {
    const lost = removeLegacyStandCache()
    if (lost)
      queueMicrotask(
        () =>
          void alertDialog({
            title: t('Alter Stand-Speicher entfernt'),
            message: t(
              'Der alte Stand-Speicher war keinem Konto zugeordnet. {n} nicht übertragene Eingaben wurden aus Sicherheitsgründen entfernt. Bitte den Stand prüfen.',
              { n: lost },
            ),
          }),
      )
    const load = () => {
      const at = revision.current
      void api
        .getSession()
        .then((next) => {
          if (at === revision.current) setUser(next)
        })
        .catch((error) => {
          if (at !== revision.current) return
          putUser(null)
          setOffline(isStandNetworkError(error))
          // Ungewisser Serverzustand sperrt die Oberfläche, erhält aber den Cache.
          // Nur getSession()s bestätigtes null darf die Konto-Bindung entfernen.
          setLoading(false)
        })
    }
    load()
    const changed = (event: StorageEvent) => {
      if (event.key !== 'hubiplan.stand.user') return
      revision.current += 1
      clearUndo()
      suspendStandUser()
      putUser(null)
      setOffline(false)
      setLoading(true)
      load()
    }
    window.addEventListener('storage', changed)
    return () => {
      revision.current += 1
      window.removeEventListener('storage', changed)
    }
  }, [setUser])

  const logout = useCallback(async () => {
    const pending = pendingStandInputs()
    if (
      pending &&
      !(await confirmDialog({
        title: t('Nicht übertragene Stand-Eingaben'),
        message: t(
          '{n} Stand-Eingaben sind noch nicht übertragen. Beim Abmelden werden sie auf diesem Browser gelöscht. Jetzt abmelden und verwerfen?',
          { n: pending },
        ),
        confirmLabel: t('Abmelden und verwerfen'),
      }))
    )
      return false
    // Wirft, wenn der Server die Abmeldung ablehnt: dann bleibt man sichtbar angemeldet.
    await api.logout()
    clearUndo()
    clearStandCache()
    setUser(null)
    return true
  }, [setUser])

  useEffect(() => {
    if (user) bindUndoToUser(user.id)
    // Konto in anderer Sprache als die Anzeige (z. B. nach der Anmeldung): umschalten
    if (user?.language && (user.language === 'de' || user.language === 'en')) {
      if (user.language !== lang()) switchLanguage(user.language)
    }
  }, [user])

  const value = useMemo(
    () => ({ user, loading, offline, setUser, logout }),
    [user, loading, offline, logout, setUser],
  )
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

// oxlint-disable-next-line react/only-export-components
export function useAuth(): AuthState {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error(t('useAuth muss innerhalb von AuthProvider genutzt werden.'))
  return ctx
}
