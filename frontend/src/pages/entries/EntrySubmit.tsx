// Meldungen: Hinweis, Abgabe, Veranstalterseite und Fassungen einer Meldung.
import { useState } from 'react'
import { Link } from 'react-router-dom'
import {
  CHANNEL_LABELS,
  entriesApi,
  type CallDetail,
  type Channel,
  type Entry,
  type EntryOptions,
  type Scope,
} from '../../api/entries.ts'
import { confirmDialog, promptDialog } from '../../components/dialog.ts'
import { Field, SelectField } from '../../components/ui.tsx'
import { locale, t } from '../../i18n/index.ts'
import { type Run } from './EntryPanel.tsx'

export function NoteCard({
  org,
  call,
  entry,
  setEntry,
}: {
  org: Scope
  call: CallDetail
  entry: Entry
  setEntry: (e: Entry) => void
}) {
  const [note, setNote] = useState(entry.note)
  return (
    <div className="card card-wide">
      <label className="field">
        <span>{t('Interne Notiz (geht nicht an den Veranstalter)')}</span>
        <textarea
          rows={2}
          value={note}
          onChange={(e) => setNote(e.target.value)}
          onBlur={async () => {
            if (note !== entry.note) setEntry(await entriesApi.updateEntry(org, call.id, { note }))
          }}
        />
      </label>
    </div>
  )
}

export function SubmitCard({
  org,
  call,
  entry,
  options,
  run,
  onDiscarded,
}: {
  org: Scope
  call: CallDetail
  entry: Entry
  options: EntryOptions
  run: Run
  onDiscarded: () => void
}) {
  const [channel, setChannel] = useState<Channel>(call.organizer_email ? 'email' : 'brief')
  const [email, setEmail] = useState(call.organizer_email)
  const [sentTo, setSentTo] = useState('')
  const [fn, setFn] = useState(options.functions[0] ?? '')
  const [busy, setBusy] = useState(false)
  // Nach Rückzug und „Wieder öffnen“ ist die nächste Abgabe wieder eine neue Meldung
  const first = entry.versions.length === 0 || entry.versions.at(-1)?.kind === 'rueckzug'
  const nothingNew = !first && !entry.changed
  const preview = (fmt: 'pdf' | 'xlsx' | 'csv') => entriesApi.previewUrl(org, call.id, fmt)

  async function submit() {
    setBusy(true)
    await run(() =>
      entriesApi.submit(org, call.id, {
        channel,
        email: channel === 'email' ? email : undefined,
        sent_to: channel === 'sonstiges' ? sentTo : undefined,
        function: fn,
      }),
    )
    setBusy(false)
  }

  async function withdraw() {
    const reason = await promptDialog({
      title: t('Meldung zurückziehen'),
      message: t(
        'Die Rückzugserklärung wird als neue Fassung festgehalten und über den gewählten Meldeweg verschickt bzw. als Brief erstellt.',
      ),
      label: t('Grund (optional)'),
      confirmLabel: t('Zurückziehen'),
      danger: true,
    })
    if (reason === null) return
    await run(() =>
      entriesApi.submit(org, call.id, {
        channel,
        email: channel === 'email' ? email : undefined,
        sent_to: channel === 'sonstiges' ? sentTo : undefined,
        function: fn,
        withdraw: true,
        reason,
      }),
    )
  }

  async function confirmed() {
    const note = await promptDialog({
      title: t('Bestätigung vermerken'),
      label: t('Wie und wann bestätigt?'),
      defaultValue: t('per Mail am {x1}', { x1: new Date().toLocaleDateString(locale()) }),
    })
    if (note !== null) await run(() => entriesApi.confirm(org, call.id, note))
  }

  async function discard() {
    const ok = await confirmDialog({
      final: true,
      title: t('Entwurf verwerfen'),
      message:
        entry.versions.length > 0
          ? `Alle Mannschaften, Personen und Angaben dieses Entwurfs samt ${entry.versions.length} früheren Fassungen löschen?`
          : t('Alle Mannschaften, Personen und Angaben dieses Entwurfs löschen?'),
      confirmLabel: t('Verwerfen'),
      danger: true,
    })
    if (ok && (await run(() => entriesApi.discard(org, call.id)))) onDiscarded()
  }

  if (call.internal)
    return (
      <div className="card card-wide">
        <div className="card-head">
          <h2>{first ? t('Meldung abgeben') : t('Änderung melden')}</h2>
        </div>
        <p className="muted">
          {t('Die Meldung geht in HUBIplan an ')}
          {call.organizer}
          {t('; dort wird sie bestätigt.')}
        </p>
        {nothingNew && entry.status !== 'rueckfrage' ? (
          <p className="muted">{t('Seit der letzten Fassung hat sich nichts geändert.')}</p>
        ) : (
          <div className="button-row">
            <button type="button" className="button" disabled={busy} onClick={submit}>
              {entry.status === 'rueckfrage' && nothingNew
                ? t('Erneut abgeben')
                : first
                  ? t('Meldung abgeben')
                  : t('Änderung melden')}
            </button>
          </div>
        )}
        <div className="button-row">
          {!first && (
            <button type="button" className="button button-ghost" onClick={withdraw}>
              {t('Meldung zurückziehen')}
            </button>
          )}
          {first && (
            <button type="button" className="button button-ghost" onClick={discard}>
              {t('Entwurf verwerfen')}
            </button>
          )}
        </div>
      </div>
    )

  return (
    <div className="card card-wide">
      <div className="card-head">
        <h2>{first ? t('Meldung abgeben') : t('Änderung melden')}</h2>
      </div>
      <p>
        {t('Vorschau:')}{' '}
        <a href={preview('pdf')} target="_blank" rel="noreferrer">
          {t('Brief (PDF)')}
        </a>{' '}
        · <a href={preview('xlsx')}>{t('Tabelle (Excel)')}</a> · <a href={preview('csv')}>CSV</a>
      </p>
      {nothingNew ? (
        <p className="muted">{t('Seit der letzten Fassung hat sich nichts geändert.')}</p>
      ) : (
        <>
          <div className="grid-3">
            <SelectField
              label={t('Meldeweg')}
              value={channel}
              onChange={(e) => setChannel(e.target.value as Channel)}
            >
              {(Object.keys(CHANNEL_LABELS) as Channel[]).map((k) => (
                <option key={k} value={k}>
                  {CHANNEL_LABELS[k]}
                </option>
              ))}
            </SelectField>
            {channel === 'email' && (
              <Field
                label={t('E-Mail des Veranstalters')}
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
              />
            )}
            {channel === 'sonstiges' && (
              <Field
                label={t('Vermerk')}
                placeholder={t('z. B. persönlich übergeben')}
                value={sentTo}
                onChange={(e) => setSentTo(e.target.value)}
              />
            )}
            {options.functions.length > 0 && (
              <SelectField
                label={t('Unterschrift als')}
                value={fn}
                onChange={(e) => setFn(e.target.value)}
              >
                {options.functions.map((f) => (
                  <option key={f} value={f}>
                    {f}
                  </option>
                ))}
              </SelectField>
            )}
          </div>
          <p className="muted small">
            {t('Unterzeichnet von ')}
            {options.signer}
            {t('. Im Brief bleibt Platz für die eigenhändige Unterschrift.')}
            {channel === 'brief' &&
              t(' Nach dem Abgeben findet ihr den Brief unter „Fassungen“ zum Drucken.')}
            {channel === 'email' && t(' Ihr bekommt eine Kopie an eure eigene Adresse.')}
          </p>
          <div className="button-row">
            <button type="button" className="button" disabled={busy} onClick={submit}>
              {first ? t('Meldung abgeben') : t('Änderung melden')}
            </button>
          </div>
        </>
      )}
      <div className="button-row">
        {entry.status === 'abgegeben' && (
          <button type="button" className="button button-ghost" onClick={confirmed}>
            {t('Bestätigung des Veranstalters vermerken')}
          </button>
        )}
        {entry.status === 'bestaetigt' && (
          <button
            type="button"
            className="button button-ghost"
            onClick={() => void run(() => entriesApi.unconfirm(org, call.id))}
          >
            {t('Bestätigung zurücknehmen')}
          </button>
        )}
        {!first && (
          <button type="button" className="button button-ghost" onClick={withdraw}>
            {t('Meldung zurückziehen')}
          </button>
        )}
        {first && (
          <button type="button" className="button button-ghost" onClick={discard}>
            {t('Entwurf verwerfen')}
          </button>
        )}
      </div>
    </div>
  )
}

/** Veranstalter: Meldung einer Untereinheit bestätigen oder mit Rückfrage zurückgeben. */
export function OrganizerCard({
  org,
  call,
  entry,
  run,
}: {
  org: Scope
  call: CallDetail
  entry: Entry
  run: Run
}) {
  async function giveBack() {
    const question = await promptDialog({
      title: t('Mit Rückfrage zurückgeben'),
      label: t('Rückfrage'),
      message: t('Die Zugführung bekommt eine Mail und gibt danach erneut ab.'),
      confirmLabel: t('Zurückgeben'),
    })
    if (question) await run(() => entriesApi.returnEntry(org, call.id, question))
  }
  return (
    <div className="card card-wide">
      <h2>{t('Als Veranstalter')}</h2>
      {entry.status === 'entwurf' && (
        <p className="muted">{t('Die Meldung ist noch nicht abgegeben.')}</p>
      )}
      <div className="button-row">
        {entry.status === 'abgegeben' && (
          <button
            type="button"
            className="button"
            onClick={() => void run(() => entriesApi.confirm(org, call.id, ''))}
          >
            {t('Meldung bestätigen')}
          </button>
        )}
        {entry.status === 'bestaetigt' && (
          <button
            type="button"
            className="button button-ghost"
            onClick={() => void run(() => entriesApi.unconfirm(org, call.id))}
          >
            {t('Bestätigung zurücknehmen')}
          </button>
        )}
        {(entry.status === 'abgegeben' || entry.status === 'bestaetigt') && (
          <button type="button" className="button button-ghost" onClick={giveBack}>
            {t('Mit Rückfrage zurückgeben')}
          </button>
        )}
      </div>
      {entry.competition && (
        <p className="muted small">
          {t('Bestätigte Personen stehen als Starter im Wettbewerb')}{' '}
          <Link to={`/wettbewerbe/${entry.competition}`}>{call.title}</Link>.
        </p>
      )}
    </div>
  )
}

// --- Fassungen ---

export function VersionsPanel({
  org,
  call,
  entry,
}: {
  org: Scope
  call: CallDetail
  entry: Entry | null
}) {
  if (!entry || entry.versions.length === 0)
    return <p className="muted">{t('Noch nichts abgegeben.')}</p>
  const url = (n: number, fmt: 'pdf' | 'xlsx' | 'csv') =>
    entriesApi.versionUrl(org, call.id, n, fmt)
  return (
    <div className="card card-wide">
      <table className="table">
        <thead>
          <tr>
            <th scope="col">{t('Fassung')}</th>
            <th scope="col">{t('Abgegeben')}</th>
            <th scope="col">{t('Meldeweg')}</th>
            <th scope="col">{t('Inhalt')}</th>
            <th scope="col">{t('Belege')}</th>
          </tr>
        </thead>
        <tbody>
          {[...entry.versions].reverse().map((v) => (
            <tr key={v.id}>
              <td>
                {v.number} · {v.kind_label}
              </td>
              <td>
                {new Date(v.created_at).toLocaleString(locale(), {
                  dateStyle: 'short',
                  timeStyle: 'short',
                })}
                <div className="muted small">{v.signed_by}</div>
              </td>
              <td>
                {v.channel_label}
                {v.sent_to && <div className="muted small">{v.sent_to}</div>}
              </td>
              <td>
                {v.changes.length > 0 ? (
                  <ul>
                    {v.changes.map((c, i) => (
                      <li key={i}>{c}</li>
                    ))}
                  </ul>
                ) : (
                  t('vollständige Meldung')
                )}
                {v.reason && (
                  <div className="muted small">
                    {t('Grund: ')}
                    {v.reason}
                  </div>
                )}
                {v.shortened && (
                  <div className="muted small">{t('nach Ablauf der Frist auf Namen gekürzt')}</div>
                )}
              </td>
              <td>
                <a href={url(v.number, 'pdf')} target="_blank" rel="noreferrer">
                  {t('Brief')}
                </a>{' '}
                · <a href={url(v.number, 'xlsx')}>Excel</a> · <a href={url(v.number, 'csv')}>CSV</a>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

// --- Ausschreibung bearbeiten ---
