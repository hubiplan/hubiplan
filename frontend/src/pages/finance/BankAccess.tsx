// Bankanbindung: Bankzugang einrichten und Umsätze direkt bei der Bank abrufen.
//
// Die PIN steht nur im Speicher dieses Dialogs und geht mit jedem Schritt neu an den Server,
// der sie nicht speichert (finance/bank_fetch.py). Beim Schließen ist sie weg.
import { useEffect, useRef, useState } from 'react'
import type { FormEvent } from 'react'
import { bankAccessApi } from '../../api/bank.ts'
import type { BankAccess, BankAccessInput, BankStep, BankStepInput } from '../../api/bank.ts'
import { ApiError } from '../../api/client.ts'
import { confirmDialog } from '../../components/dialog.ts'
import { errorMessage, formatDate, formatDateTime, useLoad } from '../../components/forms.ts'
import { Modal } from '../../components/Modal.tsx'
import { Alert, Checkbox, Field, LoadError, SelectField } from '../../components/ui.tsx'
import { useActiveOrg } from '../../org/OrgContext.tsx'
import { t, tn } from '../../i18n/index.ts'

type Kind = 'setup' | 'fetch'
type Open =
  | { what: 'form'; access: BankAccess | null }
  | { what: 'step'; access: BankAccess; kind: Kind }
  | null

/** Abstand zwischen zwei Nachfragen bei der Bank, solange die Freigabe in der App aussteht */
const POLL_MS = 3000

export function BankAccessCard({
  onFetched,
}: {
  /** Nach einem Abruf: Text für die Meldung und der erste neue Auszug */
  onFetched: (text: string, firstId: number | null) => Promise<void>
}) {
  const org = useActiveOrg()
  const list = useLoad(() => bankAccessApi.list(org.id), [org.id])
  const [open, setOpen] = useState<Open>(null)
  const [error, setError] = useState<string | null>(null)

  if (list.error) return <LoadError message={list.error} onRetry={() => void list.reload()} />
  if (!list.data || !list.data.enabled) return null
  const accesses = list.data.accesses

  async function remove(access: BankAccess) {
    const ok = await confirmDialog({
      title: t('Bankzugang löschen?'),
      message: t(
        '„{name}“ wird gelöscht. Konten, Kontoauszüge und Buchungen bleiben. Umsätze lassen sich danach nur noch als Datei einlesen.',
        { name: access.name },
      ),
      confirmLabel: t('Löschen'),
      danger: true,
      final: false,
    })
    if (!ok) return
    setError(null)
    try {
      await bankAccessApi.remove(org.id, access.id)
      await list.reload()
    } catch (err) {
      setError(errorMessage(err))
    }
  }

  return (
    <div className="card card-wide">
      <h2>{t('Umsätze bei der Bank abrufen')}</h2>
      <p className="muted small">
        {t(
          'HUBIplan holt die Umsätze direkt bei der Bank (FinTS). Die PIN gibst du bei jedem Abruf neu ein; sie wird nicht gespeichert. Verlangt die Bank eine Freigabe, bestätigst du sie wie im Online-Banking.',
        )}
      </p>
      {error && <Alert kind="error">{error}</Alert>}
      {accesses.length === 0 ? (
        <p className="muted">{t('Noch kein Bankzugang eingerichtet.')}</p>
      ) : (
        <table className="table">
          <thead>
            <tr>
              <th>{t('Bankzugang')}</th>
              <th>{t('Konten')}</th>
              <th>{t('Stand')}</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {accesses.map((access) => (
              <tr key={access.id}>
                <td>
                  {access.name}
                  <div className="muted small">
                    {t('BLZ {code}', { code: access.bank_code })}
                    {access.tan_mechanism_name && ` · ${access.tan_mechanism_name}`}
                  </div>
                </td>
                <td>
                  {access.accounts.length === 0 ? (
                    <span className="muted">
                      {access.ready ? t('kein Konto mit passender IBAN') : '–'}
                    </span>
                  ) : (
                    access.accounts.map((account) => (
                      <div key={account.id}>
                        {account.name}
                        <span className="muted small">
                          {' '}
                          {account.fetched_until
                            ? t('· abgerufen bis {date}', {
                                date: formatDate(account.fetched_until),
                              })
                            : t('· noch nicht abgerufen')}
                        </span>
                      </div>
                    ))
                  )}
                </td>
                <td>
                  {access.paused_until ? (
                    <span className="field-error">
                      {t('ruht bis {time}', { time: formatDateTime(access.paused_until) })}
                    </span>
                  ) : !access.ready ? (
                    t('noch nicht eingerichtet')
                  ) : access.retry_needs_confirm ? (
                    <span className="field-error">{t('letzte Anmeldung abgelehnt')}</span>
                  ) : (
                    t('bereit')
                  )}
                </td>
                <td className="actions">
                  <span className="button-row">
                    {access.ready && access.accounts.length > 0 && (
                      <button
                        type="button"
                        className="button button-primary"
                        disabled={!!access.paused_until}
                        onClick={() => setOpen({ what: 'step', access, kind: 'fetch' })}
                      >
                        {t('Umsätze abrufen')}
                      </button>
                    )}
                    <button
                      type="button"
                      className="button button-ghost"
                      disabled={!!access.paused_until}
                      onClick={() => setOpen({ what: 'step', access, kind: 'setup' })}
                    >
                      {access.ready ? t('Neu einrichten') : t('Einrichten')}
                    </button>
                    <button
                      type="button"
                      className="button button-ghost"
                      onClick={() => setOpen({ what: 'form', access })}
                    >
                      {t('Bearbeiten')}
                    </button>
                    <button
                      type="button"
                      className="button button-ghost"
                      onClick={() => void remove(access)}
                    >
                      {t('Löschen')}
                    </button>
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      <div className="button-row">
        <button
          type="button"
          className="button button-ghost"
          onClick={() => setOpen({ what: 'form', access: null })}
        >
          {t('Bankzugang hinzufügen')}
        </button>
      </div>
      {open?.what === 'form' && (
        <AccessForm
          access={open.access}
          onClose={() => setOpen(null)}
          onSaved={async (saved) => {
            await list.reload()
            // Neuer Zugang oder geänderte Zugangsdaten: gleich bei der Bank anmelden
            setOpen(saved.ready ? null : { what: 'step', access: saved, kind: 'setup' })
          }}
        />
      )}
      {open?.what === 'step' && (
        <StepDialog
          access={open.access}
          kind={open.kind}
          onClose={() => {
            setOpen(null)
            void list.reload()
          }}
          onFetched={onFetched}
        />
      )}
    </div>
  )
}

function AccessForm({
  access,
  onClose,
  onSaved,
}: {
  access: BankAccess | null
  onClose: () => void
  onSaved: (access: BankAccess) => Promise<void>
}) {
  const org = useActiveOrg()
  const [name, setName] = useState(access?.name ?? '')
  const [bankCode, setBankCode] = useState(access?.bank_code ?? '')
  const [url, setUrl] = useState(access?.url ?? '')
  const [login, setLogin] = useState('')
  const [customer, setCustomer] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [fields, setFields] = useState<Record<string, string>>({})

  async function submit(e: FormEvent) {
    e.preventDefault()
    setBusy(true)
    setError(null)
    setFields({})
    const data: BankAccessInput = { name: name.trim(), bank_code: bankCode.trim(), url: url.trim() }
    // Beim Bearbeiten bleibt der Anmeldename, solange das Feld leer ist
    if (!access || login.trim()) data.login = login.trim()
    if (!access || customer.trim()) data.customer_id = customer.trim()
    try {
      const saved = access
        ? await bankAccessApi.update(org.id, access.id, data)
        : await bankAccessApi.create(org.id, data)
      await onSaved(saved)
    } catch (err) {
      if (err instanceof ApiError) setFields(err.fieldErrors)
      setError(errorMessage(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <Modal
      title={access ? t('Bankzugang bearbeiten') : t('Bankzugang hinzufügen')}
      onClose={onClose}
    >
      <form onSubmit={submit}>
        <p className="muted small">
          {t(
            'Die Adresse für FinTS (auch „HBCI mit PIN/TAN“) nennt deine Bank auf ihrer Webseite oder am Telefon. Anmeldename ist der, mit dem du dich im Online-Banking anmeldest.',
          )}
        </p>
        <Field
          label={t('Bezeichnung')}
          value={name}
          onChange={(e) => setName(e.target.value)}
          error={fields.name}
          placeholder={t('z. B. Sparkasse Musterstadt')}
          maxLength={100}
          required
        />
        <div className="grid-2">
          <Field
            label={t('Bankleitzahl')}
            value={bankCode}
            onChange={(e) => setBankCode(e.target.value)}
            error={fields.bank_code}
            inputMode="numeric"
            maxLength={11}
            hint={t('acht Ziffern; in der IBAN die Stellen 5 bis 12')}
            required
          />
          <Field
            label={t('FinTS-Adresse der Bank')}
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            error={fields.url}
            type="url"
            placeholder="https://"
            required
          />
        </div>
        <div className="grid-2">
          <Field
            label={t('Anmeldename')}
            value={login}
            onChange={(e) => setLogin(e.target.value)}
            error={fields.login}
            autoComplete="off"
            maxLength={100}
            required={!access}
            hint={
              access
                ? t('gespeichert (endet auf {hint}); leer lassen, um ihn zu behalten', {
                    hint: access.login_hint,
                  })
                : undefined
            }
          />
          <Field
            label={t('Kunden-ID (falls die Bank eine nennt)')}
            value={customer}
            onChange={(e) => setCustomer(e.target.value)}
            error={fields.customer_id}
            autoComplete="off"
            maxLength={100}
          />
        </div>
        {access?.ready && (
          <p className="muted small">
            {t(
              'Nach einer Änderung an Bankleitzahl, Adresse oder Anmeldename wird der Zugang neu eingerichtet.',
            )}
          </p>
        )}
        {error && <Alert kind="error">{error}</Alert>}
        <div className="button-row">
          <button type="submit" className="button button-primary" disabled={busy}>
            {access ? t('Speichern') : t('Weiter')}
          </button>
          <button type="button" className="button button-ghost" onClick={onClose}>
            {t('Abbrechen')}
          </button>
        </div>
      </form>
    </Modal>
  )
}

function errorCode(err: unknown): string {
  if (err instanceof ApiError && err.body && typeof err.body === 'object') {
    const code = (err.body as { code?: unknown }).code
    return typeof code === 'string' ? code : ''
  }
  return ''
}

function StepDialog({
  access,
  kind,
  onClose,
  onFetched,
}: {
  access: BankAccess
  kind: Kind
  onClose: () => void
  onFetched: (text: string, firstId: number | null) => Promise<void>
}) {
  const org = useActiveOrg()
  const [pin, setPin] = useState('')
  const [tan, setTan] = useState('')
  const [step, setStep] = useState<BankStep | null>(null)
  const [mechanism, setMechanism] = useState('')
  const [medium, setMedium] = useState('')
  const [confirmRetry, setConfirmRetry] = useState(false)
  const [needConfirm, setNeedConfirm] = useState(access.retry_needs_confirm)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  // Nach einem Fehler, der den Vorgang beendet: neu mit der PIN beginnen
  const [ended, setEnded] = useState(false)
  const alive = useRef(true)
  useEffect(() => {
    alive.current = true
    return () => {
      alive.current = false
    }
  }, [])

  const waiting = step?.status === 'tan' ? step : null
  const choosing = step?.status === 'choose' ? step : null
  const done = step?.status === 'done' ? step : null

  async function run(call: () => Promise<BankStep>) {
    setBusy(true)
    setError(null)
    try {
      const answer = await call()
      if (!alive.current) return
      setTan('')
      setStep(answer)
      if (answer.status === 'choose') {
        setMechanism(answer.mechanism || answer.mechanisms[0]?.id || '')
        setMedium(answer.media[0] ?? '')
      }
      if (answer.status === 'done' && answer.kind === 'fetch') {
        setPin('')
        const dup = answer.duplicates
          ? t(' {duplicates} waren schon eingelesen.', { duplicates: answer.duplicates })
          : ''
        await onFetched(
          t('{lines} Umsätze eingelesen.{dup}', { lines: answer.lines, dup }),
          answer.statements[0] ?? null,
        )
        // Das Ergebnis steht als Meldung auf der Seite, der neue Auszug ist ausgewählt
        onClose()
        return
      }
      if (answer.status === 'done') setPin('')
    } catch (err) {
      if (!alive.current) return
      const code = errorCode(err)
      setError(errorMessage(err))
      if (code === 'pin_retry' || code === 'pin') setNeedConfirm(true)
      setConfirmRetry(false)
      // Die Bank hat den Dialog beendet (falsche TAN, abgelaufen): zurück zur PIN
      if (waiting) {
        setStep(null)
        setEnded(true)
      }
    } finally {
      if (alive.current) setBusy(false)
    }
  }

  function begin(extra: Partial<BankStepInput> = {}) {
    const data: BankStepInput = { pin, confirm_retry: confirmRetry, ...extra }
    return run(() =>
      kind === 'setup'
        ? bankAccessApi.setup(org.id, access.id, data)
        : bankAccessApi.fetch(org.id, access.id, data),
    )
  }

  // Freigabe in der App: regelmäßig bei der Bank nachfragen, bis sie bestätigt ist
  const task = waiting?.task
  const decoupled = !!waiting?.decoupled
  useEffect(() => {
    if (!task || !decoupled || busy) return
    const timer = window.setTimeout(() => {
      void run(() => bankAccessApi.proceed(org.id, task, { pin }))
    }, POLL_MS)
    return () => window.clearTimeout(timer)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [task, decoupled, busy, step])

  function close() {
    // Ein wartender Dialog bei der Bank wird beendet, damit nichts liegen bleibt
    if (waiting) void bankAccessApi.cancel(org.id, waiting.task).catch(() => undefined)
    setPin('')
    onClose()
  }

  const title =
    kind === 'setup'
      ? t('Bankzugang einrichten: {name}', { name: access.name })
      : t('Umsätze abrufen: {name}', { name: access.name })

  return (
    <Modal title={title} onClose={close} guard={false}>
      {done ? (
        <>
          {done.kind === 'setup' && <SetupResult linked={done.linked} unlinked={done.unlinked} />}
          <div className="button-row">
            <button type="button" className="button button-primary" onClick={close}>
              {t('Fertig')}
            </button>
          </div>
        </>
      ) : waiting ? (
        <form
          onSubmit={(e) => {
            e.preventDefault()
            void run(() => bankAccessApi.proceed(org.id, waiting.task, { pin, tan: tan.trim() }))
          }}
        >
          <h3>{t('Freigabe')}</h3>
          {waiting.challenge && <p>{waiting.challenge}</p>}
          {waiting.image && (
            <p>
              <img src={waiting.image} alt={t('Grafik der Bank für die Freigabe')} />
            </p>
          )}
          {waiting.decoupled ? (
            <p role="status">
              {t(
                'Bitte bestätige den Abruf jetzt in der App deiner Bank. HUBIplan fragt alle paar Sekunden nach und macht dann von selbst weiter.',
              )}
            </p>
          ) : (
            <Field
              label={t('TAN')}
              value={tan}
              onChange={(e) => setTan(e.target.value)}
              autoComplete="one-time-code"
              inputMode="numeric"
              maxLength={100}
              autoFocus
              required
            />
          )}
          <p className="muted small">
            {t('Die Freigabe gilt bis {time}.', { time: formatDateTime(waiting.expires_at) })}
          </p>
          {error && <Alert kind="error">{error}</Alert>}
          <div className="button-row">
            {!waiting.decoupled && (
              <button type="submit" className="button button-primary" disabled={busy}>
                {t('Bestätigen')}
              </button>
            )}
            <button type="button" className="button button-ghost" onClick={close}>
              {t('Abbrechen')}
            </button>
          </div>
        </form>
      ) : choosing ? (
        <form
          onSubmit={(e) => {
            e.preventDefault()
            void begin({ mechanism, ...(choosing.need === 'medium' ? { medium } : {}) })
          }}
        >
          {choosing.need === 'mechanism' ? (
            <SelectField
              label={t('Wie gibst du bei dieser Bank Aufträge frei?')}
              value={mechanism}
              onChange={(e) => setMechanism(e.target.value)}
              hint={t('dasselbe Verfahren wie im Online-Banking')}
            >
              {choosing.mechanisms.map((m) => (
                <option key={m.id} value={m.id}>
                  {m.name}
                </option>
              ))}
            </SelectField>
          ) : (
            <SelectField
              label={t('Mit welchem Gerät gibst du frei?')}
              value={medium}
              onChange={(e) => setMedium(e.target.value)}
            >
              {choosing.media.map((m) => (
                <option key={m} value={m}>
                  {m}
                </option>
              ))}
            </SelectField>
          )}
          {error && <Alert kind="error">{error}</Alert>}
          <div className="button-row">
            <button type="submit" className="button button-primary" disabled={busy}>
              {t('Weiter')}
            </button>
            <button type="button" className="button button-ghost" onClick={close}>
              {t('Abbrechen')}
            </button>
          </div>
        </form>
      ) : (
        <form
          onSubmit={(e) => {
            e.preventDefault()
            setEnded(false)
            void begin()
          }}
        >
          <p className="muted small">
            {kind === 'setup'
              ? t(
                  'HUBIplan meldet sich bei der Bank an, fragt das Freigabeverfahren ab und verbindet die Konten, deren IBAN unter Finanzen › Konten eingetragen ist.',
                )
              : t(
                  'Abgerufen werden die Umsätze seit dem letzten Abruf, beim ersten Mal die der letzten 90 Tage. Schon eingelesene Umsätze kommen nicht doppelt.',
                )}
          </p>
          {ended && !error && <Alert kind="error">{t('Bitte neu beginnen.')}</Alert>}
          <Field
            label={t('PIN für das Online-Banking')}
            type="password"
            value={pin}
            onChange={(e) => setPin(e.target.value)}
            autoComplete="off"
            maxLength={100}
            autoFocus
            required
            hint={t('wird nur für diesen Vorgang verwendet und nicht gespeichert')}
          />
          {needConfirm && (
            <Checkbox
              label={t(
                'Ich habe die PIN geprüft. Die letzte Anmeldung hat die Bank abgelehnt; nach drei falschen PINs sperren viele Banken den Zugang.',
              )}
              checked={confirmRetry}
              onChange={setConfirmRetry}
            />
          )}
          {error && <Alert kind="error">{error}</Alert>}
          <div className="button-row">
            <button
              type="submit"
              className="button button-primary"
              disabled={busy || (needConfirm && !confirmRetry)}
            >
              {busy
                ? t('Verbindung zur Bank …')
                : kind === 'setup'
                  ? t('Bei der Bank anmelden')
                  : t('Umsätze abrufen')}
            </button>
            <button type="button" className="button button-ghost" onClick={close}>
              {t('Abbrechen')}
            </button>
          </div>
        </form>
      )}
    </Modal>
  )
}

function SetupResult({ linked, unlinked }: { linked: string[]; unlinked: string[] }) {
  return (
    <>
      {linked.length > 0 ? (
        <Alert kind="success">
          {tn(
            'Der Bankzugang ist eingerichtet. {n} Konto ist verbunden.',
            'Der Bankzugang ist eingerichtet. {n} Konten sind verbunden.',
            linked.length,
          )}
        </Alert>
      ) : (
        <Alert kind="error">
          {t(
            'Die Anmeldung hat geklappt, aber keines deiner Konten hat eine IBAN, die die Bank zu diesem Zugang nennt. Bitte unter Finanzen › Konten die IBAN eintragen und den Zugang neu einrichten.',
          )}
        </Alert>
      )}
      {unlinked.length > 0 && (
        <p className="muted small">
          {t('Bei der Bank gibt es außerdem: {ibans}. Dazu ist in HUBIplan kein Konto angelegt.', {
            ibans: unlinked.join(', '),
          })}
        </p>
      )}
    </>
  )
}
