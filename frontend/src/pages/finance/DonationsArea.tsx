import { useState } from 'react'
import type { FormEvent } from 'react'
import { Navigate, Route, Routes } from 'react-router-dom'
import { donationApi, earmarkApi } from '../../api/donations.ts'
import type { Earmark } from '../../api/donations.ts'
import { euro } from '../../api/finance.ts'
import { promptDialog } from '../../components/dialog.ts'
import { errorMessage, formatDate, useLoad } from '../../components/forms.ts'
import { Alert, Field, LoadError, SelectField, Loading } from '../../components/ui.tsx'
import { useActiveOrg } from '../../org/OrgContext.tsx'
import { Term } from '../../learning/Aids.tsx'
import { t } from '../../i18n/index.ts'
import { DonationsList } from './DonationsList.tsx'
import { thisYear, yearOptions } from './donationsHelpers.ts'
import { PageNav } from './PageNav.tsx'

export function DonationsArea({ canEdit }: { canEdit: boolean }) {
  return (
    <Routes>
      <Route index element={<DonationsList canEdit={canEdit} />} />
      <Route path="bestaetigungen" element={<StatementsList canEdit={canEdit} />} />
      <Route path="zweckbindungen" element={<EarmarksList canEdit={canEdit} />} />
      {/* Die Einrichtung steht unter Finanzen › Einrichtung › Zuwendungen */}
      <Route
        path="einstellungen"
        element={<Navigate to="/finanzen/einrichtung/zuwendungen" replace />}
      />
    </Routes>
  )
}

// --- Zuwendungen ---

function StatementsList({ canEdit }: { canEdit: boolean }) {
  const org = useActiveOrg()
  const [year, setYear] = useState(thisYear())
  const [page, setPage] = useState(1)
  const [message, setMessage] = useState<{ kind: 'success' | 'error'; text: string } | null>(null)
  const years = useLoad(() => donationApi.statementYears(org.id).catch(() => null), [org.id])
  const list = useLoad(
    () => donationApi.statements(org.id, { jahr: year, page: page > 1 ? page : undefined }),
    [org.id, year, page],
  )

  async function cancel(id: number, number: string) {
    const reason = await promptDialog({
      title: t('Bestätigung {number} stornieren?', { number }),
      message: t(
        'Das Doppel bleibt gespeichert, die Zuwendungen werden wieder frei. Bitte das Original vom Zuwendenden zurückfordern.',
      ),
      label: t('Grund'),
      confirmLabel: t('Stornieren'),
      danger: true,
    })
    if (reason === null) return
    try {
      await donationApi.cancel(org.id, id, reason)
      setMessage({ kind: 'success', text: t('{number} storniert.', { number }) })
      await list.reload()
    } catch (err) {
      setMessage({ kind: 'error', text: errorMessage(err) })
    }
  }

  const rows = list.data?.results ?? []
  return (
    <div className="card card-wide">
      <div className="filters">
        <SelectField
          label={t('Ausgestellt')}
          value={year}
          onChange={(e) => {
            setYear(Number(e.target.value))
            setPage(1)
          }}
        >
          {yearOptions(years.data, year).map((y) => (
            <option key={y} value={y}>
              {y}
            </option>
          ))}
        </SelectField>
      </div>
      <p className="muted small">
        {t('Jede')} <Term k="donation_receipt">{t('Zuwendungsbestätigung')}</Term>{' '}
        {t(
          'wird als Doppel gespeichert (§ 50 Abs. 7 EStDV) und lässt sich jederzeit wieder herunterladen. Fehlerhafte Bestätigungen stornieren und neu ausstellen.',
        )}
      </p>
      {message && <Alert kind={message.kind}>{message.text}</Alert>}
      {list.error && <LoadError message={list.error} onRetry={() => void list.reload()} />}
      {!list.data ? (
        !list.error && <Loading />
      ) : rows.length === 0 ? (
        <p className="muted">{t('Keine Bestätigungen {year}.', { year })}</p>
      ) : (
        <table className="table">
          <thead>
            <tr>
              <th>{t('Nummer')}</th>
              <th>{t('ausgestellt')}</th>
              <th>{t('Zuwendender')}</th>
              <th>{t('Art')}</th>
              <th className="num">{t('Betrag')}</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {rows.map((s) => (
              <tr key={s.id} className={s.cancelled_at ? 'muted' : undefined}>
                <td>
                  <strong>{s.number}</strong>
                  {s.cancelled_at && (
                    <span className="field-error small">
                      {' '}
                      {t('· storniert ({cancel_reason})', { cancel_reason: s.cancel_reason })}
                    </span>
                  )}
                </td>
                <td>{formatDate(s.issued_on)}</td>
                <td>{s.donor_name}</td>
                <td>{s.goods ? t('Sachzuwendung') : s.kind_label}</td>
                <td className="num">{euro(s.total)}</td>
                <td className="actions">
                  <a href={donationApi.pdfUrl(org.id, s.id)} target="_blank" rel="noreferrer">
                    PDF
                  </a>
                  {canEdit && !s.cancelled_at && (
                    <>
                      {' '}
                      <button
                        type="button"
                        className="link-button"
                        onClick={() => void cancel(s.id, s.number)}
                      >
                        {t('Stornieren')}
                      </button>
                    </>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      <PageNav
        page={page}
        count={list.data?.count ?? 0}
        onPage={setPage}
        noun={t('Bestätigungen')}
      />
    </div>
  )
}

// --- Zweckbindungen (Konzept vereinskasse-steuern, S5) ---

function EarmarksList({ canEdit }: { canEdit: boolean }) {
  const org = useActiveOrg()
  const list = useLoad(() => earmarkApi.list(org.id), [org.id])
  const [name, setName] = useState('')
  const [note, setNote] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  async function run(action: () => Promise<unknown>) {
    setBusy(true)
    setError(null)
    try {
      await action()
      await list.reload()
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setBusy(false)
    }
  }

  async function add(e: FormEvent) {
    e.preventDefault()
    await run(async () => {
      await earmarkApi.create(org.id, { name, note })
      setName('')
      setNote('')
    })
  }

  if (list.error) return <LoadError message={list.error} onRetry={() => void list.reload()} />
  if (!list.data) return <Loading />
  const rows: Earmark[] = list.data

  return (
    <div className="card card-wide" data-testid="earmarks">
      <h2>{t('Zweckgebundene Spenden')}</h2>
      <p className="muted small">
        {t(
          'Spenden für einen bestimmten Zweck, etwa die Sanierung des Vereinsheims, dürfen nur dafür verwendet werden. Ordnet die Spenden hier einem Zweck zu und im Kassenbuch die Ausgaben dafür; der Rest zeigt, was noch zweckgebunden zu verwenden ist. Gezählt werden Geldzuwendungen.',
        )}
      </p>
      {error && <Alert kind="error">{error}</Alert>}
      {rows.length === 0 ? (
        <p className="muted">{t('Noch keine Zweckbindungen.')}</p>
      ) : (
        <table className="table">
          <thead>
            <tr>
              <th>{t('Zweck')}</th>
              <th className="num">{t('Spenden')}</th>
              <th className="num">{t('verwendet')}</th>
              <th className="num">{t('Rest')}</th>
              {canEdit && <th />}
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.id} className={r.is_active ? undefined : 'muted'}>
                <td>
                  {r.name}
                  {!r.is_active && <span className="muted small"> ({t('archiviert')})</span>}
                  {r.note && <div className="muted small">{r.note}</div>}
                  {r.overdue && (
                    <div className="small">
                      <span className="badge badge-open">{t('zeitnah verwenden')}</span>{' '}
                      {t(
                        'Die erste Spende liegt mehr als zwei Jahre zurück. Gemeinnützige Mittel müssen bis zum Ende des zweiten Folgejahres verwendet sein.',
                      )}
                    </div>
                  )}
                </td>
                <td className="num">{euro(r.received)}</td>
                <td className="num">{euro(r.used)}</td>
                <td className="num">
                  <strong>{euro(r.rest)}</strong>
                </td>
                {canEdit && (
                  <td>
                    <button
                      type="button"
                      className="button button-ghost"
                      disabled={busy}
                      onClick={() =>
                        void run(() => earmarkApi.update(org.id, r.id, { is_active: !r.is_active }))
                      }
                    >
                      {r.is_active ? t('Archivieren') : t('Wiederherstellen')}
                    </button>
                  </td>
                )}
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {canEdit && (
        <form className="subcard" onSubmit={(e) => void add(e)}>
          <h3>{t('Neuer Zweck')}</h3>
          <div className="grid-2">
            <Field
              label={t('Zweck')}
              value={name}
              maxLength={100}
              required
              placeholder={t('z. B. Sanierung Vereinsheim')}
              onChange={(e) => setName(e.target.value)}
            />
            <Field
              label={t('Beschreibung')}
              value={note}
              maxLength={1000}
              onChange={(e) => setNote(e.target.value)}
            />
          </div>
          <div className="button-row">
            <button type="submit" className="button button-primary" disabled={busy || !name.trim()}>
              {t('Anlegen')}
            </button>
          </div>
        </form>
      )}
    </div>
  )
}

// --- Einstellungen ---
