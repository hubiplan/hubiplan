// Mitglieder › Beitragsnachweise: eingegangene Nachweise prüfen, Stand aller Mitglieder mit
// Ermäßigung je Beitragsjahr und Vorschläge zum Beenden (docs/beitragsnachweise.md).
import { useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { feeProofApi } from '../../api/feeProofs.ts'
import type { DecideInput, FeeProof, ProofDiscount } from '../../api/feeProofs.ts'
import { PERM } from '../../api/orgs.ts'
import { promptDialog } from '../../components/dialog.ts'
import { errorMessage, formatDate, useLoad } from '../../components/forms.ts'
import { Segmented } from '../../components/PageHeader.tsx'
import { Alert, EmptyState, LoadError, Loading } from '../../components/ui.tsx'
import { t } from '../../i18n/index.ts'
import { useActiveOrg } from '../../org/OrgContext.tsx'
import { PrecheckInfo, StateBadge, channelLabel } from '../feeproofs/parts.tsx'

type View = 'pruefen' | 'uebersicht' | 'zwei-jahre'

export function FeeProofsPage() {
  const [params, setParams] = useSearchParams()
  const view: View =
    params.get('stand') === 'zwei-jahre'
      ? 'zwei-jahre'
      : params.get('ansicht') === 'uebersicht'
        ? 'uebersicht'
        : 'pruefen'
  const choose = (next: View) => {
    const p = new URLSearchParams()
    if (next === 'zwei-jahre') p.set('stand', 'zwei-jahre')
    if (next === 'uebersicht') p.set('ansicht', 'uebersicht')
    setParams(p, { replace: true })
  }
  return (
    <div className="stack">
      <Segmented<View>
        label={t('Ansicht')}
        value={view}
        onChange={choose}
        options={[
          { value: 'pruefen', label: t('Zu prüfen') },
          { value: 'uebersicht', label: t('Übersicht') },
          { value: 'zwei-jahre', label: t('Zwei Jahre ohne Nachweis') },
        ]}
      />
      {view === 'pruefen' && <Queue />}
      {view === 'uebersicht' && <YearOverview />}
      {view === 'zwei-jahre' && <Stale />}
    </div>
  )
}

function Queue() {
  const org = useActiveOrg()
  const list = useLoad(() => feeProofApi.list(org.id), [org.id])
  const discounts = useLoad(() => feeProofApi.discounts(org.id), [org.id])
  const canEdit = org.permissions.includes(PERM.membersEdit)
  if (list.error) return <LoadError message={list.error} onRetry={list.reload} />
  if (!list.data || !discounts.data) return <Loading />
  if (discounts.data.length === 0)
    return (
      <EmptyState title={t('Noch keine Ermäßigung mit Nachweis eingerichtet.')}>
        {t('Eingerichtet wird unter Finanzen › Beitragssätze.')}
      </EmptyState>
    )
  if (list.data.length === 0)
    return <EmptyState title={t('Keine Nachweise zu prüfen.')} icon="inbox" />
  return (
    <div className="stack">
      {list.data.map((p) => (
        <ProofCard
          key={p.id}
          proof={p}
          discount={discounts.data?.find((d) => d.id === p.discount)}
          canEdit={canEdit}
          onDone={() => void list.reload()}
        />
      ))}
    </div>
  )
}

function ProofCard({
  proof,
  discount,
  canEdit,
  onDone,
}: {
  proof: FeeProof
  discount?: ProofDiscount
  canEdit: boolean
  onDone: () => void
}) {
  const org = useActiveOrg()
  const [validUntil, setValidUntil] = useState(proof.precheck?.valid_until ?? '')
  const [kind, setKind] = useState(proof.kind)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const decide = async (action: DecideInput['action']) => {
    let note = ''
    if (action !== 'accept') {
      const text = await promptDialog({
        title: action === 'reject' ? t('Nachweis ablehnen') : t('Rückfrage stellen'),
        message: t('Das Mitglied bekommt den Text per E-Mail.'),
        label: action === 'reject' ? t('Grund') : t('Rückfrage'),
        confirmLabel: action === 'reject' ? t('Ablehnen') : t('Rückfrage senden'),
        danger: action === 'reject',
      })
      if (!text?.trim()) return
      note = text.trim()
    }
    setBusy(true)
    setError('')
    try {
      await feeProofApi.decide(org.id, proof.id, {
        action,
        note,
        kind,
        valid_until: action === 'accept' ? validUntil || null : undefined,
      })
      onDone()
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
          <Link to={`/mitglieder/${proof.membership}`}>
            {proof.last_name}, {proof.first_name}
          </Link>
        </h2>
        {proof.status === 'question' && <span className="badge badge-warn">{t('Rückfrage')}</span>}
      </div>
      <p>
        {proof.discount_name} · {proof.year_label} ·{' '}
        {t('eingegangen am {day}', { day: formatDate(proof.received_on) })} ·{' '}
        {channelLabel(proof.channel)}
        {proof.late && (
          <>
            {' '}
            · <span className="badge badge-warn">{t('nach der Frist')}</span>
          </>
        )}
      </p>
      {proof.member_note && <p className="muted">„{proof.member_note}“</p>}
      {proof.status === 'question' && proof.note && (
        <p className="muted">{t('Rückfrage: {note}', { note: proof.note })}</p>
      )}
      <PrecheckInfo precheck={proof.precheck} />
      {proof.has_file ? (
        <p>
          <a href={feeProofApi.fileUrl(org.id, proof.id)} target="_blank" rel="noreferrer">
            {t('Nachweis ansehen')}: {proof.file_name}
          </a>
        </p>
      ) : (
        <p className="muted">{t('Ohne Datei, z. B. eine E-Mail ohne Anhang.')}</p>
      )}
      {canEdit && (
        <>
          <div className="grid-2">
            <label className="field">
              <span>{t('gültig bis')}</span>
              <input
                type="date"
                value={validUntil}
                onChange={(e) => setValidUntil(e.target.value)}
              />
            </label>
            {discount && discount.kinds.length > 0 && (
              <label className="field">
                <span>{t('Art des Nachweises')}</span>
                <select value={kind} onChange={(e) => setKind(e.target.value)}>
                  <option value="">{t('ohne Angabe')}</option>
                  {discount.kinds.map((k) => (
                    <option key={k} value={k}>
                      {k}
                    </option>
                  ))}
                </select>
              </label>
            )}
          </div>
          {error && <Alert kind="error">{error}</Alert>}
          <div className="button-row">
            <button
              type="button"
              className="button button-primary"
              disabled={busy}
              onClick={() => void decide('accept')}
            >
              {t('Anerkennen')}
            </button>
            <button
              type="button"
              className="button"
              disabled={busy}
              onClick={() => void decide('question')}
            >
              {t('Rückfrage')}
            </button>
            <button
              type="button"
              className="button button-ghost"
              disabled={busy}
              onClick={() => void decide('reject')}
            >
              {t('Ablehnen')}
            </button>
          </div>
          <p className="muted small">
            {t('Nach der Entscheidung wird die Datei gelöscht; es bleibt nur der Vermerk.')}
          </p>
        </>
      )}
    </section>
  )
}

function YearOverview() {
  const org = useActiveOrg()
  const [year, setYear] = useState<number | undefined>(undefined)
  const data = useLoad(() => feeProofApi.overview(org.id, year), [org.id, year])
  if (data.error) return <LoadError message={data.error} onRetry={data.reload} />
  if (!data.data) return <Loading />
  const o = data.data
  return (
    <div className="stack">
      <div className="button-row">
        <button type="button" className="button button-ghost" onClick={() => setYear(o.year - 1)}>
          {t('Vorjahr')}
        </button>
        <strong>{t('Beitragsjahr {year}', { year: o.year_label })}</strong>
        <button type="button" className="button button-ghost" onClick={() => setYear(o.year + 1)}>
          {t('Folgejahr')}
        </button>
      </div>
      <p className="muted">
        {t(
          'Anerkannt {accepted} · in Prüfung {pending} · Rückfrage {question} · Frist läuft {open} · normaler Beitrag {missing}',
          o.counts,
        )}
      </p>
      {o.rows.length === 0 ? (
        <EmptyState title={t('In diesem Jahr hat niemand eine Ermäßigung mit Nachweis.')} />
      ) : (
        <div className="card table-scroll">
          <table className="table">
            <thead>
              <tr>
                <th>{t('Mitglied')}</th>
                <th>{t('Ermäßigung')}</th>
                <th>{t('Frist')}</th>
                <th>{t('Stand')}</th>
              </tr>
            </thead>
            <tbody>
              {o.rows.map((r) => (
                <tr key={`${r.membership}-${r.discount}`}>
                  <td>
                    <Link to={`/mitglieder/${r.membership}`}>
                      {r.last_name}, {r.first_name}
                    </Link>
                  </td>
                  <td>{r.discount_name}</td>
                  <td>
                    {formatDate(r.due)}
                    {r.final !== r.due && (
                      <span className="muted small">
                        {' '}
                        ({t('Kulanz bis {day}', { day: formatDate(r.final) })})
                      </span>
                    )}
                  </td>
                  <td>
                    <StateBadge state={r.state} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}

function Stale() {
  const org = useActiveOrg()
  const data = useLoad(() => feeProofApi.stale(org.id), [org.id])
  if (data.error) return <LoadError message={data.error} onRetry={data.reload} />
  if (!data.data) return <Loading />
  const rows = data.data.stale
  return (
    <div className="stack">
      <p className="muted">
        {t(
          'Diese Mitglieder haben zwei Beitragsjahre hintereinander keinen Nachweis gebracht. Liegen die Voraussetzungen nicht mehr vor, in der Mitgliedsakte ein Ende der Ermäßigung eintragen.',
        )}
      </p>
      {rows.length === 0 ? (
        <EmptyState title={t('Niemand.')} />
      ) : (
        <div className="card table-scroll">
          <table className="table">
            <thead>
              <tr>
                <th>{t('Mitglied')}</th>
                <th>{t('Ermäßigung')}</th>
                <th>{t('seit')}</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.assignment}>
                  <td>
                    <Link to={`/mitglieder/${r.membership}`}>
                      {r.last_name}, {r.first_name}
                    </Link>
                  </td>
                  <td>{r.discount_name}</td>
                  <td>{formatDate(r.valid_from)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
