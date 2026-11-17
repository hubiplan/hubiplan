// Mitgliedsakte: Ermäßigung mit Nachweis zuordnen oder beenden, Stand je Beitragsjahr,
// Nachweise ansehen und selbst eintragen (docs/beitragsnachweise.md).
import { useState } from 'react'
import type { FormEvent } from 'react'
import { feeProofApi } from '../../api/feeProofs.ts'
import type { Assignment, YearState } from '../../api/feeProofs.ts'
import { todayIso } from '../../api/members.ts'
import { confirmDialog } from '../../components/dialog.ts'
import { errorMessage, formatDate, useLoad } from '../../components/forms.ts'
import { DeleteIcon, IconButton } from '../../components/icons.tsx'
import { Alert, LoadError } from '../../components/ui.tsx'
import { t } from '../../i18n/index.ts'
import { ACCEPT_FILES, ProofStatusBadge, StateBadge, channelLabel } from '../feeproofs/parts.tsx'

export function FeeProofsCard({
  orgId,
  memberId,
  canEdit,
}: {
  orgId: number
  memberId: number
  canEdit: boolean
}) {
  const discounts = useLoad(() => feeProofApi.discounts(orgId), [orgId])
  const assignments = useLoad(() => feeProofApi.assignments(orgId, memberId), [orgId, memberId])
  const proofs = useLoad(() => feeProofApi.memberProofs(orgId, memberId), [orgId, memberId])
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [ending, setEnding] = useState<number | null>(null)
  const [endDate, setEndDate] = useState('')
  const [discount, setDiscount] = useState('')
  const [from, setFrom] = useState(todayIso())

  // Ohne eingerichtete Ermäßigung bleibt die Karte weg
  if (!discounts.data || discounts.data.length === 0) return null
  const options = discounts.data.filter((d) => !d.is_archived)

  async function run(action: () => Promise<unknown>) {
    setError(null)
    setBusy(true)
    try {
      await action()
      await Promise.all([assignments.reload(), proofs.reload()])
      return true
    } catch (err) {
      setError(errorMessage(err))
      return false
    } finally {
      setBusy(false)
    }
  }

  async function remove(a: Assignment) {
    const ok = await confirmDialog({
      final: true,
      title: t('„{name}“ entfernen?', { name: a.discount_name }),
      message: t(
        'Nur für falsche Einträge. Endet die Ermäßigung, besser ein Ende eintragen; dann bleibt der Verlauf erhalten.',
      ),
      confirmLabel: t('Entfernen'),
    })
    if (ok) await run(() => feeProofApi.removeAssignment(orgId, memberId, a.id))
  }

  async function assign(e: FormEvent) {
    e.preventDefault()
    if (!discount) return
    const ok = await run(() =>
      feeProofApi.assign(orgId, memberId, { discount: Number(discount), valid_from: from }),
    )
    if (ok) setDiscount('')
  }

  const endOfYear = `${new Date().getFullYear()}-12-31`

  return (
    <div className="card card-wide">
      <h2>{t('Ermäßigung mit Nachweis')}</h2>
      {assignments.error ? (
        <LoadError message={assignments.error} onRetry={() => void assignments.reload()} />
      ) : !assignments.data ? (
        <p className="muted small">{t('Wird geladen …')}</p>
      ) : assignments.data.length === 0 ? (
        <p className="muted">{t('Keine.')}</p>
      ) : (
        <ul className="item-list">
          {assignments.data.map((a) => (
            <li key={a.id} className="item-row">
              <span className="item-row-info">
                <strong>{a.discount_name}</strong> ·{' '}
                {a.valid_until
                  ? t('{from} bis {until}', {
                      from: formatDate(a.valid_from),
                      until: formatDate(a.valid_until),
                    })
                  : t('seit {date}', { date: formatDate(a.valid_from) })}
              </span>
              {canEdit && (
                <span className="button-row">
                  {!a.valid_until && (
                    <button
                      type="button"
                      className="link-button"
                      disabled={busy}
                      onClick={() => {
                        setEnding(a.id)
                        setEndDate(endOfYear)
                      }}
                    >
                      {t('Ende eintragen')}
                    </button>
                  )}
                  <IconButton
                    label={t('{name} entfernen', { name: a.discount_name })}
                    icon={<DeleteIcon />}
                    danger
                    disabled={busy}
                    onClick={() => void remove(a)}
                  />
                </span>
              )}
              {canEdit && ending === a.id && (
                <form
                  className="button-row"
                  onSubmit={(e) => {
                    e.preventDefault()
                    void run(() =>
                      feeProofApi.updateAssignment(orgId, memberId, a.id, { valid_until: endDate }),
                    ).then((ok) => ok && setEnding(null))
                  }}
                >
                  <label className="field">
                    <span>{t('Ermäßigung endet am')}</span>
                    <input
                      type="date"
                      value={endDate}
                      required
                      onChange={(e) => setEndDate(e.target.value)}
                    />
                  </label>
                  <button type="submit" className="button button-primary" disabled={busy}>
                    {t('Speichern')}
                  </button>
                  <button
                    type="button"
                    className="button button-ghost"
                    onClick={() => setEnding(null)}
                  >
                    {t('Abbrechen')}
                  </button>
                </form>
              )}
            </li>
          ))}
        </ul>
      )}
      {canEdit && options.length > 0 && (
        <form className="button-row" onSubmit={(e) => void assign(e)}>
          <label className="field">
            <span>{t('Ermäßigung zuordnen')}</span>
            <select value={discount} onChange={(e) => setDiscount(e.target.value)}>
              <option value="">{t('bitte wählen')}</option>
              {options.map((d) => (
                <option key={d.id} value={d.id}>
                  {d.name}
                </option>
              ))}
            </select>
          </label>
          <label className="field">
            <span>{t('ab')}</span>
            <input type="date" value={from} required onChange={(e) => setFrom(e.target.value)} />
          </label>
          <button type="submit" className="button" disabled={busy || !discount}>
            {t('Zuordnen')}
          </button>
        </form>
      )}
      {proofs.data && proofs.data.states.length > 0 && (
        <ul className="item-list">
          {proofs.data.states.map((st) => (
            <li key={`${st.discount}-${st.year}`} className="item-row">
              <span className="item-row-info">
                {st.discount_name} · {st.year_label} ·{' '}
                {t('Frist {day}', { day: formatDate(st.final) })}
              </span>
              <StateBadge state={st.state} />
            </li>
          ))}
        </ul>
      )}
      {proofs.data && proofs.data.proofs.length > 0 && (
        <details>
          <summary>{t('Nachweise ({n})', { n: proofs.data.proofs.length })}</summary>
          <ul className="item-list">
            {proofs.data.proofs.map((p) => (
              <li key={p.id} className="item-row">
                <span className="item-row-info">
                  {p.discount_name} · {p.year_label} · {formatDate(p.received_on)} ·{' '}
                  {channelLabel(p.channel)}
                  {p.valid_until && (
                    <> · {t('gültig bis {day}', { day: formatDate(p.valid_until) })}</>
                  )}
                  {p.has_file && (
                    <>
                      {' · '}
                      <a href={feeProofApi.fileUrl(orgId, p.id)} target="_blank" rel="noreferrer">
                        {p.file_name || t('Datei')}
                      </a>
                    </>
                  )}
                  {p.note && <span className="muted small"> · {p.note}</span>}
                </span>
                <ProofStatusBadge proof={p} />
              </li>
            ))}
          </ul>
        </details>
      )}
      {canEdit && proofs.data && proofs.data.states.length > 0 && (
        <BoardEntry
          states={proofs.data.states}
          busy={busy}
          onSave={(data, file) =>
            run(() => feeProofApi.addMemberProof(orgId, memberId, data, file))
          }
        />
      )}
      {error && <Alert kind="error">{error}</Alert>}
    </div>
  )
}

/** Nachweis eintragen, der beim Vorstand ankam (Papier, E-Mail an eine Person) */
function BoardEntry({
  states,
  busy,
  onSave,
}: {
  states: YearState[]
  busy: boolean
  onSave: (
    data: {
      discount: number
      year: number
      received_on: string
      valid_until?: string
      kind?: string
    },
    file: File | null,
  ) => Promise<boolean>
}) {
  const [open, setOpen] = useState(false)
  const [choice, setChoice] = useState(0)
  const [received, setReceived] = useState(todayIso())
  const [until, setUntil] = useState('')
  const [file, setFile] = useState<File | null>(null)
  if (!open)
    return (
      <div className="button-row">
        <button type="button" className="button button-ghost" onClick={() => setOpen(true)}>
          {t('Nachweis eintragen')}
        </button>
      </div>
    )
  const st = states[choice] ?? states[0]
  const submit = async (e: FormEvent) => {
    e.preventDefault()
    const ok = await onSave(
      {
        discount: st.discount,
        year: st.year,
        received_on: received,
        valid_until: until || undefined,
      },
      file,
    )
    if (ok) {
      setOpen(false)
      setFile(null)
      setUntil('')
    }
  }
  return (
    <form className="stack" onSubmit={(e) => void submit(e)}>
      <p className="muted small">
        {t(
          'Ohne Datei gilt der Eintrag als Einsichtsvermerk (Nachweis gesehen) und ist gleich anerkannt. Mit Datei kommt er in die Prüfliste.',
        )}
      </p>
      <div className="grid-2">
        <label className="field">
          <span>{t('Für')}</span>
          <select value={choice} onChange={(e) => setChoice(Number(e.target.value))}>
            {states.map((s, i) => (
              <option key={`${s.discount}-${s.year}`} value={i}>
                {s.discount_name} · {s.year_label}
              </option>
            ))}
          </select>
        </label>
        <label className="field">
          <span>{t('eingegangen am')}</span>
          <input
            type="date"
            value={received}
            required
            onChange={(e) => setReceived(e.target.value)}
          />
        </label>
        <label className="field">
          <span>{t('gültig bis')}</span>
          <input type="date" value={until} onChange={(e) => setUntil(e.target.value)} />
        </label>
      </div>
      <div className="button-row">
        <label className="button button-ghost file-button">
          {t('Datei wählen (freiwillig)')}
          <input
            type="file"
            className="file-input"
            accept={ACCEPT_FILES}
            onChange={(e) => {
              setFile(e.target.files?.[0] ?? null)
              e.target.value = ''
            }}
          />
        </label>
        {file && <span className="muted">{file.name}</span>}
      </div>
      <div className="button-row">
        <button type="submit" className="button button-primary" disabled={busy}>
          {file ? t('Zur Prüfung eintragen') : t('Als gesehen eintragen')}
        </button>
        <button type="button" className="button button-ghost" onClick={() => setOpen(false)}>
          {t('Abbrechen')}
        </button>
      </div>
    </form>
  )
}
