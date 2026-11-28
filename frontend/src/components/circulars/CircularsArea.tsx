// Rundschreiben: Liste, Editor mit Empfängerauswahl, Versand und Versandprotokoll.
// Dieselben Seiten dienen dem Vorstand (Mitglieder › Rundschreiben) und den
// Abteilungsrollen (Abteilung › Rundschreiben); nur die API-Adresse unterscheidet sich.
import { useEffect, useState } from 'react'
import { Link, Route, Routes, useNavigate, useParams } from 'react-router-dom'
import { baseUrl, channelLabel, circularApi } from '../../api/circulars.ts'
import { showNotice } from '../undo.ts'
import type { Circular, CircularBase, CircularSummary } from '../../api/circulars.ts'
import { confirmDialog } from '../dialog.ts'
import { errorMessage, formatDateTime, useLoad } from '../forms.ts'
import { Alert, LoadError, Loading } from '../ui.tsx'
import { MarkupPreview } from './MarkupEditor.tsx'
import { useOptionalOrg } from '../../org/OrgContext.tsx'
import { useTerms } from '../../org/terms.ts'
import { t } from '../../i18n/index.ts'
import { DraftEditor } from './DraftEditor.tsx'

export function CircularsArea({ base, root }: { base: CircularBase; root: string }) {
  return (
    <Routes>
      <Route index element={<CircularList base={base} root={root} />} />
      <Route path=":id" element={<CircularPage base={base} root={root} />} />
    </Routes>
  )
}

function CircularList({ base, root }: { base: CircularBase; root: string }) {
  const navigate = useNavigate()
  const list = useLoad(() => circularApi.list(base), [JSON.stringify(base)])
  const templates = useLoad(() => circularApi.templates(base), [JSON.stringify(base)])
  const [error, setError] = useState<string | null>(null)
  const [template, setTemplate] = useState('')

  async function create() {
    setError(null)
    try {
      const c = await circularApi.create(base, template ? { template: Number(template) } : {})
      navigate(`${root}/${c.id}`)
    } catch (err) {
      setError(errorMessage(err))
    }
  }

  async function removeTemplate(id: number, name: string) {
    if (
      !(await confirmDialog({
        final: true,
        message: t('Vorlage „{name}“ löschen?', { name }),
        confirmLabel: t('Löschen'),
      }))
    )
      return
    try {
      await circularApi.removeTemplate(base, id)
      showNotice(baseUrl(base), t('Vorlage gelöscht.'))
      await templates.reload()
    } catch (err) {
      setError(errorMessage(err))
    }
  }

  const drafts = (list.data ?? []).filter((c) => c.status === 'draft')
  const sent = (list.data ?? []).filter((c) => c.status !== 'draft')
  return (
    <div className="stack">
      <div className="card card-wide">
        <div className="card-head">
          <h2>{t('Neues Rundschreiben')}</h2>
        </div>
        <p className="muted small">
          {t(
            'Mitglieder mit E-Mail-Adresse bekommen eine Mail, alle anderen einen Brief zum Drucken.',
          )}
        </p>
        <div className="inline-add">
          {templates.data && templates.data.length > 0 && (
            <select
              aria-label={t('Vorlage')}
              value={template}
              onChange={(e) => setTemplate(e.target.value)}
            >
              <option value="">{t('ohne Vorlage')}</option>
              {templates.data.map((tmx) => (
                <option key={tmx.id} value={tmx.id}>
                  {t('Vorlage:')} {tmx.name}
                </option>
              ))}
            </select>
          )}
          <button type="button" className="button button-primary" onClick={() => void create()}>
            {t('Rundschreiben verfassen')}
          </button>
        </div>
        {error && <Alert kind="error">{error}</Alert>}
      </div>

      {list.error && <Alert kind="error">{list.error}</Alert>}
      {drafts.length > 0 && (
        <div className="card card-wide">
          <h2>{t('Entwürfe')}</h2>
          <SummaryTable rows={drafts} root={root} />
        </div>
      )}
      <div className="card card-wide">
        <h2>{t('Versendet')}</h2>
        {list.data && sent.length === 0 ? (
          <p className="muted">{t('Noch keine Rundschreiben versendet.')}</p>
        ) : (
          <SummaryTable rows={sent} root={root} />
        )}
      </div>

      {templates.data && templates.data.length > 0 && (
        <div className="card card-wide">
          <h2>{t('Vorlagen')}</h2>
          <ul className="plain-list">
            {templates.data.map((tmx) => (
              <li key={tmx.id}>
                <strong>{tmx.name}</strong>{' '}
                <span className="muted small">
                  {tmx.kind === 'notice'
                    ? t('Offizielle Mitteilung')
                    : tmx.kind === 'short'
                      ? t('Kurzmitteilung')
                      : t('Information')}
                  {tmx.subject && t(' · {subject}', { subject: tmx.subject })}
                </span>
                <button
                  type="button"
                  className="link-button spaced"
                  onClick={() => void removeTemplate(tmx.id, tmx.name)}
                >
                  {t('löschen')}
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  )
}

function SummaryTable({ rows, root }: { rows: CircularSummary[]; root: string }) {
  return (
    <div className="table-scroll">
      <table className="table">
        <thead>
          <tr>
            <th>{t('Betreff')}</th>
            <th>{t('Art')}</th>
            <th className="col-optional">{t('Absender')}</th>
            <th>{rows.some((r) => r.sent_at) ? t('Versendet') : t('Geändert')}</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((c) => (
            <tr key={c.id}>
              <td>
                <Link to={`${root}/${c.id}`}>{c.subject || t('ohne Betreff')}</Link>
                {c.status === 'sending' && (
                  <span className="badge badge-open">{t('wird versendet')}</span>
                )}
              </td>
              <td>{c.kind_label}</td>
              <td className="col-optional">{c.department?.name ?? '–'}</td>
              <td className="small">
                {formatDateTime(c.sent_at ?? c.updated_at)}
                {c.sent_by && <div className="muted">{c.sent_by}</div>}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function CircularPage({ base, root }: { base: CircularBase; root: string }) {
  const id = Number(useParams().id)
  const circular = useLoad(() => circularApi.get(base, id), [JSON.stringify(base), id])
  const options = useLoad(() => circularApi.options(base), [JSON.stringify(base)])
  if (circular.error) return <LoadError message={circular.error} onRetry={circular.reload} />
  if (options.error)
    return (
      <LoadError
        message={t('Die Empfängerauswahl konnte nicht geladen werden. {error}', {
          error: options.error,
        })}
        onRetry={options.reload}
      />
    )
  if (!circular.data || !options.data) return <Loading />
  const back = (
    <p>
      <Link to={root}>{t('← Alle Rundschreiben')}</Link>
    </p>
  )
  if (!circular.data.can_edit)
    return (
      <>
        {back}
        <SentView base={base} root={root} circular={circular.data} onReload={circular.reload} />
      </>
    )
  return (
    <>
      {back}
      <DraftEditor
        key={circular.data.id}
        base={base}
        root={root}
        initial={circular.data}
        options={options.data}
        onSent={circular.reload}
      />
    </>
  )
}

function SentView({
  base,
  root,
  circular,
  onReload,
}: {
  base: CircularBase
  root: string
  circular: Circular
  onReload: () => Promise<void>
}) {
  const tm = useTerms()
  const activeType = useOptionalOrg()?.active?.type
  const navigate = useNavigate()
  // Versandprotokoll seitenweise zu je 200 (Gesamtaudit 15.11., PF-28)
  const [pages, setPages] = useState(1)
  const recipients = useLoad(
    () => circularApi.recipientPages(base, circular.id, pages),
    [JSON.stringify(base), circular.id, circular.status, pages],
  )
  const [error, setError] = useState<string | null>(null)
  const sending = circular.status === 'sending'

  // Während des Versands den Stand alle paar Sekunden neu laden
  useEffect(() => {
    if (!sending) return
    // Nie zwei Abrufe gleichzeitig (langsames Netz, Gesamtaudit 30.10. WEB-P02)
    let busy = false
    const timer = setInterval(() => {
      if (busy) return
      busy = true
      onReload()
        .catch(() => undefined)
        .finally(() => {
          busy = false
        })
    }, 4000)
    return () => clearInterval(timer)
  }, [sending, onReload])

  async function reuse() {
    try {
      const c = await circularApi.create(base, { copy_of: circular.id })
      navigate(`${root}/${c.id}`)
    } catch (err) {
      setError(errorMessage(err))
    }
  }

  async function resend() {
    const open = (counts?.failed ?? 0) + (counts?.unclear ?? 0)
    const question =
      (counts?.unclear ?? 0) > 0
        ? t('{open} E-Mails erneut senden? Bei „Versand unklar“ ist offen, ob die Mail schon ', {
            open,
          }) + t('ankam; sie kann dann doppelt ankommen.')
        : t('{open} fehlgeschlagene E-Mails erneut senden?', { open })
    if (
      !(await confirmDialog({ message: question, confirmLabel: t('Erneut senden'), danger: false }))
    )
      return
    try {
      await circularApi.resend(base, circular.id)
      setError(null)
      await onReload()
    } catch (err) {
      setError(errorMessage(err))
    }
  }

  const counts = circular.counts
  const retryable = (counts?.failed ?? 0) + (counts?.unclear ?? 0)
  return (
    <div className="stack">
      <div className="card card-wide">
        <div className="card-head">
          <h2>{circular.subject}</h2>
          <span className="badge">{circular.kind_label}</span>
          {sending && <span className="badge badge-open">{t('wird versendet')}</span>}
        </div>
        <p className="muted small">
          {circular.sent_at && t('Versendet am {x}', { x: formatDateTime(circular.sent_at) })}
          {circular.sent_by && t(' von {sent_by}', { sent_by: circular.sent_by })}
          {circular.department && t(' · {name}', { name: circular.department.name })}
          {circular.reply_to && t(' · Antworten an {reply_to}', { reply_to: circular.reply_to })}
        </p>
        <MarkupPreview text={circular.body} />
        {circular.attachments.length > 0 && (
          <p>
            {t('Anhänge:')}{' '}
            {circular.attachments.map((a, i) => (
              <span key={a.id}>
                {i > 0 && ', '}
                <a href={a.url} target="_blank" rel="noreferrer">
                  {a.name}
                </a>
              </span>
            ))}
          </p>
        )}
        <div className="button-row">
          {counts && counts.letter > 0 && (
            <a
              className="button button-primary"
              href={circularApi.lettersUrl(base, circular.id)}
              target="_blank"
              rel="noreferrer"
            >
              {counts.letter} {counts.letter === 1 ? t('Brief') : t('Briefe')} {t('drucken (PDF)')}
            </a>
          )}
          <button type="button" className="button button-ghost" onClick={() => void reuse()}>
            {t('Erneut verwenden')}
          </button>
        </div>
        {error && <Alert kind="error">{error}</Alert>}
      </div>

      <div className="card card-wide">
        <h2>{t('Versandprotokoll')}</h2>
        {counts && (
          <p>
            {(counts.app ?? 0) > 0 && t('{app} per App · ', { app: counts.app })}
            {counts.mail} {t('E-Mails')}
            {counts.sent !== undefined && t(': {sent} gesendet', { sent: counts.sent })}
            {counts.pending > 0 && t(' ({x0} noch offen)', { x0: counts.pending })}
            {counts.failed > 0 && t(', {failed} fehlgeschlagen', { failed: counts.failed })}
            {(counts.unclear ?? 0) > 0 &&
              t(', {unclear} Versand unklar', { unclear: counts.unclear })}{' '}
            {t('· {letter}  Briefe', { letter: counts.letter })}
            {(counts.portal ?? 0) > 0 &&
              t(' · {portal} nur im Mitgliederbereich', { portal: counts.portal })}
          </p>
        )}
        {retryable > 0 && (
          <p>
            <button type="button" className="button button-ghost" onClick={() => void resend()}>
              {retryable} {retryable === 1 ? t('E-Mail') : t('E-Mails')} {t('erneut senden')}
            </button>
          </p>
        )}
        {recipients.error && <Alert kind="error">{recipients.error}</Alert>}
        {recipients.data && (
          <div className="table-scroll">
            <table className="table">
              <thead>
                <tr>
                  <th>{t('Name')}</th>
                  <th className="col-optional">{activeType === 'federation' ? tm.Sg : tm.e_Sg}</th>
                  <th>{t('Weg')}</th>
                  <th>{t('Stand')}</th>
                </tr>
              </thead>
              <tbody>
                {recipients.data.items.map((r) => (
                  <tr key={r.key}>
                    <td>
                      {r.last_name}
                      {r.first_name && t(', {first_name}', { first_name: r.first_name })}
                      {r.email && <div className="muted small">{r.email}</div>}
                    </td>
                    <td className="col-optional">{r.club}</td>
                    <td>{r.channel ? channelLabel[r.channel] : '–'}</td>
                    <td>
                      {r.status_label}
                      {r.error && <div className="field-error small">{r.error}</div>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            {recipients.data.page?.more && (
              <button
                type="button"
                className="button"
                disabled={recipients.loading}
                onClick={() => setPages((n) => n + 1)}
              >
                {t('Weitere laden ({n} von {total})', {
                  n: recipients.data.items.length,
                  total: recipients.data.page.total,
                })}
              </button>
            )}
          </div>
        )}
      </div>
    </div>
  )
}
