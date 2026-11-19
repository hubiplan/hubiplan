// Kartenscanner für Scanpersonal ohne Konto (Anmeldung A6, Konzept 3.11): öffnet sich über
// einen Scan-Link und kann nur Eintrittskarten prüfen, für den Einlass oder eine Zusatzleistung.
import { useCallback, useEffect, useRef, useState } from 'react'
import { useParams } from 'react-router-dom'
import { ApiError } from '../api/client.ts'
import { registrationApi } from '../api/registrations.ts'
import type { ScanHit, ScanPage, ScanResult } from '../api/registrations.ts'
import { CameraScanner, detectorClass } from '../components/calendar/CheckIn.tsx'
import { PaidBadge } from '../components/calendar/PaidBadge.tsx'
import { formatDay } from '../components/calendar/time.ts'
import { errorMessage } from '../components/forms.ts'
import { Alert, Field, Loading } from '../components/ui.tsx'
import { confirmDialog } from '../components/dialog.ts'
import { euro } from '../api/finance.ts'
import { t } from '../i18n/index.ts'

function time(iso: string): string {
  return new Date(iso).toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' })
}

function dateTime(iso: string): string {
  const d = new Date(iso)
  return `${d.toLocaleDateString(undefined, { day: '2-digit', month: '2-digit' })} ${time(iso)}`
}

function ResultCard({
  res,
  page,
  onCash,
}: {
  res: ScanResult
  page: ScanPage
  onCash: (participant: number) => void
}) {
  const card = res.card
  const okTitle = {
    entry: () => t('Gültig: einlassen'),
    addon: () => t('Gültig: ausgeben'),
    material_out: () => t('Gültig: ausgeben'),
    material_return: () => t('Zurückgenommen'),
  }[page.kind]
  const title =
    res.result === 'paid'
      ? t('Bezahlt')
      : res.result === 'ok'
        ? okTitle()
        : res.result === 'already'
          ? t('Schon gescannt')
          : t('Nicht gültig')
  return (
    <div className={`scan-result stack-sm${res.valid ? ' scan-result-ok' : ''}`} role="status">
      <p className="scan-result-title">{title}</p>
      <p>
        {res.message}
        {res.result === 'already' && res.at && ` ${t('am {when}', { when: dateTime(res.at) })}`}
      </p>
      {card && (
        <>
          <p className="scan-result-name">{card.name}</p>
          <p>
            {card.birth_date
              ? t('geboren am {date}', { date: formatDay(card.birth_date, false) })
              : t('ohne Geburtsdatum')}
            {card.minor && ` · ${t('minderjährig')}`}
          </p>
          <p>
            {card.price_name} · {card.number} <PaidBadge state={card.paid_state} />
          </p>
          {page.cash && card.open_amount && card.id && (
            <div className="button-row">
              <button type="button" className="button" onClick={() => onCash(card.id ?? 0)}>
                {t('{amount} bar erhalten', { amount: euro(card.open_amount) })}
              </button>
            </div>
          )}
          {card.checked_in_at && (
            <p className="muted small">
              {t('eingelassen am {when}', { when: dateTime(card.checked_in_at) })}
            </p>
          )}
          {(card.materials ?? []).length > 0 && (
            <ul className="plain-list">
              {(card.materials ?? []).map((m) => (
                <li key={`m${m.id}`}>
                  {m.name}{' '}
                  <span className="muted small">
                    {m.handed_out_at
                      ? t('ausgegeben am {when}', { when: dateTime(m.handed_out_at) })
                      : t('noch nicht ausgegeben')}
                    {m.returned_at &&
                      ` · ${t('zurück am {when}', { when: dateTime(m.returned_at) })}`}
                  </span>
                </li>
              ))}
            </ul>
          )}
          {card.bookings.length > 0 && (
            <ul className="plain-list">
              {card.bookings.map((b) => (
                <li key={b.id}>
                  {b.name}{' '}
                  <span className="muted small">
                    {b.redeemed_at
                      ? t('eingelöst am {when}', { when: dateTime(b.redeemed_at) })
                      : t('noch nicht eingelöst')}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </>
      )}
    </div>
  )
}

export function PublicScanPage() {
  const token = useParams().token ?? ''
  const [page, setPage] = useState<ScanPage | null>(null)
  const [invalid, setInvalid] = useState(false)
  const [unavailable, setUnavailable] = useState(false)
  const [camera, setCamera] = useState(false)
  const [code, setCode] = useState('')
  const [res, setRes] = useState<ScanResult | null>(null)
  const [failure, setFailure] = useState<string | null>(null)
  const busy = useRef(false)
  const [term, setTerm] = useState('')
  const [hits, setHits] = useState<ScanHit[] | null>(null)

  useEffect(() => {
    let alive = true
    registrationApi
      .scanPage(token)
      .then((d) => alive && setPage(d))
      .catch((err) => {
        if (!alive) return
        if (err instanceof ApiError && err.status >= 400 && err.status < 500) setInvalid(true)
        else setUnavailable(true)
      })
    return () => {
      alive = false
    }
  }, [token])

  const send = useCallback(
    async (value: string | number) => {
      const text = typeof value === 'number' ? '' : value.trim()
      if ((typeof value !== 'number' && !text) || busy.current) return
      busy.current = true
      setFailure(null)
      try {
        setRes(
          await registrationApi.scan(
            token,
            typeof value === 'number' ? { participant: value } : { code: text },
          ),
        )
        if (navigator.vibrate) navigator.vibrate(120)
      } catch (err) {
        if (err instanceof ApiError && err.status === 404) setInvalid(true)
        else setFailure(errorMessage(err))
      } finally {
        busy.current = false
      }
    },
    [token],
  )

  return (
    <main className="login-page">
      <div className="card public-photo stack-sm scan-page">
        <h1>{page ? page.event : t('Eintrittskarten scannen')}</h1>
        {invalid && <Alert kind="error">{t('Dieser Link ist ungültig oder abgelaufen.')}</Alert>}
        {unavailable && (
          <Alert kind="error">
            {t('Die Seite kann gerade nicht geladen werden. Bitte später erneut versuchen.')}
          </Alert>
        )}
        {!page && !invalid && !unavailable && <Loading />}
        {page && !invalid && (
          <>
            <p className="muted">
              {page.organization} · {formatDay(page.starts_at.slice(0, 10), false)}
              <br />
              {t('Station: {station}', { station: page.station })} · {page.label}
              {page.cash && ` · ${t('Kasse')}${page.cashier ? `: ${page.cashier}` : ''}`}
            </p>
            <div aria-live="polite">
              {res && (
                <ResultCard
                  res={res}
                  page={page}
                  onCash={(id) => {
                    const amount = res.card?.open_amount
                    if (!amount) return
                    void confirmDialog({
                      final: false,
                      title: t('{amount} bar erhalten?', { amount: euro(amount) }),
                      confirmLabel: t('Barzahlung buchen'),
                    }).then(async (ok) => {
                      if (!ok) return
                      setFailure(null)
                      try {
                        setRes(
                          await registrationApi.scanCash(token, {
                            participant: id,
                            request_key: crypto.randomUUID(),
                          }),
                        )
                      } catch (err) {
                        setFailure(errorMessage(err))
                      }
                    })
                  }}
                />
              )}
              {failure && <Alert kind="error">{failure}</Alert>}
            </div>
            {detectorClass() ? (
              <div className="button-row">
                <button
                  type="button"
                  className="button"
                  aria-pressed={camera}
                  onClick={() => setCamera(!camera)}
                >
                  {camera ? t('Kamera aus') : t('Mit der Kamera scannen')}
                </button>
              </div>
            ) : (
              <p className="muted small">
                {t(
                  'Dieser Browser kann keine QR-Codes lesen. Bitte den Code mit einem Handscanner oder von Hand eingeben, oder einen anderen Browser (z. B. Chrome) nutzen.',
                )}
              </p>
            )}
            {camera && <CameraScanner onCode={(value) => void send(value)} />}
            <form
              onSubmit={(e) => {
                e.preventDefault()
                const value = code
                setCode('')
                void send(value)
              }}
            >
              <Field
                label={t('Code der Eintrittskarte')}
                value={code}
                autoComplete="off"
                enterKeyHint="go"
                onChange={(e) => setCode(e.target.value)}
              />
              <div className="button-row">
                <button type="submit" className="button button-ghost" disabled={!code.trim()}>
                  {t('Prüfen')}
                </button>
              </div>
            </form>
            {page.allow_search && (
              <form
                className="stack-sm"
                onSubmit={async (e) => {
                  e.preventDefault()
                  setFailure(null)
                  try {
                    setHits((await registrationApi.scanSearch(token, term)).results)
                  } catch (err) {
                    setFailure(errorMessage(err))
                  }
                }}
              >
                <h2>{t('Ohne Karte')}</h2>
                <Field
                  label={t('Name suchen')}
                  hint={t('Ab drei Buchstaben. Bitte den Ausweis prüfen, bevor du einbuchst.')}
                  value={term}
                  autoComplete="off"
                  onChange={(e) => setTerm(e.target.value)}
                />
                <div className="button-row">
                  <button
                    type="submit"
                    className="button button-ghost"
                    disabled={term.trim().length < 3}
                  >
                    {t('Suchen')}
                  </button>
                </div>
                {hits && hits.length === 0 && <p className="muted">{t('Niemand gefunden.')}</p>}
                {hits && hits.length > 0 && (
                  <ul className="plain-list stack-sm">
                    {hits.map((h) => (
                      <li key={h.id}>
                        <strong>{h.name}</strong>{' '}
                        <span className="muted small">
                          {h.birth_date
                            ? t('geboren am {date}', { date: formatDay(h.birth_date, false) })
                            : t('ohne Geburtsdatum')}
                          {' · '}
                          {h.price_name} · {h.number}
                          {h.checked_in_at &&
                            ` · ${t('eingelassen am {when}', { when: dateTime(h.checked_in_at) })}`}
                        </span>{' '}
                        <button
                          type="button"
                          className="button small"
                          onClick={() => {
                            setHits(null)
                            setTerm('')
                            void send(h.id)
                          }}
                        >
                          {page.kind === 'entry'
                            ? t('Einbuchen')
                            : page.kind === 'addon'
                              ? t('Einlösen')
                              : page.kind === 'material_out'
                                ? t('Ausgeben')
                                : t('Zurücknehmen')}
                        </button>
                      </li>
                    ))}
                  </ul>
                )}
              </form>
            )}
          </>
        )}
      </div>
    </main>
  )
}
