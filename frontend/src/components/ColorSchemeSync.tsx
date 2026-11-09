// Hält die Darstellung hell/dunkel (X-02, D1) mit Seite und Konto in Einklang.
import { useEffect, useLayoutEffect } from 'react'
import { useLocation } from 'react-router-dom'
import { appearanceApi } from '../api/appearance.ts'
import { useAuth } from '../auth/AuthContext.tsx'
import { initColorScheme, setColorSchemeChoice, setColorSchemePath } from '../theme/colorScheme.ts'

let started = false

export function ColorSchemeSync() {
  const { pathname } = useLocation()
  const { user } = useAuth()
  const userId = user?.id ?? null

  // Vor dem Zeichnen, damit eine Verwaltungsseite nie kurz dunkel aufblitzt
  useLayoutEffect(() => {
    if (!started) {
      started = true
      initColorScheme()
    }
    setColorSchemePath(pathname)
  }, [pathname])

  useEffect(() => {
    if (userId === null) return
    let alive = true
    appearanceApi
      .get()
      .then((data) => alive && setColorSchemeChoice(data.color_scheme))
      .catch(() => undefined)
    return () => {
      alive = false
    }
  }, [userId])

  return null
}
