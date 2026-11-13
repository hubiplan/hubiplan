// Mein Bereich › Firma (Haushalte und Firmen H5): Ansprechpartner einer Firma, die für
// Mitarbeiter zahlt, sehen nur Name, seit wann und ob der Beitrag über die Firma läuft.
import { useState } from 'react'
import type { FormEvent } from 'react'
import { api } from '../../api/client.ts'
import { todayIso } from '../../api/members.ts'
import { errorMessage, formatDate, useLoad } from '../../components/forms.ts'
import { Alert, Field, LoadError, Loading } from '../../components/ui.tsx'
import { t } from '../../i18n/index.ts'

export interface CompanyEmployee {
  link: number
  name: string
  since: string
  until: string | null
  pays_via: boolean
}

export interface PortalCompanyData {
  can_report: boolean
  companies: { id: number; name: string; members: CompanyEmployee[] }[]
}

export function PortalCompany({ accessId }: { accessId: number }) {
  const base = `/api/portal/${accessId}/company/`
  const { data, error, reload, setData } = useLoad(() => api.get<PortalCompanyData>(base), [base])
  if (error) return <LoadError message={error} onRetry={reload} />
  if (!data) return <Loading />
  return (
    <div className="stack">
      <p>
        {t(
          'Hier siehst du die Mitarbeiterinnen und Mitarbeiter, für die deine Firma den Beitrag zahlt. Anschrift und weitere Angaben bleiben beim Verein.',
        )}
      </p>
      {data.companies.map((company) => (
        <CompanyCard
          key={company.id}
          base={`${base}${company.id}/`}
          name={company.name}
          members={company.members}
          canReport={data.can_report}
          onMembers={(members) =>
            setData({
              ...data,
              companies: data.companies.map((c) => (c.id === company.id ? { ...c, members } : c)),
            })
          }
        />
      ))}
    </div>
  )
}

function CompanyCard({
  base,
  name,
  members,
  canReport,
  onMembers,
}: {
  base: string
  name: string
  members: CompanyEmployee[]
  canReport: boolean
  onMembers: (members: CompanyEmployee[]) => void
}) {
  const [ending, setEnding] = useState<number | null>(null)
  return (
    <section className="card stack" aria-label={name}>
      <h2>{name}</h2>
      {members.length === 0 ? (
        <p className="muted">{t('Noch niemand eingetragen.')}</p>
      ) : (
        <div className="table-scroll">
          <table className="table">
            <thead>
              <tr>
                <th scope="col">{t('Name')}</th>
                <th scope="col">{t('Seit')}</th>
                <th scope="col">{t('Beitrag')}</th>
                <th scope="col">
                  <span className="sr-only">{t('Aktionen')}</span>
                </th>
              </tr>
            </thead>
            <tbody>
              {members.map((m) => (
                <tr key={m.link}>
                  <td>{m.name}</td>
                  <td>
                    {formatDate(m.since)}
                    {m.until && ` · ${t('bis {x}', { x: formatDate(m.until) })}`}
                  </td>
                  <td>{m.pays_via ? t('über die Firma') : t('zahlt selbst')}</td>
                  <td>
                    {!m.until && (
                      <button
                        type="button"
                        className="button button-ghost"
                        aria-expanded={ending === m.link}
                        onClick={() => setEnding(ending === m.link ? null : m.link)}
                      >
                        {t('Beitrag beenden')}
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {ending !== null && (
        <EndForm
          url={`${base}members/${ending}/end/`}
          name={members.find((m) => m.link === ending)?.name ?? ''}
          onDone={(rows) => {
            setEnding(null)
            onMembers(rows)
          }}
          onCancel={() => setEnding(null)}
        />
      )}
      {canReport ? (
        <ReportForm url={`${base}report/`} />
      ) : (
        <p className="muted">{t('Neue Mitarbeiter meldet ihr bitte direkt beim Verein.')}</p>
      )}
    </section>
  )
}

function EndForm({
  url,
  name,
  onDone,
  onCancel,
}: {
  url: string
  name: string
  onDone: (rows: CompanyEmployee[]) => void
  onCancel: () => void
}) {
  const [until, setUntil] = useState(todayIso())
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  async function submit(e: FormEvent) {
    e.preventDefault()
    setBusy(true)
    setError(null)
    try {
      const res = await api.post<{ members: CompanyEmployee[] }>(url, { valid_until: until })
      onDone(res.members)
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setBusy(false)
    }
  }
  return (
    <form
      className="stack-sm"
      onSubmit={submit}
      aria-label={t('Beitrag für {x} beenden', { x: name })}
    >
      <p>
        {t(
          'Die Firma zahlt dann nicht mehr für {x}. Die Mitgliedschaft bleibt bestehen; danach zahlt das Mitglied selbst. Verein und Mitglied bekommen eine Mail.',
          { x: name },
        )}
      </p>
      <Field
        label={t('Firma zahlt bis')}
        type="date"
        min={todayIso()}
        value={until}
        required
        onChange={(e) => setUntil(e.target.value)}
      />
      {error && <Alert kind="error">{error}</Alert>}
      <div className="button-row">
        <button type="submit" className="button" disabled={busy}>
          {t('Beitrag beenden')}
        </button>
        <button type="button" className="button button-ghost" onClick={onCancel}>
          {t('Abbrechen')}
        </button>
      </div>
    </form>
  )
}

function ReportForm({ url }: { url: string }) {
  const blank = { first_name: '', last_name: '', email: '' }
  const [values, setValues] = useState(blank)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [sent, setSent] = useState<string | null>(null)
  async function submit(e: FormEvent) {
    e.preventDefault()
    setBusy(true)
    setError(null)
    setSent(null)
    try {
      await api.post(url, values)
      setSent(values.email)
      setValues(blank)
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setBusy(false)
    }
  }
  return (
    <form className="stack-sm" onSubmit={submit}>
      <h3>{t('Mitarbeiter melden')}</h3>
      <p className="muted">
        {t(
          'Die Person bekommt eine Mail mit dem Link zum Online-Antrag, ergänzt ihre Angaben und bestätigt selbst. Nimmt der Verein sie auf, zahlt die Firma ihren Beitrag.',
        )}
      </p>
      <Field
        label={t('Vorname')}
        value={values.first_name}
        required
        maxLength={100}
        onChange={(e) => setValues({ ...values, first_name: e.target.value })}
      />
      <Field
        label={t('Nachname')}
        value={values.last_name}
        required
        maxLength={100}
        onChange={(e) => setValues({ ...values, last_name: e.target.value })}
      />
      <Field
        label={t('E-Mail')}
        type="email"
        value={values.email}
        required
        maxLength={200}
        onChange={(e) => setValues({ ...values, email: e.target.value })}
      />
      {error && <Alert kind="error">{error}</Alert>}
      {sent && <Alert kind="success">{t('Mail an {x} gesendet.', { x: sent })}</Alert>}
      <div className="button-row">
        <button type="submit" className="button" disabled={busy}>
          {t('Melden')}
        </button>
      </div>
    </form>
  )
}
