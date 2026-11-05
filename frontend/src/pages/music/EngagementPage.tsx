import { useState } from 'react'
import { api, newRequestKey, requestBlob, saveBlob } from '../../api/client.ts'
import { todayIso } from '../../api/members.ts'
import { euro } from '../../api/finance.ts'
import { errorMessage, useLoad } from '../../components/forms.ts'
import { useDraftGuard } from '../../components/leaveGuard.ts'
import { Alert, Field } from '../../components/ui.tsx'
import { t } from '../../i18n/index.ts'
import { useActiveOrg } from '../../org/OrgContext.tsx'
import { MusicHeader } from './MusicLayout.tsx'

type Document = {
  id: number
  number: string
  kind: string
  status: string
  valid_until: string | null
  acceptance_note: string
  resolution_note?: string
  source_status?: string
  snapshot: { title?: string; total?: string; terms?: string; buyer?: { name: string } }
}

export function EngagementPage({ performance }: { performance: number }) {
  const org = useActiveOrg()
  return org.modules.includes('finance') && org.permissions.includes('finance.view') ? (
    <EngagementEditor performance={performance} />
  ) : (
    <Alert kind="error">{t('Dafür fehlt dir die Berechtigung.')}</Alert>
  )
}

function EngagementEditor({ performance }: { performance: number }) {
  const org = useActiveOrg()
  const url = `/api/orgs/${org.id}/music/performances/${performance}/engagement/`
  const load = useLoad(() => api.get<{ documents: Document[] }>(url), [org.id, performance])
  const [terms, setTerms] = useState('')
  const [until, setUntil] = useState(todayIso)
  const [note, setNote] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [keys] = useState(() => new Map<string, string>())
  const canEdit = org.permissions.includes('finance.edit') && org.permissions.includes('music.edit')
  useDraftGuard(!!terms || !!note)
  const statuses: Record<string, string> = {
    issued: t('Angebot ausgegeben'),
    accepted: t('Feste Zusage'),
    rejected: t('Abgelehnt'),
    cancelled: t('Aufgehoben'),
    superseded: t('Durch neueres Angebot ersetzt'),
  }
  async function act(action: string, document?: number) {
    setError('')
    setBusy(true)
    const identity = `${action}:${document || ''}:${terms}:${until}:${note}`
    if (!keys.has(identity)) keys.set(identity, newRequestKey())
    try {
      await api.post(
        url,
        { action, document, terms, valid_until: until, acceptance_note: note },
        keys.get(identity),
      )
      keys.delete(identity)
      setTerms('')
      setNote('')
      await load.reload()
    } catch (e) {
      setError(errorMessage(e))
    } finally {
      setBusy(false)
    }
  }
  const docs = load.data?.documents ?? []
  const current = docs.find((d) => d.kind === 'offer' && ['issued', 'accepted'].includes(d.status))
  return (
    <section className="stack music-page">
      <MusicHeader
        title={t('Angebote und Zusagen')}
        description={t(
          'Vom Auftrittsangebot über die dokumentierte Annahme zur Auftragsbestätigung.',
        )}
      />
      {(error || load.error) && <Alert kind="error">{error || load.error}</Alert>}
      <p>{current ? statuses[current.status] : t('Anfrage ohne feste Zusage')}</p>
      <p>
        {t(
          'Angebote übernehmen Auftraggeber, Termine und Bruttobeträge aus der Auftrittsabrechnung. Vereinbarungen vor der Ausgabe vollständig prüfen. Die PDF bleibt unverändert archiviert; das Dokument ist keine Rechnung.',
        )}
      </p>
      {canEdit && current?.status !== 'accepted' && (
        <form
          className="card stack"
          onSubmit={(e) => {
            e.preventDefault()
            void act('offer')
          }}
        >
          <h2>{t('Neues Angebot ausgeben')}</h2>
          <Field
            type="date"
            label={t('Angebot gültig bis')}
            value={until}
            min={todayIso()}
            required
            onChange={(e) => setUntil(e.target.value)}
          />
          <label>
            {t('Vereinbarungen')}
            <textarea
              required
              rows={7}
              maxLength={8000}
              value={terms}
              onChange={(e) => setTerms(e.target.value)}
            />
          </label>
          <button className="button button-primary" disabled={busy || !terms.trim()}>
            {t('Angebot als PDF ausgeben')}
          </button>
        </form>
      )}
      {canEdit && current && (
        <div className="card stack">
          <label>
            {t('Nachweis oder Begründung')}
            <textarea
              value={note}
              maxLength={1000}
              rows={3}
              onChange={(e) => setNote(e.target.value)}
            />
          </label>
          <div className="music-actions">
            {current.status === 'issued' && (
              <>
                <button
                  className="button button-primary"
                  disabled={busy || !note.trim()}
                  onClick={() => void act('accept', current.id)}
                >
                  {t('Annahme dokumentieren')}
                </button>
                <button
                  className="button button-ghost"
                  disabled={busy || !note.trim()}
                  onClick={() => void act('reject', current.id)}
                >
                  {t('Ablehnung dokumentieren')}
                </button>
              </>
            )}
            {current.status === 'accepted' && (
              <button
                className="button button-primary"
                disabled={busy}
                onClick={() => void act('confirm', current.id)}
              >
                {t('Auftragsbestätigung ausgeben')}
              </button>
            )}
            <button
              className="button button-ghost"
              disabled={busy || !note.trim()}
              onClick={() => void act('cancel', current.id)}
            >
              {t('Zusage oder Angebot aufheben')}
            </button>
          </div>
          <p className="muted">
            {t(
              'Eine Annahme erst nach tatsächlicher Zusage des Auftraggebers erfassen. Änderungen nach einer festen Zusage erfordern deren dokumentierte Aufhebung und ein neues Angebot.',
            )}
          </p>
        </div>
      )}
      <h2>{t('Archivierte Auftrittsdokumente')}</h2>
      {docs.map((d) => (
        <article className="card stack" key={d.id}>
          <h3>
            {d.number} · {d.kind === 'offer' ? t('Angebot') : t('Auftragsbestätigung')}
          </h3>
          <p>
            {d.kind === 'offer'
              ? statuses[d.status]
              : d.source_status === 'cancelled'
                ? t('Aufgehoben')
                : t('Auftragsbestätigung ausgegeben')}
          </p>
          <strong>
            {d.snapshot.title} · {d.snapshot.buyer?.name} · {euro(d.snapshot.total || '0')}
          </strong>
          <p className="music-guest-notes">{d.snapshot.terms}</p>
          {d.valid_until && (
            <p>
              {t('Angebot gültig bis')}: {d.valid_until}
            </p>
          )}
          {d.acceptance_note && <p>{d.acceptance_note}</p>}
          {d.resolution_note && <p>{d.resolution_note}</p>}
          <button
            className="button button-ghost"
            disabled={busy}
            onClick={async () => {
              setBusy(true)
              setError('')
              try {
                saveBlob(await requestBlob('GET', `${url}?document=${d.id}`), `${d.number}.pdf`)
              } catch (e) {
                setError(errorMessage(e))
              } finally {
                setBusy(false)
              }
            }}
          >
            {t('Archiviertes PDF herunterladen')}
          </button>
        </article>
      ))}
    </section>
  )
}
