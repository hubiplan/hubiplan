import { useState } from 'react'
import { peeringApi } from '../../api/peering.ts'
import { confirmDialog } from '../../components/dialog.ts'
import { errorMessage } from '../../components/forms.ts'
import { Alert, Field } from '../../components/ui.tsx'
import { useActiveOrg } from '../../org/OrgContext.tsx'
import { t } from '../../i18n/index.ts'

export function MoveCard({ onMoved }: { onMoved: () => void }) {
  const org = useActiveOrg()
  const [url, setUrl] = useState('')
  const [target, setTarget] = useState<{ base_url: string; fingerprint: string } | null>(null)
  const [fingerprint, setFingerprint] = useState('')
  const [err, setErr] = useState<string | null>(null)
  const [result, setResult] = useState<{ done: number; failed: string[] } | null>(null)
  const [busy, setBusy] = useState(false)
  async function inspect() {
    setErr(null)
    setTarget(null)
    setBusy(true)
    try {
      setTarget(await peeringApi.moveInspect(org.id, url.trim()))
    } catch (e) {
      setErr(errorMessage(e))
    } finally {
      setBusy(false)
    }
  }
  async function announce() {
    if (!target) return
    const ok = await confirmDialog({
      final: true,
      title: t('Umzug melden?'),
      message:
        t('Alle Gegenstellen koppeln sich danach mit der neuen Instanz. Diese Instanz nimmt für ') +
        t('die Kopplungen dieser Einheit nichts mehr an. Das lässt sich nicht rückgängig machen.'),
      confirmLabel: t('Umzug melden'),
      danger: true,
    })
    if (!ok) return
    setErr(null)
    setBusy(true)
    try {
      setResult(await peeringApi.move(org.id, target.base_url, fingerprint))
      onMoved()
    } catch (e) {
      setErr(errorMessage(e))
    } finally {
      setBusy(false)
    }
  }
  return (
    <details className="card card-wide">
      <summary>
        <strong>{t('Umzug auf eine andere Instanz')}</strong>
      </summary>
      <ol className="small">
        <li>{t('Unter Datenübernahme diese Einheit exportieren. Die Kopplungen ziehen mit.')}</li>
        <li>{t('Die Datei auf der neuen Instanz einlesen lassen.')}</li>
        <li>
          {t(
            'Hier die neue Instanz eintragen, den Fingerabdruck vergleichen und den Umzug melden.',
          )}
        </li>
      </ol>
      {result ? (
        <Alert kind={result.failed.length ? 'error' : 'success'}>
          {result.done} {t('Gegenstelle(n) haben den Umzug übernommen.')}
          {result.failed.length > 0 && t(' Nicht erreicht: {x}', { x: result.failed.join('; ') })}
        </Alert>
      ) : (
        <>
          <Field
            label={t('Adresse der neuen Instanz')}
            type="url"
            value={url}
            placeholder="https://"
            onChange={(e) => {
              setUrl(e.target.value)
              setTarget(null)
            }}
          />
          {target && (
            <>
              <p className="small">
                {t('Fingerabdruck von {base_url}:', { base_url: target.base_url })}{' '}
                <code>{target.fingerprint}</code>
              </p>
              <Field
                label={t('Fingerabdruck zur Bestätigung')}
                hint={t('Von der Plattformverwaltung der neuen Instanz auf anderem Weg erfragen.')}
                value={fingerprint}
                onChange={(e) => setFingerprint(e.target.value)}
              />
            </>
          )}
          {err && <Alert kind="error">{err}</Alert>}
          <div className="button-row">
            {!target ? (
              <button
                type="button"
                className="button"
                disabled={busy || !url.trim()}
                onClick={() => void inspect()}
              >
                {t('Neue Instanz prüfen')}
              </button>
            ) : (
              <button
                type="button"
                className="button button-danger"
                disabled={busy || !fingerprint.trim()}
                onClick={() => void announce()}
              >
                {t('Umzug melden')}
              </button>
            )}
          </div>
        </>
      )}
    </details>
  )
}
