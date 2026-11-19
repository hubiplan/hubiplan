// Einlass vor Ort (Anmeldung A6, Konzept 3.11): Eintrittskarte scannen (Handscanner tippt den
// Code ins Feld oder Kamera) oder in der Liste abhaken. Die Kamera nutzt die QR-Erkennung des
// Browsers; wo sie fehlt (z. B. Safari auf dem iPhone), liest jsQR das Kamerabild.
import { useRowSort } from '../RowSort.tsx'
import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import type { CalendarBase } from '../../api/events.ts'
import { registrationApi } from '../../api/registrations.ts'
import type { CheckInResult, CheckInRow } from '../../api/registrations.ts'
import { errorMessage, useLoad } from '../forms.ts'
import { Alert, Field, Loading } from '../ui.tsx'
import { useRowSearch } from '../RowSearch.tsx'
import { PaidBadge } from './PaidBadge.tsx'
import { euro } from '../../api/finance.ts'
import { t } from '../../i18n/index.ts'

interface Detector {
  detect: (source: CanvasImageSource) => Promise<{ rawValue: string }[]>
}
type DetectorClass = new (options: { formats: string[] }) => Detector

function detectorClass(): DetectorClass | null {
  const w = window as unknown as { BarcodeDetector?: DetectorClass }
  return typeof w.BarcodeDetector === 'function' ? w.BarcodeDetector : null
}

/** Kamera-Scan möglich: Der Browser gibt die Kamera frei (mit oder ohne eigene QR-Erkennung). */
export function cameraAvailable(): boolean {
  return typeof navigator !== 'undefined' && !!navigator.mediaDevices?.getUserMedia
}

/** QR-Erkennung des Browsers, sonst jsQR (erst bei Bedarf geladen) auf einem verkleinerten Bild. */
async function qrDetector(): Promise<Detector> {
  const Klass = detectorClass()
  if (Klass) return new Klass({ formats: ['qr_code'] })
  const { default: jsQR } = await import('jsqr')
  const canvas = document.createElement('canvas')
  const ctx = canvas.getContext('2d', { willReadFrequently: true })
  return {
    detect: async (source) => {
      const v = source as HTMLVideoElement
      const w = v.videoWidth
      const h = v.videoHeight
      if (!ctx || !w || !h) return []
      const scale = Math.min(1, 800 / Math.max(w, h))
      canvas.width = Math.round(w * scale)
      canvas.height = Math.round(h * scale)
      ctx.drawImage(v, 0, 0, canvas.width, canvas.height)
      const image = ctx.getImageData(0, 0, canvas.width, canvas.height)
      const hit = jsQR(image.data, image.width, image.height, { inversionAttempts: 'dontInvert' })
      return hit ? [{ rawValue: hit.data }] : []
    },
  }
}

/** Abendkasse (Konzept 3.11): offene Rechnung bar kassieren, mit Quittung bei der Rechnung. */
function CashLink({ row }: { row: CheckInRow }) {
  if (!row.invoice_id || !['open', 'partly'].includes(row.paid_state)) return null
  return (
    <Link
      className="button button-ghost small"
      to={`/finanzen/rechnungen?rechnung=${row.invoice_id}`}
      aria-label={t('Bei {name} bar kassieren', { name: row.name })}
    >
      {t('Bar kassieren')}
      {row.outstanding ? ` (${euro(row.outstanding)})` : ''}
    </Link>
  )
}

function time(iso: string): string {
  return new Date(iso).toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' })
}

/** Kamera mit QR-Erkennung; ruft onCode einmal je neuem Code. */
export function CameraScanner({ onCode }: { onCode: (code: string) => void }) {
  const video = useRef<HTMLVideoElement>(null)
  const [error, setError] = useState<string | null>(null)
  const last = useRef({ code: '', at: 0 })
  useEffect(() => {
    if (!cameraAvailable()) return
    let detector: Detector | null = null
    let stream: MediaStream | null = null
    let timer = 0
    let stopped = false
    qrDetector()
      .then((d) => {
        detector = d
        return navigator.mediaDevices.getUserMedia({ video: { facingMode: 'environment' } })
      })
      .then((s) => {
        if (stopped) {
          s.getTracks().forEach((track) => track.stop())
          return
        }
        stream = s
        if (video.current) {
          video.current.srcObject = s
          void video.current.play()
        }
        timer = window.setInterval(() => {
          const v = video.current
          if (!v || v.readyState < 2 || !detector) return
          void detector.detect(v).then((codes) => {
            const value = codes[0]?.rawValue
            const now = Date.now()
            // Derselbe Code erst nach drei Sekunden wieder
            if (value && (value !== last.current.code || now - last.current.at > 3000)) {
              last.current = { code: value, at: now }
              onCode(value)
            }
          })
        }, 350)
      })
      .catch(() => setError(t('Die Kamera lässt sich nicht öffnen.')))
    return () => {
      stopped = true
      window.clearInterval(timer)
      stream?.getTracks().forEach((track) => track.stop())
    }
  }, [onCode])
  if (error) return <Alert kind="error">{error}</Alert>
  return <video ref={video} className="checkin-camera" muted playsInline aria-hidden="true" />
}

export function CheckInPanel({ base, eventId }: { base: CalendarBase; eventId: number }) {
  const { data, error, setData } = useLoad(
    () => registrationApi.checkIns(base, eventId),
    [base, eventId],
  )
  const [code, setCode] = useState('')
  const [result, setResult] = useState<CheckInResult | null>(null)
  const [failure, setFailure] = useState<string | null>(null)
  const [camera, setCamera] = useState(false)
  // Live: alle 10 Sekunden neu laden, solange die Liste offen ist (Scans vom Personal)
  useEffect(() => {
    const timer = window.setInterval(() => {
      if (document.hidden) return
      registrationApi
        .checkIns(base, eventId)
        .then((fresh) => setData(fresh))
        .catch(() => undefined)
    }, 10000)
    return () => window.clearInterval(timer)
  }, [base, eventId, setData])
  const rows = data?.participants ?? []
  const search = useRowSearch(rows, (r) => `${r.name} ${r.number} ${r.contact}`, t('Personen'))
  const sorting = useRowSort(search.shown, {
    name: (r) => r.name,
    number: (r) => r.number,
    paid: (r) => r.paid_state,
    entry: (r) => r.checked_in_at,
  })

  function apply(res: CheckInResult) {
    setResult(res)
    const row = res.participant
    if (!row) return
    setData((d) => {
      if (!d) return d
      const participants = d.participants.map((p) => (p.id === row.id ? row : p))
      return {
        ...d,
        participants,
        checked_in: participants.filter((p) => p.checked_in_at).length,
      }
    })
  }

  async function send(body: { code?: string; participant?: number; undo?: boolean }) {
    setFailure(null)
    try {
      apply(await registrationApi.checkIn(base, eventId, body))
    } catch (err) {
      setFailure(errorMessage(err))
    }
  }

  async function scan(value: string) {
    const text = value.trim()
    if (!text) return
    setCode('')
    await send({ code: text })
  }

  if (error) return <Alert kind="error">{error}</Alert>
  if (!data) return <Loading small />
  const good = result && (result.result === 'ok' || result.result === 'undone')
  const unpaid = result?.participant && ['open', 'partly'].includes(result.participant.paid_state)
  return (
    <div className="checkin">
      <p>{t('{n} von {total} Personen eingelassen.', { n: data.checked_in, total: data.count })}</p>
      {data.can_edit && (
        <form
          className="checkin-scan"
          onSubmit={(e) => {
            e.preventDefault()
            void scan(code)
          }}
        >
          <Field
            label={t('Code der Eintrittskarte')}
            hint={t('Mit einem Handscanner hier hineinscannen; Enter lässt ein.')}
            value={code}
            autoComplete="off"
            enterKeyHint="go"
            onChange={(e) => setCode(e.target.value)}
          />
          <div className="button-row">
            <button type="submit" className="button" disabled={!code.trim()}>
              {t('Einlassen')}
            </button>
            {cameraAvailable() && (
              <button
                type="button"
                className="button button-ghost"
                aria-pressed={camera}
                onClick={() => setCamera(!camera)}
              >
                {camera ? t('Kamera aus') : t('Mit der Kamera scannen')}
              </button>
            )}
          </div>
          {camera && <CameraScanner onCode={(value) => void scan(value)} />}
        </form>
      )}
      <div aria-live="polite">
        {result && (
          <Alert kind={good ? 'success' : 'error'}>
            {result.message}
            {result.participant && (
              <>
                {' '}
                <strong>{result.participant.name}</strong> · {result.participant.price_name}
                {result.result === 'already' &&
                  result.participant.checked_in_at &&
                  ` · ${t('um {time}', { time: time(result.participant.checked_in_at) })}`}
                {unpaid && ` · ${t('Zahlung offen')}`}
                {result.participant.minor && ` · ${t('minderjährig')}`}
                {unpaid && data.can_cash && (
                  <>
                    {' '}
                    <CashLink row={result.participant} />
                  </>
                )}
              </>
            )}
          </Alert>
        )}
        {failure && <Alert kind="error">{failure}</Alert>}
      </div>
      {search.field}
      <div className="table-wrap">
        <table className="table">
          <thead>
            <tr>
              {sorting.head('name', t('Name'))}
              {sorting.head('number', t('Anmeldung'))}
              {sorting.head('paid', t('Stand'))}
              {sorting.head('entry', t('Einlass'))}
            </tr>
          </thead>
          <tbody>
            {sorting.rows.map((r: CheckInRow) => (
              <tr key={r.id}>
                <td>
                  {r.name}
                  <div className="muted small">{r.price_name}</div>
                  {(r.bookings ?? []).map((b, i) => (
                    <div key={i} className="muted small">
                      {b.name}
                      {b.redeemed_at &&
                        ` · ${t('eingelöst um {time}', { time: time(b.redeemed_at) })}`}
                    </div>
                  ))}
                </td>
                <td>
                  {r.number}
                  <div className="muted small">{r.contact}</div>
                </td>
                <td>
                  <PaidBadge state={r.paid_state} />
                  {data.can_cash && (
                    <div>
                      <CashLink row={r} />
                    </div>
                  )}
                </td>
                <td>
                  {r.checked_in_at ? (
                    <>
                      <span className="badge badge-yes">
                        {t('da seit {time}', { time: time(r.checked_in_at) })}
                      </span>{' '}
                      {r.checked_in_via && <span className="muted small">{r.checked_in_via} </span>}
                      {data.can_edit && (
                        <button
                          type="button"
                          className="button button-ghost small"
                          aria-label={t('Einlass von {name} zurücknehmen', { name: r.name })}
                          onClick={() => void send({ participant: r.id, undo: true })}
                        >
                          {t('Zurücknehmen')}
                        </button>
                      )}
                    </>
                  ) : (
                    data.can_edit && (
                      <button
                        type="button"
                        className="button button-ghost small"
                        aria-label={t('{name} einlassen', { name: r.name })}
                        onClick={() => void send({ participant: r.id })}
                      >
                        {t('Einlassen')}
                      </button>
                    )
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
