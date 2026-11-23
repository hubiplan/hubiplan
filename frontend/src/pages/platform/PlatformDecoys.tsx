// Plattform › Sicherheit: Köderdaten. Erfundene Mitglieder im Datenbereich der Plattform,
// die kein Verein zu sehen bekommt; wer sie benutzt, löst eine Sicherheitsmail aus.
import { useState } from 'react'
import { decoyApi } from '../../api/security.ts'
import type { DecoyHit, DecoyState } from '../../api/security.ts'
import { confirmDialog } from '../../components/dialog.ts'
import { errorMessage, formatDate, formatDateTime, useLoad } from '../../components/forms.ts'
import { useRowSearch } from '../../components/RowSearch.tsx'
import { useRowSort } from '../../components/RowSort.tsx'
import { Alert, Field, Loading } from '../../components/ui.tsx'
import { t } from '../../i18n/index.ts'

function kindLabel(kind: DecoyHit['kind']): string {
  if (kind === 'mail_in') return t('Mail an die Köderadresse')
  if (kind === 'mail_out') return t('HUBIplan wollte dem Köder schreiben')
  if (kind === 'login') return t('Anmeldeversuch mit der Köderadresse')
  return t('Abruf der Mitgliedsnummer')
}

export function PlatformDecoys() {
  const { data, error, setData } = useLoad(() => decoyApi.state(), [])
  const [email, setEmail] = useState('')
  const [failed, setFailed] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const search = useRowSearch(
    data?.hits ?? [],
    (h) => `${kindLabel(h.kind)} ${h.decoy} ${h.detail}`,
    t('Auslösungen'),
  )
  const sort = useRowSort(search.shown, {
    kind: (h) => kindLabel(h.kind),
    decoy: (h) => h.decoy,
    detail: (h) => h.detail,
    count: (h) => h.count,
    last: (h) => h.last_at,
  })

  async function change(action: () => Promise<DecoyState>): Promise<boolean> {
    setFailed(null)
    setBusy(true)
    try {
      setData(await action())
      return true
    } catch (err) {
      setFailed(errorMessage(err))
      return false
    } finally {
      setBusy(false)
    }
  }

  async function create() {
    if (await change(() => decoyApi.create(email.trim()))) setEmail('')
  }

  async function remove(id: number, name: string) {
    const ok = await confirmDialog({
      title: t('Köder „{x}“ löschen?', { x: name }),
      message: t(
        'Danach löst diese Adresse keinen Alarm mehr aus. In älteren Sicherungen steht der Köder weiter.',
      ),
      confirmLabel: t('Köder löschen'),
      danger: true,
      final: false,
    })
    if (ok) await change(() => decoyApi.remove(id))
  }

  if (error && !data) return <Alert kind="error">{error}</Alert>
  if (!data) return <Loading />
  const full = data.decoys.length >= data.limit
  return (
    <div className="card card-wide">
      <h2>{t('Köderdaten')}</h2>
      <p className="muted">
        {t(
          'Ein Köder ist ein erfundenes Mitglied, das zu keinem Verein gehört. Keine Mitgliederliste, keine Auswertung, kein Export und keine App zeigt ihn. In der Datenbank und in jeder Sicherung steht er wie ein echtes Mitglied. Wer Daten an HUBIplan vorbei abgreift, nimmt ihn mit.',
        )}
      </p>
      <p className="muted">
        {t(
          'Eine Sicherheitsmail geht hinaus, wenn eine Mail an die Köderadresse ankommt, wenn sich jemand mit ihr anmelden will oder wenn jemand die Nummer des Köders über die Schnittstelle abruft. Je Art höchstens eine Mail in der Stunde.',
        )}
      </p>
      {failed && <Alert kind="error">{failed}</Alert>}
      {data.decoys.length === 0 ? (
        <p>{t('Noch kein Köder angelegt.')}</p>
      ) : (
        <ul>
          {data.decoys.map((d) => (
            <li key={d.id}>
              <strong>{d.name}</strong>, {d.email}, {d.place}{' '}
              <span className="muted small">
                ({t('angelegt am {date}', { date: formatDate(d.created) })})
              </span>{' '}
              <button
                type="button"
                className="link-button"
                aria-label={t('Köder „{x}“ löschen', { x: d.name })}
                disabled={busy}
                onClick={() => void remove(d.id, d.name)}
              >
                {t('Löschen')}
              </button>
            </li>
          ))}
        </ul>
      )}
      {!full && (
        <form
          onSubmit={(e) => {
            e.preventDefault()
            void create()
          }}
        >
          <Field
            label={t('E-Mail-Adresse des Köders')}
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            hint={
              data.domain
                ? t(
                    'Leer lassen: HUBIplan nimmt eine Adresse an {domain} und erkennt Mails dorthin selbst. Eine eigene Adresse musst du selbst lesen.',
                    { domain: data.domain },
                  )
                : t(
                    'Es ist keine Verteiler-Domain eingerichtet. Gib eine Adresse an, an die sonst niemand schreibt und deren Postfach du liest.',
                  )
            }
          />
          <p>
            <button type="submit" className="button" disabled={busy}>
              {t('Köder anlegen')}
            </button>
          </p>
        </form>
      )}
      <h3>{t('Auslösungen')}</h3>
      {data.hits.length === 0 ? (
        <p>{t('Bisher hat niemand einen Köder benutzt.')}</p>
      ) : (
        <>
          <Alert kind="error">
            {t(
              'Jemand hat Köderdaten benutzt. Das spricht dafür, dass Daten an HUBIplan vorbei abgeflossen sind. Prüfe Zugänge, Protokoll und Sicherungen (Notfallplan in der Betriebsanleitung).',
            )}
          </Alert>
          {search.field}
          <table className="table">
            <thead>
              <tr>
                {sort.head('kind', t('Was'))}
                {sort.head('decoy', t('Köder'))}
                {sort.head('detail', t('Angabe'))}
                {sort.head('count', t('Wie oft'), { className: 'num' })}
                {sort.head('last', t('Zuletzt'))}
              </tr>
            </thead>
            <tbody>
              {sort.rows.map((h) => (
                <tr key={h.id}>
                  <th scope="row">{kindLabel(h.kind)}</th>
                  <td>{h.decoy || t('gelöscht')}</td>
                  <td>{h.detail}</td>
                  <td className="num">{h.count}</td>
                  <td>{formatDateTime(h.last_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <p>
            <button
              type="button"
              className="button"
              disabled={busy}
              onClick={() => void change(() => decoyApi.clearHits())}
            >
              {t('Auslösungen leeren')}
            </button>
          </p>
        </>
      )}
    </div>
  )
}
