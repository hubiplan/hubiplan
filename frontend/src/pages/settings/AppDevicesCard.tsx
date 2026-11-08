import { QRCodeSVG } from 'qrcode.react'
import { useEffect, useState } from 'react'
import { useLoad, useQueryLoad } from '../../components/forms.ts'
import { LoadError } from '../../components/ui.tsx'
import { devicesApi } from '../../api/devices.ts'
import { HowTo } from '../../learning/Aids.tsx'
import { confirmDialog } from '../../components/dialog.ts'
import type { AppDevice, PairingCode } from '../../api/devices.ts'
import { locale, t } from '../../i18n/index.ts'

function formatDate(value: string): string {
  return new Date(value).toLocaleString(locale(), { dateStyle: 'medium', timeStyle: 'short' })
}

// Mein Konto: HUBIplan-App mit dem Konto verbinden und Geräte abmelden.
export function AppDevicesCard() {
  const access = useLoad(() => devicesApi.hasPortal(), [])
  const list = useQueryLoad(() => devicesApi.list(), [access.data], access.data === true)
  const devices = list.data ?? []
  const load = list.reload
  const [pairing, setPairing] = useState<PairingCode | null>(null)
  // Nach dem Scannen: welches Gerät hat sich verbunden? (ein fremdes fällt so sofort auf)
  const [connected, setConnected] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!pairing) return
    let active = true
    // Höchstens ein Abruf gleichzeitig; nach Ablauf des Codes nicht weiter fragen
    // (Gesamtaudit 30.10., WEB-P02)
    let busy = false
    const expires = Date.parse(pairing.expires_at)
    const timer = window.setInterval(() => {
      if (busy) return
      if (Number.isFinite(expires) && Date.now() > expires) {
        window.clearInterval(timer)
        setPairing(null)
        setError(t('Der QR-Code ist abgelaufen. Bitte bei Bedarf einen neuen erzeugen.'))
        return
      }
      busy = true
      devicesApi
        .pairingStatus(pairing.id)
        .then(async (status) => {
          if (!active || !status.used) return
          setConnected(status.device ?? t('unbekanntes Gerät'))
          setPairing(null)
          await load()
        })
        .catch(() => {
          // Nächster Versuch beim nächsten Takt
        })
        .finally(() => {
          busy = false
        })
    }, 3000)
    return () => {
      active = false
      window.clearInterval(timer)
    }
  }, [pairing, load])

  if (access.error)
    return (
      <section className="card">
        <h2>{t('App auf dem Telefon')}</h2>
        <LoadError message={access.error} onRetry={() => void access.reload()} />
      </section>
    )
  if (access.data === null) return null
  if (access.data === false)
    return (
      <section className="card">
        <h2>{t('App auf dem Telefon')}</h2>
        <p className="muted">
          {t(
            'Die App zeigt deinen Mitgliederbereich. Dein Konto hat noch keinen Zugang dazu: Es muss mit deiner Mitgliedschaft verknüpft sein, und dein Verein muss den Mitgliederbereich eingeschaltet haben. Wende dich dafür an deinen Vorstand.',
          )}
        </p>
      </section>
    )

  async function createCode() {
    setError(null)
    setConnected(null)
    try {
      setPairing(await devicesApi.pairingCode())
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    }
  }

  async function remove(device: AppDevice) {
    if (
      !(await confirmDialog(
        t('„{name}“ abmelden? Die App dort muss neu verbunden werden.', { name: device.name }),
      ))
    )
      return
    setError(null)
    try {
      await devicesApi.remove(device.id)
      await load()
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    }
  }

  async function lockAdmin(device: AppDevice) {
    setError(null)
    try {
      await devicesApi.lockAdmin(device.id)
      await load()
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    }
  }

  return (
    <div className="card">
      <h2>{t('App auf dem Telefon')}</h2>
      <p className="muted small">
        {t(
          'Mit der HUBIplan-App für Android siehst du Termine im Kalender deines Telefons, sagst mit einem Fingertipp zu oder ab und bekommst Mitteilungen deines Vereins.',
        )}
      </p>
      <HowTo k="how_app_devices" />
      {error && (
        <p className="alert alert-error" role="alert">
          {error}
        </p>
      )}
      {connected && (
        <p className="alert alert-success" role="status">
          {t('Verbunden:')} <strong>{connected}</strong>
          {t('. Warst du das nicht? Dann das Gerät unten sofort abmelden.')}
        </p>
      )}
      {pairing ? (
        <div className="totp-setup">
          <QRCodeSVG value={pairing.url} size={200} marginSize={2} />
          <p className="muted">
            {t(
              'In der App auf „Mit QR-Code verbinden“ tippen und diesen Code scannen. Er gilt bis  {x} Uhr und nur einmal.',
              { x: formatDate(pairing.expires_at) },
            )}
          </p>
          <button type="button" className="button button-ghost" onClick={() => setPairing(null)}>
            {t('Schließen')}
          </button>
        </div>
      ) : (
        <button type="button" className="button button-primary" onClick={() => void createCode()}>
          {t('App verbinden')}
        </button>
      )}
      <h3>{t('Angemeldete Geräte')}</h3>
      {list.error ? (
        <LoadError message={list.error} onRetry={() => void load()} />
      ) : list.loading && !list.data ? (
        <p role="status">{t('Lädt …')}</p>
      ) : devices.length === 0 ? (
        <p className="muted">{t('Noch kein Gerät verbunden.')}</p>
      ) : (
        <ul className="item-list">
          {devices.map((d) => (
            <li key={d.id} className="item-row">
              <div className="item-row-info">
                <span>
                  <strong>{d.name}</strong>{' '}
                  <span className="muted small">
                    {t('zuletzt aktiv')} {formatDate(d.last_seen_at)}
                  </span>
                </span>
                {d.admin_until && (
                  <span className="small">
                    {t('Verwaltung freigeschaltet bis')} {formatDate(d.admin_until)}
                  </span>
                )}
              </div>
              <div className="button-row">
                {d.admin_until && (
                  <button
                    type="button"
                    className="button button-ghost"
                    onClick={() => void lockAdmin(d)}
                  >
                    {t('Verwaltung sperren')}
                  </button>
                )}
                <button
                  type="button"
                  className="button button-ghost"
                  onClick={() => void remove(d)}
                >
                  {t('Abmelden')}
                </button>
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
