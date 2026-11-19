// Plattform › Hilfe: Rückmeldungen „Hat das geholfen?“ je Hilfetext (meiste „Nein“ zuerst)
// und Suchwörter ohne Treffer. Alles ohne Person und Einheit (docs/hilfe.md).
import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { helpApi } from '../../api/help.ts'
import type { HelpFeedbackState } from '../../api/help.ts'
import { errorMessage, formatDate, useLoad } from '../../components/forms.ts'
import { useRowSearch } from '../../components/RowSearch.tsx'
import { useRowSort } from '../../components/RowSort.tsx'
import { Alert, Loading } from '../../components/ui.tsx'
import { loadHelp } from '../../help/content.ts'
import type { HelpEntry } from '../../help/content.ts'
import { lang, t } from '../../i18n/index.ts'

export function PlatformHelpPage() {
  const { data, error, setData } = useLoad(() => helpApi.platformFeedback(), [])
  const [entries, setEntries] = useState<Map<string, HelpEntry>>(new Map())
  const [failed, setFailed] = useState<string | null>(null)
  useEffect(() => {
    let active = true
    loadHelp(lang())
      .then((all) => active && setEntries(new Map(all.map((e) => [e.key, e]))))
      .catch(() => {})
    return () => {
      active = false
    }
  }, [])

  const answers = useRowSearch(
    data?.entries ?? [],
    (row) =>
      `${entries.get(row.key)?.title ?? ''} ${row.key} ${row.comments.map((c) => c.text).join(' ')}`,
    t('Rückmeldungen'),
  )
  const answerSort = useRowSort(answers.shown, {
    title: (row) => entries.get(row.key)?.title ?? row.key,
    no: (row) => row.no,
    yes: (row) => row.yes,
  })
  const misses = useRowSearch(data?.misses ?? [], (m) => m.term, t('Suchwörter'))
  const missSort = useRowSort(misses.shown, {
    term: (m) => m.term,
    language: (m) => m.language,
    count: (m) => m.count,
    last: (m) => m.last_day,
  })

  async function change(action: () => Promise<HelpFeedbackState>) {
    setFailed(null)
    try {
      setData(await action())
    } catch (err) {
      setFailed(errorMessage(err))
    }
  }

  if (error && !data) return <Alert kind="error">{error}</Alert>
  if (!data) return <Loading />
  return (
    <>
      {failed && <Alert kind="error">{failed}</Alert>}
      <div className="card card-wide">
        <h2>{t('Hat das geholfen?')}</h2>
        <p className="muted">
          {t(
            'Antworten unter den Anleitungen und Seitenhilfen, die meisten „Nein“ zuerst. Gespeichert sind nur Hilfetext, Sprache, Fassung, Antwort, Satz und Tag, keine Person und kein Verein.',
          )}
        </p>
        {data.entries.length === 0 ? (
          <p>{t('Noch keine Rückmeldungen.')}</p>
        ) : (
          <>
            {answers.field}
            <table className="table help-feedback-list">
              <thead>
                <tr>
                  {answerSort.head('title', t('Hilfetext'))}
                  {answerSort.head('no', t('Nein'), { className: 'num' })}
                  {answerSort.head('yes', t('Ja'), { className: 'num' })}
                  <th scope="col">{t('Was hat gefehlt?')}</th>
                </tr>
              </thead>
              <tbody>
                {answerSort.rows.map((row) => {
                  const entry = entries.get(row.key)
                  return (
                    <tr key={row.key}>
                      <th scope="row">
                        {entry ? <Link to={`/hilfe/${entry.slug}`}>{entry.title}</Link> : row.key}
                      </th>
                      <td className="num">{row.no}</td>
                      <td className="num">{row.yes}</td>
                      <td>
                        {row.comments.length > 0 && (
                          <ul className="help-feedback-comments">
                            {row.comments.map((c) => (
                              <li key={c.id}>
                                {c.text}{' '}
                                <span className="muted small">
                                  ({formatDate(c.day)}, {c.language}
                                  {c.version ? `, ${c.version}` : ''})
                                </span>{' '}
                                <button
                                  type="button"
                                  className="link-button"
                                  aria-label={t('Satz „{x}“ entfernen', { x: c.text })}
                                  onClick={() => void change(() => helpApi.dropComment(c.id))}
                                >
                                  {t('Entfernen')}
                                </button>
                              </li>
                            ))}
                          </ul>
                        )}
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </>
        )}
      </div>
      <div className="card card-wide">
        <h2>{t('Suchen ohne Treffer')}</h2>
        <p className="muted">
          {t(
            'Wonach in der Hilfe gesucht und nichts gefunden wurde. Gespeichert sind nur die Suchwörter mit Zähler; Eingaben mit Ziffern oder E-Mail-Adressen werden nicht gespeichert.',
          )}
        </p>
        {data.misses.length === 0 ? (
          <p>{t('Bisher hat jede Suche etwas gefunden.')}</p>
        ) : (
          <>
            {misses.field}
            <table className="table">
              <thead>
                <tr>
                  {missSort.head('term', t('Suchwörter'))}
                  {missSort.head('language', t('Sprache'))}
                  {missSort.head('count', t('Wie oft'), { className: 'num' })}
                  {missSort.head('last', t('Zuletzt'))}
                  <th scope="col">
                    <span className="sr-only">{t('Aktionen')}</span>
                  </th>
                </tr>
              </thead>
              <tbody>
                {missSort.rows.map((m) => (
                  <tr key={m.id}>
                    <th scope="row">{m.term}</th>
                    <td>{m.language}</td>
                    <td className="num">{m.count}</td>
                    <td>{formatDate(m.last_day)}</td>
                    <td>
                      <button
                        type="button"
                        className="link-button"
                        aria-label={t('Suchwörter „{x}“ entfernen', { x: m.term })}
                        onClick={() => void change(() => helpApi.dropMiss(m.id))}
                      >
                        {t('Entfernen')}
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </>
        )}
      </div>
    </>
  )
}
