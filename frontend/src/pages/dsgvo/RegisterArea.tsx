import { EditAt } from '../../components/EditInPlace.tsx'
import { useState } from 'react'
import { Link } from 'react-router-dom'
import { dsgvoApi } from '../../api/dsgvo.ts'
import type { Activity, ActivityInput, PrivacyOverview, PrivacySettings } from '../../api/dsgvo.ts'
import { confirmDialog } from '../../components/dialog.ts'
import { errorMessage, useLoad } from '../../components/forms.ts'
import { Alert, Field, LoadError, Loading } from '../../components/ui.tsx'
import { t } from '../../i18n/index.ts'
import { TextArea } from '../settings/TextArea.tsx'
import './dsgvo.css'
import { ROOT } from './dsgvoHelpers.ts'

function SettingsCard({
  url,
  data,
  onSaved,
}: {
  url: string
  data: PrivacyOverview
  onSaved: (s: PrivacySettings) => void
}) {
  const [d, setD] = useState(data.settings)
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState<{ kind: 'error' | 'success'; text: string } | null>(null)
  const c = data.controller
  const edit = data.can_edit
  return (
    <form
      className="card card-wide stack"
      onSubmit={async (e) => {
        e.preventDefault()
        setBusy(true)
        setMessage(null)
        try {
          const saved = await dsgvoApi.saveSettings(url, d)
          onSaved({ ...d, ...saved })
          setD({ ...d, ...saved })
          setMessage({ kind: 'success', text: t('Gespeichert.') })
        } catch (err) {
          setMessage({ kind: 'error', text: errorMessage(err) })
        } finally {
          setBusy(false)
        }
      }}
    >
      <h2>{t('Verantwortlicher')}</h2>
      <p className="small">
        <strong>{c.name}</strong>
        {c.address && (
          <>
            <br />
            {c.address}
          </>
        )}
        {c.representatives && (
          <>
            <br />
            {t('Vertreten durch: {names}', { names: c.representatives })}
          </>
        )}
        {c.contact && (
          <>
            <br />
            {c.contact}
          </>
        )}
      </p>
      <p className="muted small">
        {t('Name, Anschrift und Vertretung kommen aus dem Impressum')} (
        <Link to="/einstellungen/impressum">{t('Einstellungen › Impressum')}</Link>).
      </p>
      {edit ? (
        <>
          <div className="grid-2">
            <Field
              label={t('Datenschutzbeauftragte/r')}
              hint={t('Leer lassen, wenn der Verein keine Person benennen muss.')}
              maxLength={200}
              value={d.dpo_name}
              onChange={(e) => setD({ ...d, dpo_name: e.target.value })}
            />
            <Field
              label={t('Kontakt der/des Datenschutzbeauftragten')}
              maxLength={300}
              value={d.dpo_contact}
              onChange={(e) => setD({ ...d, dpo_contact: e.target.value })}
            />
          </div>
          <Field
            label={t('Betreiber der HUBIplan-Instanz')}
            hint={t(
              'Wer den Server betreibt, auf dem HUBIplan für den Verein läuft. Erscheint unter den Auftragsverarbeitern.',
            )}
            maxLength={300}
            value={d.hoster}
            onChange={(e) => setD({ ...d, hoster: e.target.value })}
          />
          <TextArea
            label={t('Technische und organisatorische Maßnahmen (Art. 32 DSGVO)')}
            hint={t(
              'Vorgabe beschreibt, was HUBIplan selbst leistet. Ergänze, was der Verein außerhalb von HUBIplan tut, etwa abschließbare Schränke für Papierakten.',
            )}
            rows={6}
            value={d.toms}
            onChange={(v) => setD({ ...d, toms: v })}
          />
          {message && <Alert kind={message.kind}>{message.text}</Alert>}
          <div className="button-row">
            <button type="submit" className="button button-primary" disabled={busy}>
              {t('Speichern')}
            </button>
          </div>
        </>
      ) : (
        <>
          <p className="small">
            {t('Datenschutzbeauftragte/r')}:{' '}
            {[d.dpo_name, d.dpo_contact].filter(Boolean).join(' · ') || t('nicht benannt')}
          </p>
          <h3>{t('Technische und organisatorische Maßnahmen (Art. 32 DSGVO)')}</h3>
          <p className="small pre-line">{d.toms}</p>
        </>
      )}
    </form>
  )
}

const EMPTY: ActivityInput = {
  title: '',
  purpose: '',
  legal_basis: '',
  subjects: '',
  categories: '',
  recipients: '',
  third_country: '',
  retention: '',
}

function ActivityForm({
  initial,
  submitLabel,
  onSubmit,
  onCancel,
}: {
  initial: ActivityInput
  submitLabel: string
  onSubmit: (input: ActivityInput) => Promise<void>
  onCancel: () => void
}) {
  const [d, setD] = useState(initial)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const text = (key: keyof ActivityInput, label: string, rows = 2) => (
    <TextArea
      label={label}
      rows={rows}
      value={String(d[key] ?? '')}
      onChange={(v) => setD({ ...d, [key]: v })}
    />
  )
  return (
    <form
      className="stack"
      onSubmit={async (e) => {
        e.preventDefault()
        setBusy(true)
        setError(null)
        try {
          await onSubmit(d)
        } catch (err) {
          setError(errorMessage(err))
          setBusy(false)
        }
      }}
    >
      <Field
        label={t('Bezeichnung')}
        required
        maxLength={200}
        value={d.title ?? ''}
        onChange={(e) => setD({ ...d, title: e.target.value })}
      />
      {text('purpose', t('Zweck'))}
      <div className="grid-2">
        <Field
          label={t('Rechtsgrundlage')}
          maxLength={300}
          value={d.legal_basis ?? ''}
          onChange={(e) => setD({ ...d, legal_basis: e.target.value })}
        />
        <Field
          label={t('Betroffene')}
          maxLength={300}
          value={d.subjects ?? ''}
          onChange={(e) => setD({ ...d, subjects: e.target.value })}
        />
      </div>
      {text('categories', t('Datenkategorien'))}
      {text('recipients', t('Empfänger'))}
      <Field
        label={t('Übermittlung in Drittländer')}
        maxLength={300}
        value={d.third_country ?? ''}
        onChange={(e) => setD({ ...d, third_country: e.target.value })}
      />
      {text('retention', t('Löschfrist'))}
      {error && <Alert kind="error">{error}</Alert>}
      <div className="button-row">
        <button type="submit" className="button button-primary" disabled={busy}>
          {submitLabel}
        </button>
        <button type="button" className="button" onClick={onCancel}>
          {t('Abbrechen')}
        </button>
      </div>
    </form>
  )
}

function ActivityDetails({ a }: { a: Activity }) {
  const rows: [string, string][] = [
    [t('Zweck'), a.purpose],
    [t('Rechtsgrundlage'), a.legal_basis],
    [t('Betroffene'), a.subjects],
    [t('Datenkategorien'), a.categories],
    [t('Empfänger'), a.recipients],
    [t('Übermittlung in Drittländer'), a.third_country],
    [t('Löschfrist'), a.retention],
  ]
  return (
    <dl className="small dsgvo-fields">
      {rows.map(([label, value]) => (
        <div key={label}>
          <dt>{label}</dt>
          <dd>{value || '–'}</dd>
        </div>
      ))}
    </dl>
  )
}

export function RegisterArea({ base: url }: { base: string }) {
  const { data, error, reload, setData } = useLoad(() => dsgvoApi.overview(url), [url])
  const [editing, setEditing] = useState<number | 'new' | null>(null)
  const [actionError, setActionError] = useState<string | null>(null)
  if (error) return <LoadError message={error} onRetry={reload} />
  if (!data) return <Loading />
  const edit = data.can_edit
  const run = async (action: () => Promise<unknown>) => {
    setActionError(null)
    try {
      await action()
      reload()
    } catch (err) {
      setActionError(errorMessage(err))
    }
  }
  const remove = async (a: Activity) => {
    const yes = await confirmDialog({
      final: true,
      message: t('Tätigkeit „{name}“ aus dem Verzeichnis löschen?', { name: a.title }),
      confirmLabel: t('Löschen'),
    })
    if (yes && a.id) await run(() => dsgvoApi.removeActivity(url, a.id as number))
  }
  const visible = data.activities.filter((a) => !a.hidden)
  const hidden = data.activities.filter((a) => a.hidden)
  return (
    <div className="stack">
      {data.open_breaches.some((b) => b.status !== 'open') && (
        <Alert kind="error">
          {t('Eine Datenpanne wartet auf die Meldung an die Aufsichtsbehörde.')}{' '}
          <Link to={`${ROOT}/datenpannen`}>{t('Zu den Datenpannen')}</Link>
        </Alert>
      )}
      <SettingsCard
        url={url}
        data={data}
        onSaved={(s) => setData({ ...data, settings: { ...data.settings, ...s } })}
      />
      <section className="card card-wide stack">
        <div className="card-head">
          <h2>{t('Verarbeitungstätigkeiten')}</h2>
          <div className="button-row">
            <a
              className="button button-ghost"
              href={dsgvoApi.registerPdfUrl(url)}
              target="_blank"
              rel="noreferrer"
            >
              {t('Verzeichnis als PDF')}
            </a>
            {edit && editing !== 'new' && (
              <button type="button" className="button" onClick={() => setEditing('new')}>
                {t('Eigene Tätigkeit')}
              </button>
            )}
          </div>
        </div>
        <p className="muted small">
          {t(
            'HUBIplan schlägt je eingeschaltetem Modul eine Tätigkeit vor. Prüfe die Angaben; was der Verein nicht nutzt, blendest du aus. Was der Verein außerhalb von HUBIplan verarbeitet (etwa Fahrgemeinschaften oder Fotos in einer Messenger-Gruppe), legst du als eigene Tätigkeit an.',
          )}
        </p>
        {editing === 'new' && (
          <EditAt at={null}>
            <ActivityForm
              initial={EMPTY}
              submitLabel={t('Tätigkeit speichern')}
              onCancel={() => setEditing(null)}
              onSubmit={async (input) => {
                await dsgvoApi.createActivity(url, input)
                setEditing(null)
                reload()
              }}
            />
          </EditAt>
        )}
        {actionError && <Alert kind="error">{actionError}</Alert>}
        <ul className="item-list dsgvo-list">
          {visible.map((a) => (
            <li key={a.id ?? a.key}>
              {editing === a.id && a.id ? (
                <EditAt at={null}>
                  <ActivityForm
                    initial={a}
                    submitLabel={t('Speichern')}
                    onCancel={() => setEditing(null)}
                    onSubmit={async (input) => {
                      await dsgvoApi.updateActivity(url, a.id as number, input)
                      setEditing(null)
                      reload()
                    }}
                  />
                </EditAt>
              ) : (
                <details>
                  <summary>
                    <strong>{a.title}</strong>{' '}
                    <span className="muted small">
                      {a.key ? t('Vorschlag aus HUBIplan') : t('eigene Tätigkeit')}
                    </span>
                  </summary>
                  <ActivityDetails a={a} />
                  {edit && (
                    <div className="button-row">
                      {a.key ? (
                        <button
                          type="button"
                          className="button"
                          onClick={() => void run(() => dsgvoApi.hide(url, a.key, true))}
                        >
                          {t('Ausblenden')}
                        </button>
                      ) : (
                        <>
                          <button type="button" className="button" onClick={() => setEditing(a.id)}>
                            {t('Bearbeiten')}
                          </button>
                          <button
                            type="button"
                            className="button button-danger"
                            onClick={() => void remove(a)}
                          >
                            {t('Löschen')}
                          </button>
                        </>
                      )}
                    </div>
                  )}
                </details>
              )}
            </li>
          ))}
        </ul>
        {edit && hidden.length > 0 && (
          <>
            <h3>{t('Ausgeblendet')}</h3>
            <ul className="item-list">
              {hidden.map((a) => (
                <li key={a.key} className="item-row">
                  <span className="item-row-info muted">{a.title}</span>
                  <button
                    type="button"
                    className="button"
                    onClick={() => void run(() => dsgvoApi.hide(url, a.key, false))}
                  >
                    {t('Wieder aufnehmen')}
                  </button>
                </li>
              ))}
            </ul>
          </>
        )}
      </section>
    </div>
  )
}

// --- Auftragsverarbeiter ---
