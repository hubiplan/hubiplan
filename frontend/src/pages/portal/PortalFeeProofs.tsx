// Mein Bereich › Beitragsnachweise: Nachweis für einen ermäßigten Beitrag einreichen und den
// Stand je Beitragsjahr sehen (docs/beitragsnachweise.md).
import { useState } from 'react'
import { portalFeeProofApi } from '../../api/feeProofs.ts'
import type { MemberProofs, YearState } from '../../api/feeProofs.ts'
import { errorMessage, formatDate, useLoad } from '../../components/forms.ts'
import { Alert, EmptyState, LoadError, Loading } from '../../components/ui.tsx'
import { t } from '../../i18n/index.ts'
import { ProofStatusBadge, StateBadge, UploadForm, stateSentence } from '../feeproofs/parts.tsx'

export function PortalFeeProofs({ accessId }: { accessId: number }) {
  const { data, error, reload } = useLoad(() => portalFeeProofApi.get(accessId), [accessId])
  const [shown, setShown] = useState<MemberProofs | null>(null)
  if (error) return <LoadError message={error} onRetry={reload} />
  const view = shown ?? data
  if (!view) return <Loading />
  return (
    <div className="stack">
      <p className="muted">
        {t(
          'Für einen ermäßigten Beitrag braucht der Verein jedes Jahr einen aktuellen Nachweis, zum Beispiel eine Immatrikulationsbescheinigung. Ohne Nachweis gilt der normale Beitrag.',
        )}
      </p>
      {view.states.length === 0 && <EmptyState title={t('Gerade ist kein Nachweis nötig.')} />}
      {view.states.map((st) => (
        <YearCard
          key={`${st.discount}-${st.year}`}
          accessId={accessId}
          state={st}
          onDone={(next) => setShown(next)}
        />
      ))}
      {view.proofs.length > 0 && (
        <section className="stack">
          <h2>{t('Eingereichte Nachweise')}</h2>
          <ul className="expense-items">
            {view.proofs.map((p) => (
              <li key={p.id}>
                <span>
                  {p.discount_name} · {p.year_label} · {formatDate(p.received_on)}
                  {p.file_name ? ` · ${p.file_name}` : ''}
                </span>{' '}
                <ProofStatusBadge proof={p} />
                {p.note && <div className="muted small">{p.note}</div>}
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  )
}

function YearCard({
  accessId,
  state,
  onDone,
}: {
  accessId: number
  state: YearState
  onDone: (next: MemberProofs) => void
}) {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const canUpload = state.state !== 'accepted'
  const submit = async (file: File, kind: string, note: string) => {
    setBusy(true)
    setError('')
    try {
      const next = await portalFeeProofApi.submit(
        accessId,
        { discount: state.discount, year: state.year, kind, note },
        file,
      )
      setNotice(t('Danke! Dein Nachweis ist eingegangen.'))
      onDone(next)
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setBusy(false)
    }
  }
  return (
    <section className="card stack">
      <div className="card-head">
        <h2>
          {state.discount_name} · {state.year_label}
        </h2>
        <StateBadge state={state.state} />
      </div>
      <p>{stateSentence(state)}</p>
      {notice && <Alert kind="success">{notice}</Alert>}
      {canUpload && (
        <UploadForm
          kinds={state.kinds}
          busy={busy}
          error={error}
          onSubmit={(f, k, n) => void submit(f, k, n)}
        />
      )}
    </section>
  )
}
