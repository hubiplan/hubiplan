// Stand des eigenen Mitgliedsantrags über den Link aus der Mail (ohne Anmeldung):
// bestätigen (?bestaetigen=1), zurückziehen (?zurueckziehen=1), unterschreiben, PDF.
import { useEffect, useRef, useState } from 'react'
import { useParams, useSearchParams } from 'react-router-dom'
import { ApiError } from '../../api/client.ts'
import { joinApi } from '../../api/admission.ts'
import type { JoinStatus } from '../../api/admission.ts'
import type { SignatureInput } from '../../api/finance.ts'
import { SignaturePad } from '../../components/SignaturePad.tsx'
import { errorMessage } from '../../components/forms.ts'
import { Logo } from '../../components/Logo.tsx'
import { Alert, Loading } from '../../components/ui.tsx'
import { t } from '../../i18n/index.ts'

function statusText(s: JoinStatus): string {
  switch (s.status) {
    case 'unconfirmed':
      return t('Bitte bestätige den Antrag, sonst wird er nach 48 Stunden gelöscht.')
    case 'unsigned':
      return t(
        'Der Verein braucht deine Unterschrift. Unterschreibe hier oder gib den ausgedruckten Antrag unterschrieben ab.',
      )
    case 'open':
      return t('Der Antrag liegt dem Verein vor. Du bekommst eine E-Mail, sobald entschieden ist.')
    case 'query':
      return t('Der Verein hat eine Rückfrage an dich geschickt. Bitte antworte auf die E-Mail.')
    case 'accepted':
      return t('Willkommen! Der Verein hat dich aufgenommen.')
    case 'rejected':
      return t('Der Verein hat den Antrag abgelehnt.')
    case 'withdrawn':
      return t('Du hast den Antrag zurückgezogen.')
  }
}

export function JoinStatusPage() {
  const token = useParams().token ?? ''
  const [search, setSearch] = useSearchParams()
  const [info, setInfo] = useState<JoinStatus | null>(null)
  const [invalid, setInvalid] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState('')
  const [busy, setBusy] = useState(false)
  const [asking, setAsking] = useState(search.get('zurueckziehen') === '1')
  const [signature, setSignature] = useState<SignatureInput | null>(null)
  const started = useRef(false)

  useEffect(() => {
    if (started.current) return
    started.current = true
    const confirm = search.get('bestaetigen') === '1'
    const load = async () => {
      try {
        let d = await joinApi.status(token)
        if (confirm && d.status === 'unconfirmed') {
          d = await joinApi.confirm(token)
          setNotice(t('Danke, der Antrag ist bestätigt.'))
          const next = new URLSearchParams(search)
          next.delete('bestaetigen')
          setSearch(next, { replace: true })
        }
        setInfo(d)
      } catch (err) {
        if (err instanceof ApiError && err.status === 404) setInvalid(true)
        else setError(errorMessage(err))
      }
    }
    void load()
  }, [token, search, setSearch])

  async function run(action: () => Promise<JoinStatus>, done: string) {
    setBusy(true)
    setError(null)
    setNotice('')
    try {
      setInfo(await action())
      setNotice(done)
      setAsking(false)
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <main className="login-page">
      <div className="card public-photo stack-sm">
        <div className="login-logo">
          <Logo name={info?.organization} logoUrl={null} />
        </div>
        <h1>{info ? t('Antrag {number}', { number: info.number }) : t('Mitgliedsantrag')}</h1>
        {invalid && (
          <Alert kind="error">
            {t(
              'Diesen Antrag gibt es nicht mehr. Unbestätigte Anträge werden nach 48 Stunden gelöscht; nach der Entscheidung des Vereins gilt der Link noch 30 Tage.',
            )}
          </Alert>
        )}
        {!info && !invalid && !error && <Loading />}
        {notice && <Alert kind="success">{notice}</Alert>}
        {error && <Alert kind="error">{error}</Alert>}
        {info && (
          <>
            <p className="muted">
              {info.name ? `${info.organization} · ${info.name}` : info.organization}
            </p>
            <p>
              <strong>{info.status_label}</strong>
            </p>
            <p>{statusText(info)}</p>
            <ul className="small">
              {info.summary.map((line) => (
                <li key={line}>{line}</li>
              ))}
            </ul>
            <div className="button-row">
              {info.status === 'unconfirmed' && (
                <button
                  type="button"
                  className="button button-primary"
                  disabled={busy}
                  onClick={() =>
                    void run(() => joinApi.confirm(token), t('Danke, der Antrag ist bestätigt.'))
                  }
                >
                  {t('Antrag bestätigen')}
                </button>
              )}
              {(info.pdf ?? info.status !== 'unconfirmed') && (
                <a className="button" href={joinApi.pdfUrl(token)} target="_blank" rel="noreferrer">
                  {t('Antrag als PDF')}
                </a>
              )}
              {info.can_withdraw && !asking && (
                <button type="button" className="button" onClick={() => setAsking(true)}>
                  {t('Mitgliedsantrag zurückziehen')}
                </button>
              )}
            </div>
            {info.can_sign && info.signature_required && !info.signed && (
              <section className="stack-sm">
                <h2>{t('Unterschreiben')}</h2>
                <SignaturePad onChange={setSignature} />
                <div className="button-row">
                  <button
                    type="button"
                    className="button button-primary"
                    disabled={busy || !signature}
                    onClick={() =>
                      signature &&
                      void run(
                        () => joinApi.sign(token, signature),
                        t('Danke, die Unterschrift ist gespeichert.'),
                      )
                    }
                  >
                    {t('Unterschrift speichern')}
                  </button>
                </div>
              </section>
            )}
            {asking && info.can_withdraw && (
              <Alert kind="info" as="div">
                <p>
                  {t(
                    'Willst du den Antrag wirklich zurückziehen? Das lässt sich nicht rückgängig machen.',
                  )}
                </p>
                <div className="button-row">
                  <button
                    type="button"
                    className="button button-danger"
                    disabled={busy}
                    onClick={() =>
                      void run(() => joinApi.withdraw(token), t('Der Antrag ist zurückgezogen.'))
                    }
                  >
                    {t('Ja, zurückziehen')}
                  </button>
                  <button type="button" className="button" onClick={() => setAsking(false)}>
                    {t('Abbrechen')}
                  </button>
                </div>
              </Alert>
            )}
          </>
        )}
      </div>
    </main>
  )
}
