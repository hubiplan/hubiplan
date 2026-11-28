// Datenschutz-Werkzeuge (Lückenliste 20.11.2026, B5): Verzeichnis der Verarbeitungstätigkeiten
// aus den eingeschalteten Modulen, Auftragsverarbeiter aus den Geschäftspartnern und das
// Protokoll von Datenpannen mit der 72-Stunden-Frist. Ein Vorschlag, keine Rechtsberatung.
import { EditAt } from '../../components/EditInPlace.tsx'
import { useEffect, useRef, useState } from 'react'
import { Link, Route, Routes } from 'react-router-dom'
import { dsgvoApi, dsgvoBase } from '../../api/dsgvo.ts'
import type { Breach, BreachInput, BreachRisk } from '../../api/dsgvo.ts'
import { PERM } from '../../api/orgs.ts'
import { PageHeader } from '../../components/PageHeader.tsx'
import { useDetailParam } from '../../components/detailParam.ts'
import { confirmDialog } from '../../components/dialog.ts'
import { errorMessage, formatDate, formatDateTime, useLoad } from '../../components/forms.ts'
import { Alert, Field, LoadError, Loading, SelectField, Tabs } from '../../components/ui.tsx'
import { t } from '../../i18n/index.ts'
import { useOrg } from '../../org/OrgContext.tsx'
import { NoAccessPage } from '../NoticePages.tsx'
import { TextArea } from '../settings/TextArea.tsx'
import './dsgvo.css'
import { ROOT } from './dsgvoHelpers.ts'
import { RegisterArea } from './RegisterArea.tsx'

/** Wert für ein datetime-local-Feld in der Zeitzone des Browsers */
function localInput(value?: string | null) {
  if (!value) return ''
  const date = new Date(value)
  return new Date(date.getTime() - date.getTimezoneOffset() * 60000).toISOString().slice(0, 16)
}

function fromInput(value: string): string | null {
  return value ? new Date(value).toISOString() : null
}

export function DsgvoPage() {
  const { active } = useOrg()
  if (
    !active ||
    (active.type !== 'club' && active.type !== 'federation') ||
    !active.permissions.includes(PERM.privacyView)
  ) {
    return <NoAccessPage reason={active ? 'right' : 'workspace'} />
  }
  const base = dsgvoBase(active.id)
  return (
    <section className="stack">
      <PageHeader
        subtitle={t(
          'Verzeichnis der Verarbeitungstätigkeiten, Auftragsverarbeiter und Datenpannen. Ein Vorschlag aus den genutzten Modulen, keine Rechtsberatung.',
        )}
      />
      <Tabs
        items={[
          { to: ROOT, label: t('Verzeichnis') },
          { to: `${ROOT}/auftragsverarbeiter`, label: t('Auftragsverarbeiter') },
          { to: `${ROOT}/datenpannen`, label: t('Datenpannen') },
        ]}
      />
      <Routes>
        <Route path="auftragsverarbeiter" element={<ProcessorsArea base={base} />} />
        <Route path="datenpannen" element={<BreachesArea base={base} />} />
        <Route path="*" element={<RegisterArea base={base} />} />
      </Routes>
    </section>
  )
}

// --- Verzeichnis ---

function ProcessorsArea({ base: url }: { base: string }) {
  const { data, error, reload } = useLoad(() => dsgvoApi.overview(url), [url])
  if (error) return <LoadError message={error} onRetry={reload} />
  if (!data) return <Loading />
  const missing = data.processors.filter((p) => !p.agreement)
  return (
    <section className="card card-wide stack">
      <h2>{t('Auftragsverarbeiter')}</h2>
      <p className="muted small">
        {t(
          'Dienstleister, die personenbezogene Daten im Auftrag des Vereins verarbeiten (etwa Hosting, Mailversand, Druckerei für Mitgliederbriefe), brauchen einen Vertrag nach Art. 28 DSGVO. Lege sie als Geschäftspartner mit der Rolle „Auftragsverarbeiter“ an und hinterlege den Vertrag als Vereinbarung der Art „Auftragsverarbeitungsvertrag“.',
        )}
      </p>
      {missing.length > 0 && (
        <Alert kind="info">
          {t('Bei {n} Auftragsverarbeitern fehlt ein gültiger Vertrag.', { n: missing.length })}
        </Alert>
      )}
      <ul className="item-list">
        {data.settings.hoster && (
          <li className="item-row">
            <div className="item-row-info">
              <strong>{data.settings.hoster}</strong>
              <div className="muted small">{t('Betreiber der HUBIplan-Instanz')}</div>
            </div>
          </li>
        )}
        {data.processors.map((p) => (
          <li key={p.id} className="item-row">
            <div className="item-row-info">
              <strong>{p.name}</strong>
              <div className="muted small">
                {p.agreement
                  ? t('Vertrag „{title}“ seit {date}', {
                      title: p.agreement.title,
                      date: formatDate(p.agreement.start),
                    })
                  : t('kein Vertrag zur Auftragsverarbeitung hinterlegt')}
              </div>
            </div>
            {p.agreement ? (
              <span className="badge badge-public">{t('Vertrag liegt vor')}</span>
            ) : (
              <span className="badge badge-cancelled">{t('Vertrag fehlt')}</span>
            )}
          </li>
        ))}
      </ul>
      {data.processors.length === 0 && !data.settings.hoster && (
        <p>{t('Noch keine Auftragsverarbeiter eingetragen.')}</p>
      )}
      {data.can_partners && (
        <p className="small">
          <Link to="/geschaeftspartner">{t('Zu den Geschäftspartnern')}</Link>
        </p>
      )}
    </section>
  )
}

// --- Datenpannen ---

function StatusBadge({ b }: { b: Breach }) {
  if (b.status === 'overdue')
    return <span className="badge badge-cancelled">{t('Meldefrist abgelaufen')}</span>
  if (b.status === 'report_due')
    return <span className="badge badge-open">{t('Meldung offen')}</span>
  if (b.status === 'closed') return <span className="badge badge-public">{t('abgeschlossen')}</span>
  return <span className="badge">{t('in Bearbeitung')}</span>
}

function riskLabel(risk: BreachRisk) {
  return {
    unlikely: t('voraussichtlich kein Risiko'),
    risk: t('Risiko'),
    high: t('hohes Risiko'),
  }[risk]
}

type BreachDraft = Record<
  | 'title'
  | 'discovered_at'
  | 'occurred'
  | 'description'
  | 'categories'
  | 'affected'
  | 'consequences'
  | 'measures'
  | 'reported_at'
  | 'report_reference'
  | 'no_report_reason'
  | 'notified_at',
  string
> & { risk: BreachRisk }

function draftOf(b: Breach | null, now: string): BreachDraft {
  return {
    title: b?.title ?? '',
    discovered_at: b ? localInput(b.discovered_at) : now,
    occurred: b?.occurred ?? '',
    description: b?.description ?? '',
    categories: b?.categories ?? '',
    affected: b?.affected ?? '',
    consequences: b?.consequences ?? '',
    measures: b?.measures ?? '',
    risk: b?.risk ?? 'risk',
    reported_at: localInput(b?.reported_at),
    report_reference: b?.report_reference ?? '',
    no_report_reason: b?.no_report_reason ?? '',
    notified_at: localInput(b?.notified_at),
  }
}

function BreachForm({
  initial,
  submitLabel,
  onSubmit,
  onCancel,
}: {
  initial: BreachDraft
  submitLabel: string
  onSubmit: (input: BreachInput) => Promise<void>
  onCancel: () => void
}) {
  const [d, setD] = useState(initial)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const set = <K extends keyof BreachDraft>(key: K, value: BreachDraft[K]) =>
    setD({ ...d, [key]: value })
  const area = (key: keyof BreachDraft, label: string, hint?: string) => (
    <TextArea label={label} hint={hint} value={d[key]} onChange={(v) => set(key, v as never)} />
  )
  return (
    <form
      className="stack"
      onSubmit={async (e) => {
        e.preventDefault()
        setBusy(true)
        setError(null)
        try {
          await onSubmit({
            ...d,
            discovered_at: fromInput(d.discovered_at) ?? undefined,
            reported_at: fromInput(d.reported_at),
            notified_at: fromInput(d.notified_at),
          })
        } catch (err) {
          setError(errorMessage(err))
          setBusy(false)
        }
      }}
    >
      <Field
        label={t('Kurzbezeichnung')}
        required
        maxLength={200}
        value={d.title}
        onChange={(e) => set('title', e.target.value)}
      />
      <div className="grid-2">
        <Field
          label={t('Bekannt geworden am')}
          hint={t('Ab hier laufen die 72 Stunden für die Meldung.')}
          type="datetime-local"
          required
          value={d.discovered_at}
          onChange={(e) => set('discovered_at', e.target.value)}
        />
        <Field
          label={t('Zeitpunkt oder Zeitraum der Panne')}
          maxLength={200}
          value={d.occurred}
          onChange={(e) => set('occurred', e.target.value)}
        />
      </div>
      {area('description', t('Was ist passiert?'))}
      <div className="grid-2">
        {area('categories', t('Betroffene Daten'))}
        <Field
          label={t('Betroffene Personen (Art, ungefähre Zahl)')}
          maxLength={300}
          value={d.affected}
          onChange={(e) => set('affected', e.target.value)}
        />
      </div>
      {area('consequences', t('Wahrscheinliche Folgen'))}
      {area(
        'measures',
        t('Ergriffene Maßnahmen'),
        t('Was wurde getan, um die Panne zu beheben und Folgen zu mildern?'),
      )}
      <SelectField
        label={t('Einschätzung des Risikos für die Betroffenen')}
        hint={t(
          'Bei Risiko muss die Panne binnen 72 Stunden der Aufsichtsbehörde gemeldet werden, bei hohem Risiko sind auch die Betroffenen zu benachrichtigen.',
        )}
        value={d.risk}
        onChange={(e) => set('risk', e.target.value as BreachRisk)}
      >
        {(['unlikely', 'risk', 'high'] as const).map((r) => (
          <option key={r} value={r}>
            {riskLabel(r)}
          </option>
        ))}
      </SelectField>
      <div className="grid-2">
        <Field
          label={t('Gemeldet an die Aufsichtsbehörde')}
          type="datetime-local"
          value={d.reported_at}
          onChange={(e) => set('reported_at', e.target.value)}
        />
        <Field
          label={t('Aktenzeichen der Meldung')}
          maxLength={100}
          value={d.report_reference}
          onChange={(e) => set('report_reference', e.target.value)}
        />
      </div>
      {area(
        'no_report_reason',
        t('Begründung'),
        t('Warum nicht oder nicht rechtzeitig gemeldet wurde.'),
      )}
      <Field
        label={t('Betroffene benachrichtigt')}
        type="datetime-local"
        value={d.notified_at}
        onChange={(e) => set('notified_at', e.target.value)}
      />
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

function BreachesArea({ base: url }: { base: string }) {
  const { data, error, reload, setData } = useLoad(() => dsgvoApi.breaches(url), [url])
  const detail = useDetailParam('panne')
  const [editing, setEditing] = useState<number | 'new' | null>(null)
  const [now] = useState(() => localInput(new Date().toISOString()))
  const [actionError, setActionError] = useState<string | null>(null)
  const marked = useRef<HTMLLIElement | null>(null)
  const focus = detail.value ? Number(detail.value) : null
  const loaded = !!data
  useEffect(() => {
    if (loaded && focus) marked.current?.scrollIntoView?.({ block: 'center' })
  }, [loaded, focus])
  if (error) return <LoadError message={error} onRetry={reload} />
  if (!data) return <Loading />
  const edit = data.can_edit
  const replace = (b: Breach) =>
    setData({ ...data, items: data.items.map((x) => (x.id === b.id ? b : x)) })
  const close = async (b: Breach, closed: boolean) => {
    setActionError(null)
    try {
      replace(await dsgvoApi.updateBreach(url, b.id, { closed, version: b.version }))
    } catch (err) {
      setActionError(errorMessage(err))
    }
  }
  const remove = async (b: Breach) => {
    const yes = await confirmDialog({
      final: true,
      message: t(
        'Eintrag „{name}“ löschen? Nur für versehentliche Einträge; eine echte Panne muss dokumentiert bleiben.',
        { name: b.title },
      ),
      confirmLabel: t('Löschen'),
    })
    if (!yes) return
    setActionError(null)
    try {
      await dsgvoApi.removeBreach(url, b.id)
      reload()
    } catch (err) {
      setActionError(errorMessage(err))
    }
  }
  return (
    <div className="stack">
      <section className="card card-wide stack">
        <div className="card-head">
          <h2>{t('Datenpannen')}</h2>
          {edit && editing !== 'new' && (
            <button
              type="button"
              className="button button-primary"
              onClick={() => setEditing('new')}
            >
              {t('Datenpanne erfassen')}
            </button>
          )}
        </div>
        <p className="muted small">
          {t(
            'Jede Verletzung des Schutzes personenbezogener Daten wird dokumentiert (Art. 33 Abs. 5 DSGVO), etwa eine Mail mit offenem Verteiler, ein verlorener USB-Stick oder ein geknacktes Konto. Besteht ein Risiko für die Betroffenen, muss der Verein sie binnen 72 Stunden der Aufsichtsbehörde melden.',
          )}
        </p>
        {editing === 'new' && (
          <BreachForm
            initial={draftOf(null, now)}
            submitLabel={t('Datenpanne speichern')}
            onCancel={() => setEditing(null)}
            onSubmit={async (input) => {
              await dsgvoApi.createBreach(url, input)
              setEditing(null)
              reload()
            }}
          />
        )}
        {actionError && <Alert kind="error">{actionError}</Alert>}
        {data.items.length === 0 ? (
          <p>{t('Keine Datenpannen dokumentiert.')}</p>
        ) : (
          <ul className="item-list dsgvo-list">
            {data.items.map((b) => (
              <li
                key={b.id}
                ref={focus === b.id ? marked : undefined}
                className={focus === b.id ? 'dsgvo-marked' : undefined}
              >
                {editing === b.id ? (
                  <EditAt at={null}>
                    <BreachForm
                      initial={draftOf(b, now)}
                      submitLabel={t('Speichern')}
                      onCancel={() => setEditing(null)}
                      onSubmit={async (input) => {
                        replace(
                          await dsgvoApi.updateBreach(url, b.id, { ...input, version: b.version }),
                        )
                        setEditing(null)
                      }}
                    />
                  </EditAt>
                ) : (
                  <div className="item-row">
                    <div className="item-row-info">
                      <div>
                        <strong>{b.title}</strong> <StatusBadge b={b} />
                      </div>
                      <div className="muted small">
                        {[
                          t('bekannt seit {date}', { date: formatDateTime(b.discovered_at) }),
                          riskLabel(b.risk),
                          b.reported_at
                            ? t('gemeldet am {date}', { date: formatDateTime(b.reported_at) })
                            : b.risk !== 'unlikely' && !b.closed_at
                              ? t('Meldung bis {date}', { date: formatDateTime(b.report_deadline) })
                              : '',
                        ]
                          .filter(Boolean)
                          .join(' · ')}
                      </div>
                      {b.description && <p className="small pre-line">{b.description}</p>}
                    </div>
                    <div className="button-row">
                      <a
                        className="button button-ghost"
                        href={dsgvoApi.breachPdfUrl(url, b.id)}
                        target="_blank"
                        rel="noreferrer"
                      >
                        {t('PDF')}
                      </a>
                      {edit && !b.closed_at && (
                        <>
                          <button type="button" className="button" onClick={() => setEditing(b.id)}>
                            {t('Bearbeiten')}
                          </button>
                          <button
                            type="button"
                            className="button button-primary"
                            onClick={() => void close(b, true)}
                          >
                            {t('Abschließen')}
                          </button>
                        </>
                      )}
                      {edit && b.closed_at && (
                        <button
                          type="button"
                          className="button"
                          onClick={() => void close(b, false)}
                        >
                          {t('Wieder öffnen')}
                        </button>
                      )}
                      {edit && (
                        <button
                          type="button"
                          className="button button-danger"
                          onClick={() => void remove(b)}
                        >
                          {t('Löschen')}
                        </button>
                      )}
                    </div>
                  </div>
                )}
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  )
}
