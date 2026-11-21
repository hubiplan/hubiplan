// Training im Mitgliederbereich: eigene Anwesenheit, Einchecken per QR-Code und mit Schießsport
// das eigene Schießbuch mit Stand nach § 14 WaffG; Schießtermine melden.
import { useEffect, useRef, useState } from 'react'
import { newRequestKey } from '../../api/client.ts'
import { portalTrainingApi } from '../../api/training.ts'
import type { PortalTraining as Data } from '../../api/training.ts'
import { errorMessage, formatDate, useLoad } from '../../components/forms.ts'
import { Alert, LoadError, Loading } from '../../components/ui.tsx'
import { t } from '../../i18n/index.ts'
import { EntryForm } from '../training/EntryForm.tsx'
import { EvaluationCard } from '../training/Evaluation.tsx'
import { entryDetails } from '../training/ShootingLog.tsx'

export function PortalTraining({
  accessId,
  checkin,
}: {
  accessId: number
  /** Aus dem QR-Code: Training und Code, wird beim Öffnen gleich eingecheckt */
  checkin?: { session: number; code: string }
}) {
  const { data, error, reload, setData } = useLoad(
    () => portalTrainingApi.get(accessId),
    [accessId],
  )
  const [message, setMessage] = useState('')
  const [checkinError, setCheckinError] = useState('')
  const tried = useRef(false)
  useEffect(() => {
    if (!checkin || tried.current) return
    tried.current = true
    portalTrainingApi
      .checkin(accessId, checkin.session, checkin.code)
      .then(() => {
        setMessage(t('Du bist eingecheckt. Viel Spaß beim Training!'))
        // Neu laden verwirft eine vorher gestartete, ältere Abfrage
        void reload()
      })
      .catch((err) => setCheckinError(errorMessage(err)))
  }, [accessId, checkin, reload])
  if (error) return <LoadError message={error} onRetry={reload} />
  if (!data) return <Loading />
  return (
    <div className="stack">
      {message && <Alert kind="success">{message}</Alert>}
      {checkinError && <Alert kind="error">{checkinError}</Alert>}
      {data.checkin.length > 0 && (
        <section className="card stack-sm">
          <h2>{t('Einchecken')}</h2>
          <ul className="plain-list">
            {data.checkin.map((s) => (
              <li key={s.id}>
                {formatDate(s.date)} · {s.title}
                {s.present ? (
                  <span className="badge badge-brand">{t('eingecheckt')}</span>
                ) : (
                  <span className="muted small">
                    {' '}
                    · {t('Scanne den QR-Code der Übungsleitung mit der App oder der Handykamera.')}
                  </span>
                )}
              </li>
            ))}
          </ul>
        </section>
      )}
      <Attendance data={data} />
      {data.shooting_enabled && data.shooting && (
        <Shooting accessId={accessId} data={data} onChange={setData} />
      )}
    </div>
  )
}

function Attendance({ data }: { data: Data }) {
  return (
    <section className="card stack-sm">
      <h2>{t('Meine Anwesenheit')}</h2>
      <p role="status">
        {t('Dieses Jahr {year}-mal da, in den letzten 12 Monaten {last}-mal.', {
          year: data.count_year,
          last: data.count_12,
        })}
      </p>
      {data.attendance.length === 0 ? (
        <p className="muted">{t('Noch keine Anwesenheit eingetragen.')}</p>
      ) : (
        <ul className="plain-list training-entries">
          {data.attendance.slice(0, 30).map((a) => (
            <li key={a.session}>
              {formatDate(a.date)} · {a.title}
              <span className="muted small">
                {' '}
                · {[a.kind_label, a.department_name].filter(Boolean).join(' · ')}
              </span>
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}

function Shooting({
  accessId,
  data,
  onChange,
}: {
  accessId: number
  data: Data
  onChange: (d: Data) => void
}) {
  const shooting = data.shooting!
  const [error, setError] = useState('')
  const [done, setDone] = useState('')
  const withdraw = async (id: number) => {
    setError('')
    try {
      onChange(await portalTrainingApi.withdraw(accessId, id))
    } catch (err) {
      setError(errorMessage(err))
    }
  }
  return (
    <>
      <EvaluationCard evaluation={shooting.evaluation} />
      <section className="card stack-sm">
        <h2>{t('Schießtermin melden')}</h2>
        <p className="muted small">
          {t(
            'Für Termine außerhalb der Trainings, etwa in einem anderen Verein oder bei einem Wettkampf. Der Verein prüft die Meldung und bestätigt sie; erst dann zählt sie.',
          )}
        </p>
        {done && <Alert kind="success">{done}</Alert>}
        <EntryForm
          disciplines={shooting.disciplines}
          submitLabel={t('Melden')}
          onSubmit={async (draft) => {
            setDone('')
            onChange(await portalTrainingApi.report(accessId, draft, newRequestKey()))
            setDone(t('Gemeldet. Der Verein bestätigt den Termin.'))
          }}
        />
      </section>
      <section className="card stack-sm">
        <h2>{t('Mein Schießbuch')}</h2>
        {error && <p role="alert">{error}</p>}
        {shooting.entries.length === 0 ? (
          <p className="muted">{t('Noch keine Einträge.')}</p>
        ) : (
          <ul className="plain-list training-entries">
            {shooting.entries.map((e) => (
              <li key={e.id} className={e.status === 'rejected' ? 'muted' : undefined}>
                {formatDate(e.date)}: <strong>{e.discipline}</strong>
                <span className="muted small"> · {entryDetails(e)}</span>
                <span className="badge">{e.status_label}</span>
                {e.status === 'reported' && (
                  <button type="button" className="link-button" onClick={() => void withdraw(e.id)}>
                    {t('Zurückziehen')}
                  </button>
                )}
              </li>
            ))}
          </ul>
        )}
      </section>
    </>
  )
}
