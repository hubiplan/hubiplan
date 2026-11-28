// Einstellungen › Verbund: Kopplungen mit Einheiten auf anderen HUBIplan-Instanzen.
import { useState } from 'react'
import { peeringApi } from '../../api/peering.ts'
import { errorMessage, formatDateTime, useLoad } from '../../components/forms.ts'
import { Alert, LoadError, Loading } from '../../components/ui.tsx'
import { useActiveOrg } from '../../org/OrgContext.tsx'
import { HowTo } from '../../learning/Aids.tsx'
import { t } from '../../i18n/index.ts'
import { JoinCard } from './JoinCard.tsx'
import { SpinOffCard } from './SpinOffCard.tsx'
import { CouplingCard } from './CouplingCard.tsx'
import { MoveCard } from './MoveCard.tsx'

export function PeeringPage() {
  const org = useActiveOrg()
  const { data, error, reload } = useLoad(() => peeringApi.overview(org.id), [org.id])
  if (error) return <LoadError message={error} onRetry={() => void reload()} />
  if (!data) return <Loading />
  if (!data.enabled) {
    return (
      <div className="card card-wide">
        <h2>{t('Verbund')}</h2>
        <Alert kind="info">
          {t(
            'Der Verbund mit anderen HUBIplan-Instanzen ist auf dieser Instanz nicht eingeschaltet. Alles läuft wie bisher auf dieser Instanz. Einschalten kann ihn die Plattformverwaltung.',
          )}
        </Alert>
      </div>
    )
  }
  const open = data.couplings.filter((c) => c.state !== 'ended' && c.state !== 'moved')
  const closed = data.couplings.filter((c) => c.state === 'ended' || c.state === 'moved')
  return (
    <>
      <div className="card card-wide">
        <h2>{t('Verbund')}</h2>
        <p className="muted small">
          {t(
            'Einheiten auf anderen HUBIplan-Instanzen koppeln. Es fließen nur die Daten, die du unten freigibst, verschlüsselt und unterschrieben. Diese Instanz: {base_url} · Fingerabdruck',
            { base_url: data.instance?.base_url },
          )}{' '}
          <code>{data.instance?.fingerprint}</code>
        </p>
        <HowTo k="how_peering" />
      </div>
      {data.can_offer && <OfferCard />}
      {data.can_offer && org.type === 'club' && <SpinOffCard onChange={() => void reload()} />}
      {data.can_join && <JoinCard onJoined={() => void reload()} />}
      {open.map((c) => (
        <CouplingCard key={c.id} coupling={c} onChange={() => void reload()} />
      ))}
      {open.some((c) => c.state === 'active' || c.state === 'paused') && (
        <MoveCard onMoved={() => void reload()} />
      )}
      {closed.length > 0 && (
        <div className="card card-wide">
          <h3>{t('Frühere Kopplungen')}</h3>
          <ul className="plain-list">
            {closed.map((c) => (
              <li key={c.id}>
                {c.remote.name} ({c.remote.base_url}) · {c.state_label}
                {c.ended_at && t(' am {x}', { x: formatDateTime(c.ended_at) })}
              </li>
            ))}
          </ul>
        </div>
      )}
      {!data.can_offer && !data.can_join && open.length === 0 && (
        <Alert kind="info">
          {t(
            'Diese Einheit kann sich nicht mit anderen Instanzen koppeln: Nur Einheiten mit eigenem Datenbereich nehmen ferne Einheiten auf, und nur Einheiten mit eigenen Mitgliedern ohne Einheit darüber koppeln sich unter eine ferne Einheit.',
          )}
        </Alert>
      )}
    </>
  )
}

function OfferCard() {
  const org = useActiveOrg()
  const [code, setCode] = useState<{ code: string; expires_at: string } | null>(null)
  const [err, setErr] = useState<string | null>(null)
  async function create() {
    setErr(null)
    try {
      setCode(await peeringApi.createCode(org.id))
    } catch (e) {
      setErr(errorMessage(e))
    }
  }
  return (
    <div className="card card-wide">
      <h3>{t('Ferne Einheit aufnehmen')}</h3>
      {org.type === 'club' && (
        <p className="muted small">
          {t(
            'Für eine Untereinheit, die eine eigene HUBIplan-Instanz betreibt: Sie erscheint hier unter den Untereinheiten und teilt Stammdaten, Termine, Vorstand und Satzung.',
          )}
        </p>
      )}
      <p className="muted small">
        {t(
          'Erzeuge einen Kopplungscode und gib ihn auf anderem Weg (Telefon, Mail, Papier) an den Vorstand der anderen Einheit. Der Code gilt 48 Stunden und nur einmal. Danach bestätigst du die Anfrage hier.',
        )}
      </p>
      {code && (
        <>
          <label className="field">
            <span>{t('Kopplungscode')}</span>
            <textarea readOnly rows={4} value={code.code} onFocus={(e) => e.target.select()} />
          </label>
          <p className="muted small">
            {t('Gültig bis {x}.', { x: formatDateTime(code.expires_at) })}
          </p>
        </>
      )}
      {err && <Alert kind="error">{err}</Alert>}
      <div className="button-row">
        <button type="button" className="button" onClick={() => void create()}>
          {code ? t('Neuen Code erzeugen') : t('Kopplungscode erzeugen')}
        </button>
        {code && (
          <button
            type="button"
            className="button"
            onClick={() => void navigator.clipboard?.writeText(code.code)}
          >
            {t('Kopieren')}
          </button>
        )}
      </div>
    </div>
  )
}
