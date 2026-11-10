// Plattform › Version: laufende Version, neueres Release und Selbstupdate
// (konzepte/selbstupdate.md, 7c). Der Knopf legt nur einen Auftrag ab; aktualisiert wird vom
// Aktualisierer auf dem Server (deploy/aktualisierer/), der Signatur und Rückschritt prüft.
import { useEffect, useState } from 'react'
import type { FormEvent } from 'react'
import { platformApi } from '../../api/orgs.ts'
import type { SelfUpdate } from '../../api/orgs.ts'
import { Alert, Field, Loading } from '../../components/ui.tsx'
import { errorMessage, formatDateTime, useLoad } from '../../components/forms.ts'
import { useRunningVersion } from '../../news/version.ts'
import { t, tn } from '../../i18n/index.ts'

/** Abstand der Nachfragen, solange ein Auftrag läuft (der Server startet dabei neu). */
const POLL_MS = 10_000

export function PlatformVersionPage() {
  const { data, error, reload, setData } = useLoad(() => platformApi.newRelease(), [])
  const running = useRunningVersion()
  const pending = !!data?.selfupdate?.pending
  useEffect(() => {
    if (!pending) return
    // Während des Updates ist der Server kurz weg; Fehler beim Nachfragen sind dann normal
    const timer = window.setInterval(() => void reload(), POLL_MS)
    return () => window.clearInterval(timer)
  }, [pending, reload])

  if (error && !data) return <Alert kind="error">{error}</Alert>
  if (!data) return <Loading />
  const update = data.update
  const self = data.selfupdate
  return (
    <div className="card card-wide">
      <h2>{t('Version')}</h2>
      <p>{t('Hier läuft HUBIplan {x}.', { x: running ?? update?.running ?? t('(unbekannt)') })}</p>
      {update ? (
        <p>
          {t('Neueres Release: {x}.', { x: update.version })}{' '}
          {update.url && (
            <a href={update.url} target="_blank" rel="noreferrer noopener">
              {t('Änderungen ansehen')}
            </a>
          )}
        </p>
      ) : (
        <p className="muted">
          {data.enabled
            ? t('Kein neueres Release bekannt. Der Server fragt einmal am Tag nach.')
            : t('Die Suche nach neuen Releases ist auf diesem Server ausgeschaltet.')}
        </p>
      )}
      {data.virus_scan && !(data.virus_scan.enabled && data.virus_scan.required) && (
        <Alert kind="error">
          {data.virus_scan.enabled
            ? t(
                'Die Virenprüfung ist eingerichtet, aber für die Weitergabe abgeschaltet (VIRUS_SCAN_REQUIRED=0). Rundschreiben-Anhänge und öffentliche Dokumente können ungeprüft hinausgehen.',
              )
            : t(
                'Auf diesem Server ist keine Virenprüfung eingerichtet. Rundschreiben-Anhänge und öffentliche Dokumente gehen ungeprüft an viele Empfänger. Einrichtung: docs/betrieb.md, Abschnitt Virenprüfung.',
              )}
        </Alert>
      )}
      {!!data.virus_scan?.quarantine?.pending && (
        <Alert kind="info">
          {tn(
            '{n} eingegangene Datei wartet auf die Virenprüfung und ist bis dahin gesperrt.',
            '{n} eingegangene Dateien warten auf die Virenprüfung und sind bis dahin gesperrt.',
            data.virus_scan.quarantine.pending,
          )}
        </Alert>
      )}
      {!!data.virus_scan?.quarantine?.infected && (
        <Alert kind="error">
          {tn(
            'In {n} eingegangenen Datei wurde Schadsoftware gefunden. Sie bleibt gesperrt.',
            'In {n} eingegangenen Dateien wurde Schadsoftware gefunden. Sie bleiben gesperrt.',
            data.virus_scan.quarantine.infected,
          )}
        </Alert>
      )}
      {self?.result && <LastResult result={self.result} />}
      {self?.enabled ? (
        pending ? (
          <Alert kind="info">
            {t(
              'Die Aktualisierung läuft. HUBIplan ist dabei einige Minuten nicht erreichbar; diese Seite fragt von selbst nach.',
            )}
          </Alert>
        ) : (
          update && (
            <StartUpdate
              version={update.version}
              onStarted={(s) => setData({ ...data, selfupdate: s })}
            />
          )
        )
      ) : (
        <p className="muted">
          {t(
            'Das Selbstupdate ist auf diesem Server nicht eingeschaltet. Aktualisiert wird dann von Hand durch den Betreiber (docs/betrieb.md).',
          )}
        </p>
      )}
    </div>
  )
}

function LastResult({ result }: { result: NonNullable<SelfUpdate['result']> }) {
  const when = result.zeit ? formatDateTime(result.zeit) : ''
  const version = result.version ?? ''
  if (result.status === 'ok') {
    return (
      <Alert kind="success">
        {t('Letzte Aktualisierung auf {x} erfolgreich ({y}).', { x: version, y: when })}
      </Alert>
    )
  }
  if (result.status === 'fehler') {
    return (
      <Alert kind="error">
        {t('Letzte Aktualisierung auf {x} fehlgeschlagen ({y}).', { x: version, y: when })}{' '}
        {result.text}
      </Alert>
    )
  }
  // „laeuft“: Zwischenstand des Aktualisierers (Text vom Server)
  return result.text ? <p className="muted">{result.text}</p> : null
}

function StartUpdate({
  version,
  onStarted,
}: {
  version: string
  onStarted: (s: SelfUpdate) => void
}) {
  const [password, setPassword] = useState('')
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState<string | null>(null)
  async function start(ev: FormEvent) {
    ev.preventDefault()
    setBusy(true)
    setMessage(null)
    try {
      onStarted(await platformApi.startUpdate(version, password))
      setPassword('')
    } catch (err) {
      setMessage(errorMessage(err))
    } finally {
      setBusy(false)
    }
  }
  return (
    <form onSubmit={start}>
      <h3>{t('Jetzt aktualisieren')}</h3>
      <p>
        {t(
          'Der Server sichert zuerst die Datenbank, prüft die Signatur des Releases und spielt es dann ein. Schlägt etwas fehl, läuft die bisherige Version weiter. Der Betreiber bekommt dazu eine Sicherheitsmail.',
        )}
      </p>
      {message && <Alert kind="error">{message}</Alert>}
      <Field
        label={t('Dein Passwort zur Bestätigung')}
        type="password"
        autoComplete="current-password"
        required
        value={password}
        onChange={(e) => setPassword(e.target.value)}
        hint={t('Nur mit Zwei-Faktor-Anmeldung möglich.')}
      />
      <button type="submit" className="button button-primary" disabled={busy || !password}>
        {t('Auf {x} aktualisieren', { x: version })}
      </button>
    </form>
  )
}
