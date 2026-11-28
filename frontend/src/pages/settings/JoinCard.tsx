import { useState } from 'react'
import { levelsOf, peeringApi } from '../../api/peering.ts'
import type { Levels, PeeringPreview } from '../../api/peering.ts'
import { confirmDialog } from '../../components/dialog.ts'
import { errorMessage } from '../../components/forms.ts'
import { Alert } from '../../components/ui.tsx'
import { useActiveOrg } from '../../org/OrgContext.tsx'
import { t } from '../../i18n/index.ts'
import { PacketToggles } from './PacketToggles.tsx'

export function JoinCard({ onJoined }: { onJoined: () => void }) {
  const org = useActiveOrg()
  const [code, setCode] = useState('')
  const [preview, setPreview] = useState<PeeringPreview | null>(null)
  const [levels, setLevels] = useState<Levels>({})
  const [err, setErr] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  async function check() {
    setErr(null)
    setBusy(true)
    try {
      const p = await peeringApi.inspect(org.id, code)
      setPreview(p)
      setLevels(levelsOf(p.send))
    } catch (e) {
      setErr(errorMessage(e))
      setPreview(null)
    } finally {
      setBusy(false)
    }
  }

  async function join() {
    if (!preview) return
    const ok = await confirmDialog({
      message: t(
        '{name} unter „{name2}“ ({base_url}) koppeln? Die andere Seite muss noch bestätigen.',
        { name: org.name, name2: preview.remote.name, base_url: preview.remote.base_url },
      ),
      confirmLabel: t('Koppeln'),
      danger: false,
    })
    if (!ok) return
    setBusy(true)
    try {
      await peeringApi.join(org.id, code, levels)
      setCode('')
      setPreview(null)
      onJoined()
    } catch (e) {
      setErr(errorMessage(e))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="card card-wide">
      <h3>{t('Unter eine ferne Einheit koppeln')}</h3>
      <p className="muted small">
        {t(
          'Den Kopplungscode bekommst du vom Vorstand der Einheit darüber. Vor dem Koppeln siehst du, wer die andere Seite ist und welche Daten fließen.',
        )}
      </p>
      <label className="field">
        <span>{t('Kopplungscode')}</span>
        <textarea rows={3} value={code} onChange={(e) => setCode(e.target.value)} />
      </label>
      {err && <Alert kind="error">{err}</Alert>}
      {preview && (
        <>
          <p>
            <strong>{preview.remote.name}</strong> {t('auf')} {preview.remote.base_url}
            {preview.remote.country && t(' (Server in {x0})', { x0: preview.remote.country })}
            <br />
            <span className="muted small">
              {t('Fingerabdruck')} <code>{preview.remote.fingerprint}</code>
              {t('. Vergleiche ihn am besten am Telefon mit der anderen Seite.')}
            </span>
          </p>
          {preview.remote.kind === 'club' && (
            <Alert kind="info">
              {t(
                'Die andere Seite ist ein Verein. {name} erscheint dort als Untereinheit auf einer eigenen Instanz.',
                { name: org.name },
              )}
            </Alert>
          )}
          <PacketToggles choices={preview.send} levels={levels} onChange={setLevels} />
          <p className="muted small">
            {t('Von dort kann kommen:')}{' '}
            {preview.receive.map((r) => r.label).join(', ') || t('nichts')}.
          </p>
        </>
      )}
      <div className="button-row">
        <button
          type="button"
          className="button"
          disabled={busy || !code}
          onClick={() => void check()}
        >
          {t('Prüfen')}
        </button>
        {preview && (
          <button
            type="button"
            className="button button-primary"
            disabled={busy}
            onClick={() => void join()}
          >
            {t('Koppeln')}
          </button>
        )}
      </div>
    </div>
  )
}
