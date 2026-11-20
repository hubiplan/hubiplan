// Rundschreiben › Glückwünsche: Geburtstage und Mitgliedsjubiläen automatisch gratulieren.
// Einige Tage vorher entsteht ein Entwurf (Briefe drucken), am Tag geht er per App oder
// Mail hinaus, von selbst oder nach Freigabe. Mitglieder können widersprechen.
import { useState } from 'react'
import { Link } from 'react-router-dom'
import { ApiError } from '../../api/client.ts'
import { greetingApi } from '../../api/greetings.ts'
import type { GreetingBatch, GreetingOccasion, GreetingSettings } from '../../api/greetings.ts'
import { confirmDialog } from '../dialog.ts'
import { errorMessage, formatDate, formatDateTime, useLoad } from '../forms.ts'
import { Alert, Checkbox, Field, LoadError, Loading, SelectField, StatusMessage } from '../ui.tsx'
import { MarkupEditor } from './MarkupEditor.tsx'
import { useRowSearch } from '../RowSearch.tsx'
import { useRowSort } from '../RowSort.tsx'
import { t } from '../../i18n/index.ts'

type Texts = 'birthday_subject' | 'birthday_body' | 'jubilee_subject' | 'jubilee_body'

function placeholders() {
  return [
    { name: 'Anrede Du', label: t('„Lieber …“ / „Liebe …“ mit Vorname') },
    { name: 'Anrede', label: t('„Sehr geehrter Herr …“ / „Sehr geehrte Frau …“') },
    { name: 'Vorname', label: t('Vorname') },
    { name: 'Nachname', label: t('Nachname') },
    { name: 'Alter', label: t('Alter am Geburtstag') },
    { name: 'Jubiläumsjahre', label: t('Jahre im Verein beim Jubiläum') },
    { name: 'Verein', label: t('Name des Vereins') },
  ]
}

function channelText(channel: GreetingBatch['recipients'][number]['channel']) {
  if (channel === 'app') return t('per App')
  if (channel === 'mail') return t('per E-Mail')
  if (channel === 'letter') return t('Brief')
  if (channel === 'portal') return t('nur im Mitgliederbereich')
  return t('kein Glückwunsch')
}

function statusText(b: GreetingBatch, approval: boolean) {
  if (b.status === 'sent')
    return b.sent_at ? t('versendet am {x}', { x: formatDateTime(b.sent_at) }) : t('versendet')
  if (b.status === 'skipped')
    return b.note ? t('ausgelassen ({note})', { note: b.note }) : t('ausgelassen')
  if (b.status === 'late') return t('nicht versendet')
  return approval ? t('wartet auf Freigabe') : t('geht am Tag von selbst hinaus')
}

function occasionText(o: GreetingOccasion) {
  return o.kind === 'birthday'
    ? t('{n}. Geburtstag', { n: o.age ?? '' })
    : t('{n} Jahre im Verein', { n: o.years ?? '' })
}

/** Heutiges Datum im Ortszeit-Format JJJJ-MM-TT (Vergleich mit den Tagen der Glückwünsche) */
function localToday() {
  const d = new Date()
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`
}

export function GreetingsArea({ orgId }: { orgId: number }) {
  const data = useLoad(() => greetingApi.overview(orgId), [orgId])
  // Ungespeicherte Änderungen; ohne Änderung gilt die geladene Einstellung
  const [edits, setForm] = useState<GreetingSettings | null>(null)
  const [today] = useState(localToday)
  const [errors, setErrors] = useState<Record<string, string>>({})
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  if (data.error) return <LoadError message={data.error} onRetry={() => void data.reload()} />
  if (!data.data) return <Loading />
  const form = edits ?? data.data.settings
  const canEdit = data.data.can_edit
  const open = data.data.batches.filter((b) => b.status === 'draft' || b.status === 'late')
  const done = data.data.batches.filter((b) => b.status === 'sent' || b.status === 'skipped')

  function set<K extends keyof GreetingSettings>(key: K, value: GreetingSettings[K]) {
    setForm({ ...form, [key]: value })
  }

  async function save() {
    if (busy) return
    setBusy(true)
    setError(null)
    setErrors({})
    setNotice(null)
    try {
      await greetingApi.save(orgId, {
        birthdays: form.birthdays,
        round_ages: form.round_ages,
        every_year_from: Number(form.every_year_from) || 0,
        jubilees: form.jubilees,
        approval: form.approval,
        lead_days: Number(form.lead_days) || 0,
        send_hour: Number(form.send_hour) || 9,
        via_app: form.via_app,
        also_mail: form.also_mail,
        reply_to: form.reply_to,
        birthday_subject: form.birthday_subject,
        birthday_body: form.birthday_body,
        jubilee_subject: form.jubilee_subject,
        jubilee_body: form.jubilee_body,
      })
      setNotice(t('Gespeichert. Die Entwürfe der nächsten Tage sind angepasst.'))
      await data.reload()
      setForm(null)
    } catch (err) {
      if (err instanceof ApiError) setErrors(err.fieldErrors)
      setError(errorMessage(err))
    } finally {
      setBusy(false)
    }
  }

  async function act(b: GreetingBatch, action: 'send' | 'skip' | 'restore') {
    setError(null)
    setNotice(null)
    if (action === 'send') {
      const ok = await confirmDialog({
        message: t('Glückwunsch zum {kind} am {date} jetzt versenden?', {
          kind: b.kind_label,
          date: formatDate(b.date),
        }),
        confirmLabel: t('Jetzt versenden'),
        danger: false,
      })
      if (!ok) return
    }
    try {
      await greetingApi[action](orgId, b.id)
      setNotice(
        action === 'send'
          ? t('Der Glückwunsch wird versendet.')
          : action === 'skip'
            ? t('Ausgelassen.')
            : t('Wieder vorgesehen.'),
      )
      await data.reload()
    } catch (err) {
      setError(errorMessage(err))
    }
  }

  function resetTexts(keys: Texts[]) {
    const next = { ...form }
    for (const key of keys) next[key] = form.defaults[key]
    setForm(next)
  }

  return (
    <div className="stack">
      <div className="card card-wide">
        <h2>{t('Anstehende Glückwünsche')}</h2>
        <p className="muted small">
          {form.active
            ? form.approval
              ? t('{n} Tage vorher entsteht ein Entwurf. Ihr gebt jeden Glückwunsch selbst frei.', {
                  n: form.lead_days,
                })
              : t(
                  '{n} Tage vorher entsteht ein Entwurf, damit ihr Briefe rechtzeitig drucken könnt. Am Tag geht er ab {h} Uhr per App oder E-Mail von selbst hinaus.',
                  { n: form.lead_days, h: form.send_hour },
                )
            : t('Glückwünsche sind ausgeschaltet. Unten unter „Einstellung“ einschalten.')}
        </p>
        {open.length === 0 && form.active && (
          <p className="muted">{t('In den nächsten Tagen steht nichts an.')}</p>
        )}
        {open.length > 0 && (
          <ul className="plain-list">
            {open.map((b) => (
              <li key={b.id} className="subcard">
                <strong>
                  {formatDate(b.date)} · {b.kind_label}
                </strong>{' '}
                <span className={`badge${b.status === 'late' ? ' badge-open' : ''}`}>
                  {statusText(b, form.approval)}
                </span>
                <ul className="small">
                  {b.recipients.map((r, i) => (
                    <li key={i}>
                      {r.name}: {channelText(r.channel)}
                      {r.note && !r.channel && <span className="muted"> · {r.note}</span>}
                    </li>
                  ))}
                </ul>
                <div className="button-row">
                  {b.letters > 0 && b.letters_url && (
                    <a className="button" href={b.letters_url} target="_blank" rel="noreferrer">
                      {b.letters === 1
                        ? t('1 Brief drucken (PDF)')
                        : t('{n} Briefe drucken (PDF)', { n: b.letters })}
                    </a>
                  )}
                  {canEdit && b.date <= today && (
                    <button
                      type="button"
                      className="button button-primary"
                      onClick={() => void act(b, 'send')}
                    >
                      {t('Jetzt versenden')}
                    </button>
                  )}
                  {canEdit && (
                    <button
                      type="button"
                      className="button button-ghost"
                      onClick={() => void act(b, 'skip')}
                    >
                      {t('Auslassen')}
                    </button>
                  )}
                </div>
              </li>
            ))}
          </ul>
        )}
        <StatusMessage message={notice} />
        {error && <Alert kind="error">{error}</Alert>}
      </div>

      {data.data.upcoming.length > 0 && (
        <div className="card card-wide">
          <h2>{t('Die nächsten 60 Tage')}</h2>
          <UpcomingTable rows={data.data.upcoming} />
        </div>
      )}

      {done.length > 0 && (
        <div className="card card-wide">
          <h2>{t('Verlauf (30 Tage)')}</h2>
          <ul className="plain-list">
            {done.map((b) => (
              <li key={b.id}>
                {formatDate(b.date)} · {b.kind_label} · {statusText(b, form.approval)}
                {b.status === 'sent' && b.circular && (
                  <>
                    {' · '}
                    <Link to={`/rundschreiben/${b.circular}`}>{t('Versandprotokoll')}</Link>
                  </>
                )}
                {canEdit && b.status === 'skipped' && b.date >= today && (
                  <>
                    {' · '}
                    <button
                      type="button"
                      className="link-button"
                      onClick={() => void act(b, 'restore')}
                    >
                      {t('Wieder vorsehen')}
                    </button>
                  </>
                )}
              </li>
            ))}
          </ul>
        </div>
      )}

      <form
        className="card card-wide"
        onSubmit={(e) => {
          e.preventDefault()
          void save()
        }}
      >
        <h2>{t('Einstellung')}</h2>
        <fieldset disabled={!canEdit || busy}>
          <SelectField
            label={t('Geburtstage')}
            value={form.birthdays}
            error={errors.birthdays}
            onChange={(e) => set('birthdays', e.target.value as GreetingSettings['birthdays'])}
          >
            <option value="off">{t('keine Glückwünsche')}</option>
            <option value="round">{t('nur zu besonderen Geburtstagen')}</option>
            <option value="all">{t('zu jedem Geburtstag')}</option>
          </SelectField>
          {form.birthdays === 'round' && (
            <>
              <Field
                label={t('Besondere Geburtstage')}
                hint={t('Lebensjahre, durch Komma getrennt')}
                value={form.round_ages}
                error={errors.round_ages}
                onChange={(e) => set('round_ages', e.target.value)}
              />
              <Field
                label={t('Ab diesem Alter jedes Jahr')}
                hint={t('0 = nie')}
                type="number"
                min={0}
                max={120}
                value={form.every_year_from}
                error={errors.every_year_from}
                onChange={(e) => set('every_year_from', Number(e.target.value))}
              />
            </>
          )}
          <Checkbox
            label={t('Zu Mitgliedsjubiläen im Verein gratulieren')}
            hint={t('nach den Jubiläumsstufen des Vereins; jahresgenaue Jubiläen ohne Tag nicht')}
            checked={form.jubilees}
            onChange={(v) => set('jubilees', v)}
          />
          <SelectField
            label={t('Versand')}
            value={form.approval ? 'approval' : 'auto'}
            onChange={(e) => set('approval', e.target.value === 'approval')}
          >
            <option value="auto">{t('am Tag von selbst')}</option>
            <option value="approval">{t('erst nach Freigabe durch den Vorstand')}</option>
          </SelectField>
          <Field
            label={t('Entwurf so viele Tage vorher')}
            hint={t('damit Briefe rechtzeitig gedruckt werden können')}
            type="number"
            min={0}
            max={30}
            value={form.lead_days}
            error={errors.lead_days}
            onChange={(e) => set('lead_days', Number(e.target.value))}
          />
          <Field
            label={t('Versand ab (Uhr)')}
            type="number"
            min={6}
            max={20}
            value={form.send_hour}
            error={errors.send_hour}
            onChange={(e) => set('send_hour', Number(e.target.value))}
          />
          <Checkbox
            label={t('Per App, wo möglich')}
            checked={form.via_app}
            onChange={(v) => set('via_app', v)}
          />
          {form.via_app && (
            <Checkbox
              label={t('App-Nutzer bekommen zusätzlich die E-Mail')}
              checked={form.also_mail}
              onChange={(v) => set('also_mail', v)}
            />
          )}
          <Field
            label={t('Antworten an (E-Mail)')}
            hint={t('leer: ohne Antwortadresse')}
            type="email"
            value={form.reply_to}
            error={errors.reply_to}
            onChange={(e) => set('reply_to', e.target.value)}
          />
          {form.birthdays !== 'off' && (
            <fieldset className="subcard greeting-text">
              <legend>{t('Text zum Geburtstag')}</legend>
              <Field
                label={t('Betreff')}
                value={form.birthday_subject}
                error={errors.birthday_subject}
                onChange={(e) => set('birthday_subject', e.target.value)}
              />
              <MarkupEditor
                value={form.birthday_body}
                onChange={(v) => set('birthday_body', v)}
                placeholders={placeholders()}
                error={errors.birthday_body}
              />
              <button
                type="button"
                className="link-button small"
                onClick={() => resetTexts(['birthday_subject', 'birthday_body'])}
              >
                {t('Vorgabetext übernehmen')}
              </button>
            </fieldset>
          )}
          {form.jubilees && (
            <fieldset className="subcard greeting-text">
              <legend>{t('Text zum Jubiläum')}</legend>
              <Field
                label={t('Betreff')}
                value={form.jubilee_subject}
                error={errors.jubilee_subject}
                onChange={(e) => set('jubilee_subject', e.target.value)}
              />
              <MarkupEditor
                value={form.jubilee_body}
                onChange={(v) => set('jubilee_body', v)}
                placeholders={placeholders()}
                error={errors.jubilee_body}
              />
              <button
                type="button"
                className="link-button small"
                onClick={() => resetTexts(['jubilee_subject', 'jubilee_body'])}
              >
                {t('Vorgabetext übernehmen')}
              </button>
            </fieldset>
          )}
          <p className="muted small">
            {t(
              'Mitglieder können Glückwünschen im Mitgliederbereich widersprechen; der Vorstand vermerkt einen Widerspruch in der Mitgliedsakte.',
            )}
          </p>
          {canEdit && (
            <div className="button-row">
              <button type="submit" className="button button-primary" disabled={busy}>
                {t('Speichern')}
              </button>
            </div>
          )}
        </fieldset>
      </form>
    </div>
  )
}

/** Anlässe der nächsten Tage: ab 20 Zeilen mit Suche, sortierbar nach jeder Spalte. */
function UpcomingTable({ rows }: { rows: GreetingOccasion[] }) {
  const search = useRowSearch(rows, (o) => `${o.name} ${occasionText(o)}`, t('Anlässe'))
  const sorting = useRowSort(search.shown, {
    date: (o) => o.date,
    name: (o) => o.name,
    occasion: (o) => occasionText(o),
  })
  return (
    <>
      {search.field}
      <div className="table-scroll">
        <table className="table">
          <thead>
            <tr>
              {sorting.head('date', t('Datum'))}
              {sorting.head('name', t('Name'))}
              {sorting.head('occasion', t('Anlass'))}
            </tr>
          </thead>
          <tbody>
            {sorting.rows.map((o) => (
              <tr key={`${o.kind}-${o.member_id}-${o.date}`}>
                <td>{formatDate(o.date)}</td>
                <td>
                  {o.name}
                  {o.opted_out && (
                    <div className="muted small">{t('möchte keine Glückwünsche')}</div>
                  )}
                </td>
                <td>{occasionText(o)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  )
}
