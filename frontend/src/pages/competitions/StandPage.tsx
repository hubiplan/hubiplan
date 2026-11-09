// Standmodus: Vollbild ohne Menü, für Tablet, Laptop und Handy am Schießstand.
// Angemeldet über /stand/<einheit>/<wettbewerb> oder ohne Konto über einen Standzugang
// (/stand/zugang/<schlüssel>). Der Bildschirm bleibt an, und die Seite lässt sich auch ohne
// Netz neu laden (Offline-Speicher im Browser, public/sw-stand.js).
import { useEffect, useMemo, useState } from 'react'
import type { ReactNode } from 'react'
import { Link, useParams } from 'react-router-dom'
import {
  orgStandApi,
  tokenStandApi,
  type CompetitionDetail,
  type StandApi,
} from '../../api/competitions.ts'
import { useLoad } from '../../components/forms.ts'
import { LoadError, Loading } from '../../components/ui.tsx'
import { StandAccessCard } from './BirdSetup.tsx'
import { BirdStand } from './BirdStand.tsx'
import { LiveTables } from './LiveTables.tsx'
import { StandPanel } from './StandPanel.tsx'
import { locale, t } from '../../i18n/index.ts'
import { useAuth } from '../../auth/AuthContext.tsx'
import {
  isStandNetworkError,
  loadStandCache,
  pendingStandInputs,
  revokeStandCache,
  saveStandCache,
  standCacheAllowed,
  standCacheExpired,
  standRevision,
  standTokenKey,
  subscribeStandCache,
} from '../../api/standCache.ts'

// Die HUBIplan-App zeigt den Standmodus eingebettet und fragt vor dem Verlassen, ob noch
// Eingaben auf dem Gerät warten (konzepte/schiessen-android.md).
declare global {
  interface Window {
    hubiplanStand?: { pending: () => number }
  }
}

function useAppBridge() {
  useEffect(() => {
    window.hubiplanStand = { pending: pendingStandInputs }
    return () => {
      delete window.hubiplanStand
    }
  }, [])
}

export function StandPage() {
  useAppBridge()
  const params = useParams()
  const org = Number(params.org)
  const id = Number(params.id)
  const { user } = useAuth()
  const api = useMemo(() => orgStandApi(org, id), [org, id, user?.id])
  return (
    <StandShell
      key={api.key}
      api={api}
      org={org}
      exit={
        <Link className="button button-ghost" to={`/wettbewerbe/${id}`}>
          {t('Standmodus verlassen')}
        </Link>
      }
    />
  )
}

export function StandTokenPage() {
  useAppBridge()
  const token = useParams().token ?? ''
  const [key, setKey] = useState<{ token: string; key: string } | null>(null)
  const [failed, setFailed] = useState(false)
  useEffect(() => {
    let stop = false
    void standTokenKey(token)
      .then((key) => {
        if (!stop) setKey({ token, key })
      })
      .catch(() => {
        if (!stop) setFailed(true)
      })
    return () => {
      stop = true
    }
  }, [token])
  const api = useMemo(
    () => (key?.token === token ? tokenStandApi(token, key.key) : null),
    [token, key],
  )
  if (failed)
    return (
      <p className="alert alert-error">
        {t('Der sichere Stand-Speicher ist in diesem Browser nicht verfügbar.')}
      </p>
    )
  return api ? <StandShell key={api.key} api={api} exit={null} /> : <Loading />
}

function StandShell({ api, exit, org }: { api: StandApi; exit: ReactNode; org?: number }) {
  const [showAccess, setShowAccess] = useState(false)
  const [, refresh] = useState(0)
  useEffect(() => subscribeStandCache(() => refresh((n) => n + 1)), [])
  useEffect(() => {
    const timer = setInterval(() => {
      if (standCacheExpired(api.key)) revokeStandCache(api.key)
    }, 1000)
    return () => clearInterval(timer)
  }, [api.key])
  const {
    data: loaded,
    error,
    reload,
  } = useLoad(async () => {
    const at = standRevision()
    try {
      const detail = await api.get()
      saveStandCache(api.key, 'detail', detail, at)
      return detail
    } catch (err) {
      // Ohne Empfang: zuletzt geladene Einrichtung vom Gerät
      const cached =
        at === standRevision() && isStandNetworkError(err)
          ? loadStandCache<CompetitionDetail>(api.key, 'detail')
          : null
      if (cached) return cached
      throw err
    }
  }, [api.key])
  const data = !error && standCacheAllowed(api.key) ? loaded : null
  useWakeLock()
  useOfflineReload()
  return (
    <main className="stand-page">
      <header className="stand-head">
        <strong>{data?.title ?? t('Standmodus')}</strong>
        {data?.stand_access && (
          <span className="muted small">
            {t('Standzugang')}
            {data.stand_access.label ? ` ${data.stand_access.label}` : ''} {t('bis')}{' '}
            {new Date(data.stand_access.expires_at).toLocaleTimeString(locale(), {
              hour: '2-digit',
              minute: '2-digit',
            })}
          </span>
        )}
        {exit && (
          <div className="button-row push-right stand-head-actions">
            {org &&
              data?.own &&
              (data.can_stand_access ?? data.can_manage) &&
              data.status !== 'endgueltig' && (
                <button
                  type="button"
                  className="button button-ghost"
                  aria-expanded={showAccess}
                  onClick={() => setShowAccess((v) => !v)}
                >
                  {t('Anderes Gerät per QR-Code')}
                </button>
              )}
            {exit}
          </div>
        )}
      </header>
      {showAccess && org && data && <StandAccessCard org={org} comp={data} />}
      {error && <LoadError message={error} onRetry={reload} />}
      {loaded && !data && !error && (
        <LoadError
          message={t('Der Standzugang ist abgelaufen oder wurde beendet. Bitte erneut verbinden.')}
          onRetry={reload}
        />
      )}
      {data &&
        (!data.own ? (
          <p className="alert alert-info">
            {t(
              'Bei fremden Wettbewerben gibt es keinen Standmodus. Plätze bitte unter „Erfassen“ eintragen.',
            )}
          </p>
        ) : data.form === 'vogel' ? (
          <BirdStand api={api} comp={data} fullscreen />
        ) : (
          <div className="stand-layout">
            <StandPanel api={api} comp={data} fullscreen org={org} />
            <LiveTables api={api} />
          </div>
        ))}
    </main>
  )
}

/** Bildschirm bleibt an, solange der Standmodus offen und sichtbar ist. */
function useWakeLock() {
  useEffect(() => {
    type Sentinel = { release: () => Promise<void> }
    const nav = navigator as Navigator & {
      wakeLock?: { request: (type: 'screen') => Promise<Sentinel> }
    }
    if (!nav.wakeLock) return
    let lock: Sentinel | null = null
    let stop = false
    const take = () => {
      if (document.visibilityState !== 'visible') return
      nav.wakeLock
        ?.request('screen')
        .then((l) => {
          if (stop) void l.release()
          else lock = l
        })
        .catch(() => undefined)
    }
    take()
    document.addEventListener('visibilitychange', take)
    return () => {
      stop = true
      document.removeEventListener('visibilitychange', take)
      void lock?.release().catch(() => undefined)
    }
  }, [])
}

/** Offline-Speicher: die Seite und ihre Dateien für das Neuladen ohne Netz vormerken. */
function useOfflineReload() {
  useEffect(() => {
    if (!('serviceWorker' in navigator) || !window.isSecureContext) return
    const assets = performance
      .getEntriesByType('resource')
      .map((e) => new URL(e.name).pathname)
      .filter((p) => p.startsWith('/assets/'))
    navigator.serviceWorker
      .register('/sw-stand.js', { scope: '/' })
      .then(() => navigator.serviceWorker.ready)
      .then((reg) =>
        reg.active?.postMessage({
          type: 'merken',
          page: window.location.pathname,
          assets: [...new Set(assets)],
        }),
      )
      .catch(() => undefined)
  }, [])
}
