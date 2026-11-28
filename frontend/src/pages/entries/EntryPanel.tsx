// Meldungen: die Meldung einer Einheit zu einer Ausschreibung (Blöcke, Abgabe, Rücknahme).
import { useCallback, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  STATUS_LABELS,
  entriesApi,
  type CallDetail,
  type Entry,
  type EntryOptions,
  type Scope,
} from '../../api/entries.ts'
import { confirmDialog } from '../../components/dialog.ts'
import { errorMessage } from '../../components/forms.ts'
import { Alert } from '../../components/ui.tsx'
import { InterestCard } from './CallEvent.tsx'
import { EntryResultsCard } from './EntryResults.tsx'
import { t } from '../../i18n/index.ts'
import { NoteCard, OrganizerCard, SubmitCard } from './EntrySubmit.tsx'
import { BlockEntry } from './EntryBlocks.tsx'

export function EntryPanel({
  org,
  call,
  entry,
  options,
  setEntry,
  organizer = false,
}: {
  org: Scope
  call: CallDetail
  entry: Entry | null
  options: EntryOptions
  setEntry: (e: Entry | null) => void
  /** Veranstalter bearbeitet die Meldung einer Untereinheit (bestätigen, zurückgeben) */
  organizer?: boolean
}) {
  const [message, setMessage] = useState<string | null>(null)
  const run = useCallback(
    async (action: () => Promise<Entry | unknown>) => {
      setMessage(null)
      try {
        const result = await action()
        if (result && typeof result === 'object' && 'status' in result) setEntry(result as Entry)
        return true
      } catch (err) {
        setMessage(errorMessage(err))
        return false
      }
    },
    [setEntry],
  )

  if (!entry) {
    return (
      <div className="card card-wide">
        <p>{t('Zu dieser Ausschreibung gibt es noch keine Meldung.')}</p>
        {call.blocks.length === 0 && (
          <Alert kind="info">
            {t(
              'Die Ausschreibung hat noch keine Bausteine. Legt unter „Ausschreibung“ fest, was gemeldet wird, z. B. Mannschaften.',
            )}
          </Alert>
        )}
        {message && <Alert kind="error">{message}</Alert>}
        <div className="button-row">
          <button
            type="button"
            className="button"
            onClick={() => void run(() => entriesApi.createEntry(org, call.id))}
          >
            {t('Meldung zusammenstellen')}
          </button>
        </div>
      </div>
    )
  }

  const withdrawn = entry.status === 'zurueckgezogen'
  const locked = withdrawn
  return (
    <>
      <div className="card card-wide">
        <div className="card-head">
          <h2>
            {t('Meldung: ')}
            {STATUS_LABELS[entry.status]}
            {entry.changed && entry.status !== 'entwurf'
              ? t(' (geändert, noch nicht gemeldet)')
              : ''}
          </h2>
        </div>
        {entry.confirmed_note && (
          <p className="muted">
            {t('Bestätigung: ')}
            {entry.confirmed_note}
          </p>
        )}
        {entry.question && (
          <Alert kind="info">
            {t('Rückfrage ')}
            {call.internal ? t('von {x1}', { x1: call.organizer }) : ''}: {entry.question}
            {!organizer && t(' Bitte prüfen und die Meldung erneut abgeben.')}
          </Alert>
        )}
        {entry.after_deadline && !withdrawn && (
          <Alert kind="info">
            {t('Der Meldeschluss ist vorbei.')}{' '}
            {call.changes_after_deadline === 'frei'
              ? t('Änderungen sind bis zum Anlass möglich.')
              : call.changes_after_deadline === 'ersatz'
                ? t('Möglich ist nur noch der Ersatz von Personen.')
                : t('Änderungen sind nicht mehr vorgesehen.')}
          </Alert>
        )}
        {entry.hints.length > 0 && (
          <div className="alert alert-info" role="status">
            <strong>{t('Bitte prüfen')}</strong>
            {call.strict ? t(' (so lässt sich nicht abgeben):') : t(' (Abgeben bleibt möglich):')}
            <ul>
              {entry.hints.map((h, i) => (
                <li key={i}>{h.text}</li>
              ))}
            </ul>
          </div>
        )}
        {entry.competition && !call.internal && (
          <p>
            {t('Zur Meldung gehört der Wettbewerb')}{' '}
            <Link to={`/wettbewerbe/${entry.competition}`}>{call.title}</Link>
            {t('; dort tragt ihr später eure Plätze ein.')}
          </p>
        )}
        {message && <Alert kind="error">{message}</Alert>}
      </div>
      {/* Ausschreibung an Untereinheiten: Ergebnisse kommen nach Abschluss hierher zurück */}
      {entry.competition && call.internal && <EntryResultsCard org={org} call={call.id} />}
      <InterestCard org={org} call={call} entry={entry} locked={locked} run={run} />
      {call.blocks.map((b) => (
        <BlockEntry
          key={b.id}
          org={org}
          call={call}
          block={b}
          entry={entry}
          locked={locked}
          run={run}
        />
      ))}
      {!locked && <NoteCard org={org} call={call} entry={entry} setEntry={setEntry} />}
      {!locked && (
        <SubmitCard
          org={org}
          call={call}
          entry={entry}
          options={options}
          run={run}
          onDiscarded={() => setEntry(null)}
        />
      )}
      {withdrawn && (
        <WithdrawnCard
          org={org}
          call={call}
          entry={entry}
          run={run}
          onDeleted={() => setEntry(null)}
        />
      )}
      {organizer && <OrganizerCard org={org} call={call} entry={entry} run={run} />}
    </>
  )
}

/** Zurückgezogene Meldung: wieder öffnen oder ganz löschen (die Ausschreibung bleibt). */
function WithdrawnCard({
  org,
  call,
  entry,
  run,
  onDeleted,
}: {
  org: Scope
  call: CallDetail
  entry: Entry
  run: Run
  onDeleted: () => void
}) {
  async function remove() {
    const ok = await confirmDialog({
      final: true,
      title: t('Meldung löschen'),
      message: t(
        'Die Meldung mit allen Mannschaften, Personen und {x1} Fassungen löschen? Die Ausschreibung bleibt erhalten.',
        { x1: entry.versions.length },
      ),
      confirmLabel: t('Löschen'),
      danger: true,
    })
    if (ok && (await run(() => entriesApi.discard(org, call.id)))) onDeleted()
  }
  return (
    <div className="card card-wide">
      <div className="card-head">
        <h2>{t('Zurückgezogen')}</h2>
      </div>
      <p className="muted">
        {t(
          'Öffnet ihr die Meldung wieder, wird sie zum Entwurf mit den bisherigen Angaben; die Fassungen bleiben erhalten. Beim Löschen verschwindet die Meldung mit allen Fassungen, und ihr könnt neu anfangen.',
        )}
      </p>
      <div className="button-row">
        <button
          type="button"
          className="button"
          onClick={() => void run(() => entriesApi.reopen(org, call.id))}
        >
          {t('Wieder öffnen')}
        </button>
        <button type="button" className="button button-ghost" onClick={remove}>
          {t('Meldung löschen')}
        </button>
      </div>
    </div>
  )
}

export type Run = (action: () => Promise<Entry | unknown>) => Promise<boolean>
