// Mitglieder › Würdenträger: Würden (frei benannt, z. B. König, Prinz, Zugkönig),
// Regentschaften mit Begleitpersonen und Foto, Excel-Import der Königsliste.
import { EditAt, editKey } from '../../components/EditInPlace.tsx'
import { EmptyList } from '../../components/EmptyList.tsx'
import { useState } from 'react'
import { Route, Routes } from 'react-router-dom'
import { newRequestKey } from '../../api/client.ts'
import { honorsApi } from '../../api/honors.ts'
import type { ImportRow, Reign, SharedDignity } from '../../api/honors.ts'
import { PERM } from '../../api/orgs.ts'
import { DataTable } from '../../components/DataTable.tsx'
import type { Column } from '../../components/DataTable.tsx'
import { confirmDialog } from '../../components/dialog.ts'
import { errorMessage, useLoad } from '../../components/forms.ts'
import { DeleteIcon, EditIcon, IconButton } from '../../components/icons.tsx'
import { Alert, Loading } from '../../components/ui.tsx'
import { useActiveOrg } from '../../org/OrgContext.tsx'
import { MembersSection } from '../MembersPage.tsx'
import { t, tn } from '../../i18n/index.ts'
import { ReignForm } from './ReignForm.tsx'
import { DignitiesPanel } from './DignitiesPanel.tsx'
import { CandidateSelect } from './CandidateSelect.tsx'

export function ChroniclePage() {
  const org = useActiveOrg()
  const canEdit = org.permissions.includes(PERM.membersEdit)
  const tabs = [
    { to: '/mitglieder/wuerdentraeger', label: t('Regentschaften') },
    { to: '/mitglieder/wuerdentraeger/wuerden', label: t('Würden') },
    ...(canEdit ? [{ to: '/mitglieder/wuerdentraeger/import', label: t('Import') }] : []),
  ]
  return (
    <MembersSection title={t('Würdenträger')} tabs={tabs}>
      <Routes>
        <Route index element={<ReignsPanel />} />
        <Route path="wuerden" element={<DignitiesPanel />} />
        {canEdit && <Route path="import" element={<ImportPanel />} />}
      </Routes>
    </MembersSection>
  )
}

// --- Regentschaften ---

function ReignsPanel() {
  const org = useActiveOrg()
  const canEdit = org.permissions.includes(PERM.membersEdit)
  const dignities = useLoad(() => honorsApi.dignities(org.id), [org.id])
  const reigns = useLoad(() => honorsApi.reigns(org.id), [org.id])
  const origins = useLoad(() => honorsApi.origins(org.id), [org.id])
  const shared = useLoad(() => honorsApi.shared(org.id), [org.id])
  const [editing, setEditing] = useState<Reign | 'new' | null>(null)
  const [message, setMessage] = useState<string | null>(null)

  if (dignities.error || reigns.error)
    return <Alert kind="error">{dignities.error ?? reigns.error}</Alert>
  if (!dignities.data || !reigns.data) return <Loading />
  const usable = dignities.data.filter((d) => !d.is_archived)

  async function remove(r: Reign) {
    const ok = await confirmDialog({
      final: false,
      title: t('Regentschaft löschen?'),
      message: t('{dignity_name} {period_text}: {display_name}', {
        dignity_name: r.dignity_name,
        period_text: r.period_text,
        display_name: r.display_name,
      }),
      confirmLabel: t('Löschen'),
    })
    if (!ok) return
    try {
      await honorsApi.deleteReign(org.id, r.id)
      await reigns.reload()
    } catch (err) {
      setMessage(errorMessage(err))
    }
  }

  const columns: Column<Reign>[] = [
    {
      key: 'year',
      label: t('Jahr'),
      value: (r) => r.year ?? Number((r.valid_from ?? '0').slice(0, 4)),
      render: (r) => r.period_text,
      numeric: true,
    },
    { key: 'dignity', label: t('Würde'), value: (r) => r.dignity_name, filter: true },
    {
      key: 'name',
      label: t('Name'),
      value: (r) => r.numbered_name,
      render: (r) => (
        <>
          {r.numbered_name}
          {r.person === null && (
            <span className="muted small"> {t('(kein Mitglied verknüpft)')}</span>
          )}
        </>
      ),
    },
    {
      key: 'companions',
      label: t('Begleitung'),
      value: (r) =>
        r.companions
          .map((c) =>
            t('{label}: {display_name}', { label: c.label, display_name: c.display_name }),
          )
          .join(', '),
      optional: true,
    },
    { key: 'origin', label: t('Aus'), value: (r) => r.origin_text, filter: true, optional: true },
    { key: 'note', label: t('Bemerkung'), value: (r) => r.note, optional: true },
    { key: 'photo', label: t('Foto'), value: (r) => (r.photo ? 'ja' : ''), optional: true },
  ]

  return (
    <div className="card card-wide">
      {canEdit && <PhotoConsentHint org={org.id} />}
      <div className="card-head">
        <h2>{t('Regentschaften')}</h2>
        {canEdit && editing === null && usable.length > 0 && (
          <button
            type="button"
            className="button button-ghost push-right"
            onClick={() => setEditing('new')}
          >
            {t('Neue Regentschaft')}
          </button>
        )}
      </div>
      <p className="muted small">
        {t(
          'Wer in welchem Jahr welche Würde trug, mit Begleitpersonen. Personen aus der Zeit vor HUBIplan tragt ihr als Namen ein. Auf der Webseite erscheinen Namen, solange die Person nicht widersprochen hat; Fotos verknüpfter Mitglieder nur mit Einwilligung.',
        )}
      </p>
      {usable.length === 0 && (
        <Alert kind="info">{t('Legt zuerst unter „Würden“ an, welche Würden es gibt.')}</Alert>
      )}
      {editing !== null && (
        <EditAt at={editing === 'new' ? null : editKey('reign', editing.id)}>
          <ReignForm
            key={editing === 'new' ? 'new' : editing.id}
            reign={editing === 'new' ? null : editing}
            dignities={dignities.data.filter(
              (d) => !d.is_archived || (editing !== 'new' && d.id === editing.dignity),
            )}
            origins={origins.data ?? []}
            onDone={async () => {
              setEditing(null)
              await reigns.reload()
            }}
            onCancel={() => setEditing(null)}
          />
        </EditAt>
      )}
      {message && <Alert kind="error">{message}</Alert>}
      <DataTable
        label={t('Regentschaften')}
        slot="reign"
        rows={reigns.data}
        rowKey={(r) => r.id}
        columns={columns}
        initialSort={{ key: 'year', dir: 'desc' }}
        emptyText={t('Noch keine Regentschaften erfasst.')}
        empty={
          editing === null ? (
            <EmptyList
              title={t('Noch keine Regentschaften erfasst.')}
              canAdd={canEdit && usable.length > 0}
              action={{ label: t('Neue Regentschaft'), onClick: () => setEditing('new') }}
            />
          ) : undefined
        }
        actions={
          canEdit
            ? (r) => (
                <>
                  <IconButton
                    label={t('{display_name} {period_text} bearbeiten', {
                      display_name: r.display_name,
                      period_text: r.period_text,
                    })}
                    icon={<EditIcon />}
                    onClick={() => setEditing(r)}
                  />
                  <IconButton
                    label={t('{display_name} {period_text} löschen', {
                      display_name: r.display_name,
                      period_text: r.period_text,
                    })}
                    icon={<DeleteIcon />}
                    danger
                    onClick={() => void remove(r)}
                  />
                </>
              )
            : undefined
        }
      />
      {(shared.data ?? []).map((d) => (
        <SharedCard key={d.id} dignity={d} />
      ))}
    </div>
  )
}

/** Würde der Einheit darüber mit den Trägern, die aus dieser Einheit kamen (nur lesen). */
function SharedCard({ dignity }: { dignity: SharedDignity }) {
  type Row = SharedDignity['reigns'][number]
  const columns: Column<Row>[] = [
    {
      key: 'year',
      label: t('Jahr'),
      value: (r) => r.year,
      render: (r) => r.period_text,
      numeric: true,
    },
    { key: 'name', label: t('Name'), value: (r) => r.numbered_name },
    {
      key: 'companions',
      label: t('Begleitung'),
      value: (r) =>
        r.companions.map((c) => t('{label}: {name}', { label: c.label, name: c.name })).join(', '),
      optional: true,
    },
    { key: 'note', label: t('Bemerkung'), value: (r) => r.note, optional: true },
  ]
  return (
    <section className="subcard">
      <h3>
        {dignity.name} ({dignity.owner})
      </h3>
      <p className="muted small">
        {t(
          'Diese Würde vergibt {owner}. Hier stehen die Träger, die aus eurer Einheit kamen; ändern kann sie nur {owner2}.',
          { owner: dignity.owner, owner2: dignity.owner },
        )}
      </p>
      <DataTable
        label={t('{name} ({owner})', { name: dignity.name, owner: dignity.owner })}
        rows={dignity.reigns}
        rowKey={(r) => r.id}
        columns={columns}
        initialSort={{ key: 'year', dir: 'desc' }}
        emptyText={t('Keine Träger aus eurer Einheit.')}
      />
    </section>
  )
}

interface Decision {
  take: boolean
  person_id: number | null
  companions: (number | null)[]
}

function ImportPanel() {
  const org = useActiveOrg()
  const [rows, setRows] = useState<ImportRow[] | null>(null)
  // Ein Schlüssel je Vorschau: nochmal „Übernehmen“ (z. B. nach Verbindungsabbruch)
  // legt nichts doppelt an
  const [requestKey, setRequestKey] = useState(newRequestKey)
  const [newDignities, setNewDignities] = useState<string[]>([])
  const [decisions, setDecisions] = useState<Decision[]>([])
  const [error, setError] = useState<string | null>(null)
  const [result, setResult] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  async function read(file: File) {
    setError(null)
    setResult(null)
    setBusy(true)
    try {
      const data = await honorsApi.importPreview(org.id, file)
      setRows(data.rows)
      setRequestKey(newRequestKey())
      setNewDignities(data.new_dignities)
      setDecisions(
        data.rows.map((r) => ({
          take: r.errors.length === 0 && !r.duplicate,
          person_id: r.person_id,
          companions: r.companions.map((c) => c.person_id),
        })),
      )
    } catch (err) {
      setRows(null)
      setError(errorMessage(err))
    } finally {
      setBusy(false)
    }
  }

  function decide(index: number, patch: Partial<Decision>) {
    setDecisions((all) => all.map((d, i) => (i === index ? { ...d, ...patch } : d)))
  }

  async function commit() {
    if (!rows) return
    setBusy(true)
    setError(null)
    try {
      const chosen = rows
        .map((r, i) => ({ r, d: decisions[i] }))
        .filter(({ r, d }) => d.take && r.errors.length === 0 && r.year !== null)
        .map(({ r, d }) => ({
          year: r.year as number,
          end_year: r.end_year ?? null,
          dignity: r.dignity,
          name: r.name,
          person_id: d.person_id,
          note: r.note,
          ordinal: r.ordinal ?? null,
          origin: r.origin ?? null,
          origin_name: r.origin_name ?? '',
          companions: r.companions.map((c, j) => ({
            label: c.label,
            name: c.name,
            person_id: d.companions[j],
          })),
        }))
      const res = await honorsApi.importRows(org.id, chosen, requestKey)
      setResult(
        t('{created} Regentschaften übernommen.', { created: res.created }) +
          (res.dignities_created.length
            ? t(
                ' Neu angelegte Würden: {x}. Sie sind erst intern; unter „Würden“ könnt ihr sie zur Veröffentlichung freigeben.',
                { x: res.dignities_created.join(', ') },
              )
            : ''),
      )
      setRows(null)
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setBusy(false)
    }
  }

  const count = rows ? decisions.filter((d, i) => d.take && rows[i].errors.length === 0).length : 0

  return (
    <div className="card card-wide">
      <h2>{t('Königsliste importieren')}</h2>
      <p className="muted small">
        {t('Excel- oder CSV-Datei mit den Spalten')} <strong>{t('Jahr')}</strong>,{' '}
        <strong>{t('Würde')}</strong>, <strong>{t('Name')}</strong> {t('und optional')}{' '}
        <strong>{t('Endjahr')}</strong> {t('(für Würden über mehrere Jahre),')}{' '}
        <strong>{t('Begleitung')}</strong>{' '}
        {t('(z. B. „Königin: Erika Beispiel; Minister: Max Muster“),')}{' '}
        <strong>{t('Bemerkung')}</strong>, <strong>{t('Ordnungszahl')}</strong>{' '}
        {t('(z. B. „IV“ aus einer alten Liste; leer zählt HUBIplan selbst) und')}{' '}
        <strong>{t('Aus')}</strong>{' '}
        {t(
          '(Zug oder Verein, aus dem der Würdenträger kam). HUBIplan schlägt zu jedem Namen passende Mitglieder vor; prüft die Zuordnung, bevor ihr übernehmt. Unbekannte Würden werden angelegt, zunächst nur intern.',
        )}
      </p>
      <input
        type="file"
        accept=".xlsx,.xlsm,.csv,.txt"
        aria-label={t('Datei auswählen')}
        disabled={busy}
        onChange={(e) => {
          const file = e.target.files?.[0]
          if (file) void read(file)
        }}
      />
      {error && <Alert kind="error">{error}</Alert>}
      {result && <Alert kind="success">{result}</Alert>}
      {rows && (
        <>
          {newDignities.length > 0 && (
            <Alert kind="info">
              {t('Neue Würden werden angelegt:')} {newDignities.join(', ')}
              {t('. Sie erscheinen nicht auf der Webseite, bis ihr sie unter „Würden“ freigebt.')}
            </Alert>
          )}
          <div className="table-scroll">
            <table className="table">
              <thead>
                <tr>
                  <th>{t('Übernehmen')}</th>
                  <th>{t('Zeile')}</th>
                  <th>{t('Jahr')}</th>
                  <th>{t('Würde')}</th>
                  <th>{t('Name und Zuordnung')}</th>
                  <th>{t('Zahl')}</th>
                  <th>{t('Begleitung')}</th>
                  <th>{t('Bemerkung')}</th>
                  <th>{t('Aus')}</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((r, i) => (
                  <tr key={r.line} className={r.errors.length ? 'inactive' : undefined}>
                    <td>
                      <input
                        type="checkbox"
                        aria-label={t('Zeile {line} übernehmen', { line: r.line })}
                        checked={decisions[i].take}
                        disabled={r.errors.length > 0}
                        onChange={(e) => decide(i, { take: e.target.checked })}
                      />
                    </td>
                    <td>{r.line}</td>
                    <td>{r.end_year ? `${r.year}–${r.end_year}` : (r.year ?? '')}</td>
                    <td>{r.dignity}</td>
                    <td>
                      {r.name}
                      {r.errors.length > 0 && (
                        <div className="field-error small">{r.errors.join(' ')}</div>
                      )}
                      {r.duplicate && <div className="muted small">{t('Schon vorhanden.')}</div>}
                      {r.name && (
                        <CandidateSelect
                          label={t('Zuordnung Zeile {line}', { line: r.line })}
                          candidates={r.candidates}
                          value={decisions[i].person_id}
                          onChange={(id) => decide(i, { person_id: id })}
                        />
                      )}
                    </td>
                    <td>{r.ordinal_text}</td>
                    <td>
                      {r.companions.map((c, j) => (
                        <div key={j}>
                          {c.label}: {c.name}
                          <CandidateSelect
                            label={t('Zuordnung {label} Zeile {line}', {
                              label: c.label,
                              line: r.line,
                            })}
                            candidates={c.candidates ?? []}
                            value={decisions[i].companions[j]}
                            onChange={(id) =>
                              decide(i, {
                                companions: decisions[i].companions.map((x, k) =>
                                  k === j ? id : x,
                                ),
                              })
                            }
                          />
                        </div>
                      ))}
                    </td>
                    <td>{r.note}</td>
                    <td>
                      {r.origin_text}
                      {r.origin_name && <span className="muted small"> {t('(frei)')}</span>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="button-row">
            <button
              type="button"
              className="button button-primary"
              disabled={busy || count === 0}
              onClick={() => void commit()}
            >
              {count} {t('Regentschaften übernehmen')}
            </button>
          </div>
        </>
      )}
    </div>
  )
}

/** Würden-Fotos mit frei eingetragenen Namen ohne bestätigte Einwilligung: Hinweis und
 * Sammelaktion zum Nachtragen (Gesamtaudit 15.11., PF-21). */
function PhotoConsentHint({ org }: { org: number }) {
  const state = useLoad(() => honorsApi.photoConsentOpen(org), [org])
  const [error, setError] = useState<string | null>(null)
  const open = state.data?.open ?? 0
  if (!open) return null
  async function confirmAll() {
    if (
      !(await confirmDialog({
        title: t('Einwilligungen bestätigen?'),
        message: t(
          'Du bestätigst für {n} Fotos, dass die nur mit Namen eingetragenen Abgebildeten in die Veröffentlichung eingewilligt haben.',
          { n: open },
        ),
        confirmLabel: t('Bestätigen'),
        danger: false,
      }))
    )
      return
    setError(null)
    try {
      state.setData(await honorsApi.confirmAllPhotos(org))
    } catch (err) {
      setError(errorMessage(err))
    }
  }
  return (
    <Alert kind="info">
      {tn(
        '{n} Foto mit nur namentlich eingetragenen Personen erscheint nicht auf der Webseite, bis die Einwilligung der Abgebildeten bestätigt ist.',
        '{n} Fotos mit nur namentlich eingetragenen Personen erscheinen nicht auf der Webseite, bis die Einwilligung der Abgebildeten bestätigt ist.',
        open,
      )}{' '}
      <button type="button" className="link-button" onClick={() => void confirmAll()}>
        {t('Für alle bestätigen …')}
      </button>
      {error && <span className="error"> {error}</span>}
    </Alert>
  )
}
