import { sendingVersion } from '../../api/client.ts'
import { EditAt, EditSlot, editKey } from '../../components/EditInPlace.tsx'
import { Fragment, useState } from 'react'
import { donationApi } from '../../api/donations.ts'
import type { Donation } from '../../api/donations.ts'
import { euro } from '../../api/finance.ts'
import { confirmDialog, promptDialog } from '../../components/dialog.ts'
import { errorMessage, formatDate, useLoad } from '../../components/forms.ts'
import { Alert, Checkbox, LoadError, SelectField, Loading } from '../../components/ui.tsx'
import { confirmDiscard } from '../../components/leaveGuard.ts'
import { useActiveOrg } from '../../org/OrgContext.tsx'
import { Term, Why } from '../../learning/Aids.tsx'
import { Checklist } from '../../learning/Checklist.tsx'
import { donationChecks } from '../../learning/checks.ts'
import { t } from '../../i18n/index.ts'
import { PageNav } from './PageNav.tsx'
import { thisYear, yearOptions } from './donationsHelpers.ts'
import { DonationForm } from './DonationForm.tsx'

export function DonationsList({ canEdit }: { canEdit: boolean }) {
  const org = useActiveOrg()
  const [year, setYear] = useState(thisYear())
  const [onlyOpen, setOnlyOpen] = useState(false)
  const [page, setPage] = useState(1)
  const [editing, setEditing] = useState<Donation | 'new' | null>(null)
  const [editDirty, setEditDirty] = useState(false)
  const [selected, setSelected] = useState<number[]>([])
  const [message, setMessage] = useState<{ kind: 'success' | 'error'; text: string } | null>(null)
  const [busy, setBusy] = useState(false)
  const settings = useLoad(() => donationApi.settings(org.id), [org.id])
  const years = useLoad(() => donationApi.years(org.id).catch(() => null), [org.id])
  const list = useLoad(
    () =>
      donationApi.list(org.id, { jahr: year, offen: onlyOpen, page: page > 1 ? page : undefined }),
    [org.id, year, onlyOpen, page],
  )
  // Zahlen für die Prüfliste (blockiert nie)
  const checks = useLoad(
    () => donationApi.checks(org.id, year).catch(() => null),
    [org.id, year, list.data],
  )
  // Ohne geladene Einstellungen ist nicht bekannt, ob Ausstellen möglich ist (UX-Audit 31.10. N05)
  const problems = settings.data?.problems ?? []
  const settingsReady = !!settings.data

  /** Anderen Eintrag öffnen, ohne ungespeicherte Eingaben still zu ersetzen (W01) */
  async function edit(next: Donation | 'new') {
    if (editing !== null && !(await confirmDiscard(editDirty))) return
    setEditDirty(false)
    setEditing(next)
  }

  async function run(action: () => Promise<string>) {
    setBusy(true)
    setMessage(null)
    try {
      setMessage({ kind: 'success', text: await action() })
      setSelected([])
      await list.reload()
    } catch (err) {
      setMessage({ kind: 'error', text: errorMessage(err) })
    } finally {
      setBusy(false)
    }
  }

  async function importBookings() {
    await run(async () => {
      const { created } = await donationApi.importBookings(org.id, year)
      return created
        ? t('{created} Einnahmen aus Spenden-Kategorien übernommen.', { created })
        : t('Keine neuen Einnahmen {year} in Kategorien mit Kennzeichen „Spenden“.', { year })
    })
  }

  async function issueSelected() {
    const signer = await promptDialog({
      title: t('Zuwendungsbestätigung ausstellen'),
      message: t(
        'Mehrere Zuwendungen eines Zuwendenden aus einem Jahr ergeben eine Sammelbestätigung. Das PDF wird als Doppel gespeichert.',
      ),
      label: t('Unterschrift durch (Name)'),
      confirmLabel: t('Ausstellen'),
    })
    if (signer === null) return
    await run(async () => {
      const st = await donationApi.issue(org.id, selected, signer)
      return t('Bestätigung {number} für {donor_name} ausgestellt.', {
        number: st.number,
        donor_name: st.donor_name,
      })
    })
  }

  async function yearEnd() {
    // Vorschau kontrolliert laden: Fehler sichtbar, Knopf gesperrt (UX-Audit 31.10. N05)
    setBusy(true)
    setMessage(null)
    let preview
    try {
      preview = await donationApi.yearEnd(org.id, year)
    } catch (err) {
      setMessage({
        kind: 'error',
        text: t('Die Vorschau konnte nicht geladen werden ({x}). Bitte erneut versuchen.', {
          x: errorMessage(err),
        }),
      })
      return
    } finally {
      setBusy(false)
    }
    if (preview.problems.length > 0) {
      setMessage({
        kind: 'error',
        text: t('Noch keine Bestätigungen möglich: {x} Bitte unter „Einstellungen“ ergänzen.', {
          x: preview.problems.join(' '),
        }),
      })
      await settings.reload()
      return
    }
    // Ohne vollständigen Namen und Anschrift wird nicht bestätigt (Audit 31.10., Fachfrage 5)
    const ready = preview.donors.filter((d) => !d.incomplete)
    const missing = preview.donors.filter((d) => d.incomplete)
    const missingText =
      missing.length > 0
        ? t(' Noch offen, weil Angaben fehlen: {x}.', {
            x: missing.map((d) => `${d.donor_name} (${d.incomplete})`).join(', '),
          })
        : ''
    if (ready.length === 0) {
      setMessage(
        missing.length > 0
          ? { kind: 'error', text: t('Keine Bestätigung möglich.{missingText}', { missingText }) }
          : {
              kind: 'success',
              text: t('Für {year} sind alle Geldzuwendungen bestätigt.', { year }),
            },
      )
      return
    }
    const sum = ready.reduce((s, d) => s + Number(d.total), 0)
    const signer = await promptDialog({
      title: t('Bestätigungen für {year} ausstellen?', { year }),
      message: t(
        '{n} Zuwendende, zusammen {x}. Je Zuwendendem eine Bestätigung (bei mehreren Zuwendungen eine Sammelbestätigung). Sachzuwendungen bleiben offen und werden einzeln bestätigt.{missingText}',
        { n: ready.length, x: euro(sum), missingText },
      ),
      label: t('Unterschrift durch (Name)'),
      confirmLabel: t('Alle ausstellen'),
    })
    if (signer === null) return
    await run(async () => {
      const { created } = await donationApi.issueYearEnd(org.id, year, signer)
      return t('{created} Bestätigungen ausgestellt. Sie stehen unter „Bestätigungen“.', {
        created,
      })
    })
  }

  async function remove(d: Donation) {
    const ok = await confirmDialog({
      final: false,
      title: t('Zuwendung löschen?'),
      message: t('{x} von {donor_name} am {x2}', {
        x: euro(d.amount),
        donor_name: d.donor_name,
        x2: formatDate(d.date),
      }),
      confirmLabel: t('Löschen'),
      danger: true,
    })
    if (ok)
      await run(
        async () => (
          await sendingVersion(d.version, () => donationApi.remove(org.id, d.id)),
          t('Gelöscht.')
        ),
      )
  }

  const count = list.data?.count ?? 0

  const rows = list.data?.results ?? []
  const openRows = rows.filter((d) => !d.statement)
  const toggle = (id: number, on: boolean) =>
    setSelected((s) => (on ? [...s, id] : s.filter((x) => x !== id)))

  return (
    <div className="card card-wide">
      {settings.error && (
        <LoadError
          message={t(
            'Die Angaben zur Steuerbegünstigung konnten nicht geladen werden. {error} Ausstellen ist erst danach möglich.',
            { error: settings.error },
          )}
          onRetry={() => void settings.reload()}
        />
      )}
      {problems.length > 0 && (
        <Alert kind="info">
          {t('Noch keine Bestätigungen möglich:')} {problems.join(' ')}{' '}
          {t('Bitte unter „Einstellungen“ ergänzen.')}
        </Alert>
      )}
      <div className="filters">
        <SelectField
          label={t('Jahr')}
          value={year}
          onChange={(e) => {
            setYear(Number(e.target.value))
            setPage(1)
            setSelected([])
          }}
        >
          {yearOptions(years.data, year).map((y) => (
            <option key={y} value={y}>
              {y}
            </option>
          ))}
        </SelectField>
        <Checkbox
          label={t('nur noch nicht bestätigte')}
          checked={onlyOpen}
          onChange={(on) => {
            setOnlyOpen(on)
            setPage(1)
          }}
        />
      </div>
      {canEdit && editing === null && (
        <div className="button-row">
          <button type="button" className="button button-primary" onClick={() => void edit('new')}>
            {t('Zuwendung erfassen')}
          </button>
          <button
            type="button"
            className="button button-ghost"
            disabled={busy}
            onClick={importBookings}
          >
            {t('Aus dem Kassenbuch übernehmen')}
          </button>
          <button
            type="button"
            className="button button-ghost"
            disabled={busy || !settingsReady || problems.length > 0}
            onClick={yearEnd}
          >
            {t('Jahresende: alle bestätigen')}
          </button>
          {selected.length > 0 && (
            <button
              type="button"
              className="button button-primary"
              disabled={busy || !settingsReady || problems.length > 0}
              onClick={issueSelected}
            >
              {selected.length === 1
                ? t('Bestätigung ausstellen')
                : t('Sammelbestätigung ausstellen')}
            </button>
          )}
        </div>
      )}
      <p className="muted small">
        {t(
          'Übernehmen holt Einnahmen aus Kategorien mit dem Kennzeichen „Spenden“ (Finanzen › Einrichtung › Kategorien). Name und Anschrift kommen aus dem Mitglied oder dem Zahler. Bis 300 € genügt dem Spender oft der',
        )}{' '}
        <Term k="simplified_proof">{t('vereinfachte Zuwendungsnachweis')}</Term>.
      </p>
      <div className="aid-row">
        <Why k="donation_year_end" />
        <Why k="donation_liability" />
      </div>
      {canEdit && checks.data && (
        <Checklist
          title={t('Vor den Jahresbestätigungen {year}', { year })}
          items={donationChecks({ problems, ...checks.data })}
        />
      )}
      {editing !== null && (
        <EditAt at={editing === 'new' ? null : editKey('donation', editing.id)}>
          <DonationForm
            key={editing === 'new' ? 'new' : editing.id}
            initial={editing === 'new' ? null : editing}
            settings={settings.data}
            onDirty={setEditDirty}
            onCancel={() => {
              setEditDirty(false)
              setEditing(null)
            }}
            onDone={async (text) => {
              setEditDirty(false)
              setEditing(null)
              setMessage({ kind: 'success', text })
              await list.reload()
            }}
          />
        </EditAt>
      )}
      {message && <Alert kind={message.kind}>{message.text}</Alert>}
      {list.error && <LoadError message={list.error} onRetry={() => void list.reload()} />}
      {!list.data ? (
        !list.error && <Loading />
      ) : rows.length === 0 ? (
        <p className="muted">{t('Keine Zuwendungen {year}.', { year })}</p>
      ) : (
        <table className="table">
          <thead>
            <tr>
              {canEdit && (
                <th>
                  <span className="sr-only">{t('Auswahl')}</span>
                </th>
              )}
              <th>{t('Datum')}</th>
              <th>{t('Zuwendender')}</th>
              <th>{t('Art')}</th>
              <th className="num">{t('Betrag')}</th>
              <th>{t('Bestätigung')}</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {rows.map((d) => (
              <Fragment key={d.id}>
                <tr key={d.id}>
                  {canEdit && (
                    <td>
                      {!d.statement && (
                        <input
                          type="checkbox"
                          aria-label={t('{donor_name} {x} auswählen', {
                            donor_name: d.donor_name,
                            x: formatDate(d.date),
                          })}
                          checked={selected.includes(d.id)}
                          onChange={(e) => toggle(d.id, e.target.checked)}
                        />
                      )}
                    </td>
                  )}
                  <td>{formatDate(d.date)}</td>
                  <td>
                    <strong>{d.donor_name}</strong>
                    {d.booking_number && (
                      <span className="muted small">
                        {' '}
                        {t('· Buchung')} {d.booking_number}
                      </span>
                    )}
                  </td>
                  <td>
                    {d.kind_label}
                    {d.waiver && (
                      <span className="muted small"> {t('· Verzicht auf Aufwendungsersatz')}</span>
                    )}
                  </td>
                  <td className="num">{euro(d.amount)}</td>
                  <td>{d.statement_number ?? <span className="muted">{t('offen')}</span>}</td>
                  <td className="actions">
                    {canEdit && !d.statement && (
                      <>
                        <button type="button" className="link-button" onClick={() => void edit(d)}>
                          {t('Ändern')}
                        </button>{' '}
                        <button
                          type="button"
                          className="link-button"
                          onClick={() => void remove(d)}
                        >
                          {t('Löschen')}
                        </button>
                      </>
                    )}
                  </td>
                </tr>
                <EditSlot id={editKey('donation', d.id)} colSpan={canEdit ? 7 : 6} />
              </Fragment>
            ))}
          </tbody>
        </table>
      )}
      <PageNav page={page} count={count} onPage={setPage} noun={t('Zuwendungen')} />
      {canEdit && openRows.length > 1 && selected.length === 0 && (
        <p className="muted small">
          {t('Mehrere Zuwendungen eines Zuwendenden ankreuzen ergibt eine Sammelbestätigung.')}
        </p>
      )}
    </div>
  )
}
