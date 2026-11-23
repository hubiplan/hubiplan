// Plattform › Sicherheit: Köderdaten (PlatformDecoys) und was Browser an blockierten Inhalten
// gemeldet haben (CSP-Verstöße).
// Gespeichert ohne Person, Einheit und Adresse des Aufrufers (docs/betrieb.md).
import { useState } from 'react'
import { securityApi } from '../../api/security.ts'
import type { CspEntry, CspState } from '../../api/security.ts'
import { confirmDialog } from '../../components/dialog.ts'
import { errorMessage, formatDate, useLoad } from '../../components/forms.ts'
import { useRowSearch } from '../../components/RowSearch.tsx'
import { useRowSort } from '../../components/RowSort.tsx'
import { Alert, Loading } from '../../components/ui.tsx'
import { t } from '../../i18n/index.ts'
import { PlatformDecoys } from './PlatformDecoys.tsx'

/** Was blockiert wurde, in Worten: Art des Inhalts oder die fremde Adresse. */
function blockedLabel(entry: CspEntry): string {
  if (entry.blocked === 'inline') return t('eingebetteter Code auf der Seite')
  if (entry.blocked === 'eval') return t('zur Laufzeit erzeugter Code')
  if (entry.blocked === 'data') return t('eingebettete Daten (data:)')
  if (entry.blocked === 'blob') return t('im Browser erzeugte Datei (blob:)')
  return entry.blocked
}

export function PlatformSecurityPage() {
  const { data, error, setData } = useLoad(() => securityApi.cspReports(), [])
  const [failed, setFailed] = useState<string | null>(null)
  const search = useRowSearch(
    data?.entries ?? [],
    (e) => `${e.directive} ${e.blocked} ${blockedLabel(e)} ${e.page}`,
    t('Meldungen'),
  )
  const sort = useRowSort(search.shown, {
    blocked: (e) => blockedLabel(e),
    directive: (e) => e.directive,
    page: (e) => e.page,
    count: (e) => e.count,
    first: (e) => e.first_day,
    last: (e) => e.last_day,
  })

  async function change(action: () => Promise<CspState>) {
    setFailed(null)
    try {
      setData(await action())
    } catch (err) {
      setFailed(errorMessage(err))
    }
  }

  async function clear() {
    const ok = await confirmDialog({
      title: t('Alle Meldungen entfernen?'),
      message: t(
        'Die Liste wird geleert. Meldet ein Browser denselben Verstoß erneut, steht er wieder hier.',
      ),
      confirmLabel: t('Alle entfernen'),
      danger: true,
      final: false,
    })
    if (ok) await change(() => securityApi.clearCspReports())
  }

  if (error && !data) return <Alert kind="error">{error}</Alert>
  if (!data) return <Loading />
  return (
    <>
      <PlatformDecoys />
      {failed && <Alert kind="error">{failed}</Alert>}
      <div className="card card-wide">
        <h2>{t('Meldungen des Browsers')}</h2>
        <p className="muted">
          {t(
            'HUBIplan gibt jedem Browser Regeln mit, was die Oberfläche laden und ausführen darf. Verstößt eine Seite dagegen, blockiert der Browser den Inhalt und meldet es hierher. Gespeichert sind nur Regel, blockierte Herkunft, Seite und Tag, keine Person, kein Verein und keine Adresse des Aufrufers.',
          )}
        </p>
        <p className="muted">
          {t(
            'Die Meldungen sind nicht beglaubigt: Erweiterungen im Browser lösen sie aus, und jeder kann eine schicken. Ein blockiertes Skript von einer fremden Adresse verdient trotzdem einen Blick. Dafür gibt es höchstens eine Sicherheitsmail am Tag.',
          )}
        </p>
        {data.entries.length === 0 ? (
          <p>{t('Bisher hat kein Browser einen Verstoß gemeldet.')}</p>
        ) : (
          <>
            {data.total >= data.limit && (
              <Alert kind="info">
                {t(
                  'Die Liste ist voll ({n} Einträge). Neue Verstöße werden erst wieder aufgenommen, wenn du Einträge entfernst.',
                  { n: data.limit },
                )}
              </Alert>
            )}
            {search.field}
            <table className="table">
              <thead>
                <tr>
                  {sort.head('blocked', t('Blockiert'))}
                  {sort.head('directive', t('Regel'))}
                  {sort.head('page', t('Seite'))}
                  {sort.head('count', t('Wie oft'), { className: 'num' })}
                  {sort.head('first', t('Zuerst'))}
                  {sort.head('last', t('Zuletzt'))}
                  <th scope="col">
                    <span className="sr-only">{t('Aktionen')}</span>
                  </th>
                </tr>
              </thead>
              <tbody>
                {sort.rows.map((e) => (
                  <tr key={e.id}>
                    <th scope="row">
                      {blockedLabel(e)}
                      {e.script && (
                        <>
                          {' '}
                          <span className="muted small">({t('Skript')})</span>
                        </>
                      )}
                    </th>
                    <td>{e.directive}</td>
                    <td>{e.page}</td>
                    <td className="num">{e.count}</td>
                    <td>{formatDate(e.first_day)}</td>
                    <td>{formatDate(e.last_day)}</td>
                    <td>
                      <button
                        type="button"
                        className="link-button"
                        aria-label={t('Meldung „{x}“ entfernen', {
                          x: `${blockedLabel(e)}, ${e.directive}, ${e.page}`,
                        })}
                        onClick={() => void change(() => securityApi.dropCspReport(e.id))}
                      >
                        {t('Entfernen')}
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            <p>
              <button type="button" className="button" onClick={() => void clear()}>
                {t('Alle entfernen')}
              </button>
            </p>
          </>
        )}
      </div>
    </>
  )
}
