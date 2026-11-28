import { useState } from 'react'
import { FolderIcon } from './DocumentIcons.tsx'
import './documents.css'
import type { FormEvent } from 'react'
import { docApi, formatSize } from '../../api/documents.ts'
import type { DocBase, DocItem, DocOverview, Visibility } from '../../api/documents.ts'
import { StatutePanel } from '../../components/StatutePanel.tsx'
import { errorMessage } from '../../components/forms.ts'
import { Alert, Checkbox, Field, SelectField } from '../../components/ui.tsx'
import { PageActions } from '../../components/PageHeader.tsx'
import { useTerms } from '../../org/terms.ts'
import { Why } from '../../learning/Aids.tsx'
import { t, tn } from '../../i18n/index.ts'
import { type Msg } from './documentsHelpers.ts'
import { DocumentRow } from './DocumentRow.tsx'
import { FolderView } from './FolderView.tsx'

function matches(doc: DocItem, query: string): boolean {
  if (!query) return true
  const q = query.trim().toLocaleLowerCase('de')
  return (
    doc.title.toLocaleLowerCase('de').includes(q) || doc.note.toLocaleLowerCase('de').includes(q)
  )
}

export function Library({
  base,
  data,
  reload,
  orgId,
  canEditStatute,
}: {
  base: DocBase
  data: DocOverview
  reload: () => Promise<void>
  orgId: number | null
  canEditStatute: boolean
}) {
  const [query, setQuery] = useState('')
  const [view, setView] = useState<'tiles' | 'list'>('tiles')
  const [selected, setSelected] = useState<string | null>(null)
  const [creating, setCreating] = useState(false)
  const [message, setMessage] = useState<Msg>(null)
  const [busy, setBusy] = useState(false)
  const [newName, setNewName] = useState('')
  const [newVisibility, setNewVisibility] = useState<Visibility>('board')
  const [newShared, setNewShared] = useState(false)
  const tm = useTerms()
  const shareUp = data.share_up_label ?? null
  const manage = data.can_manage
  const visibilities = data.visibilities ?? []

  async function run(action: () => Promise<unknown>, success?: string) {
    setBusy(true)
    setMessage(null)
    try {
      await action()
      await reload()
      if (success) setMessage({ kind: 'success', text: success })
    } catch (err) {
      setMessage({ kind: 'error', text: errorMessage(err) })
    } finally {
      setBusy(false)
    }
  }

  async function createFolder(e: FormEvent) {
    e.preventDefault()
    if (!newName.trim()) return
    await run(async () => {
      await docApi.createFolder(base, newName.trim(), newVisibility, newShared)
      setNewName('')
      setNewShared(false)
    }, t('Der Ordner wurde angelegt.'))
  }

  const ctx = { base, manage, busy, run, folders: data.folders, visibilities, setMessage, shareUp }
  // Nur die vom Server nach Rechten gefilterten Ordner verwenden.
  // Herkunft voranstellen, damit Freigaben auch bei gleichen IDs getrennt bleiben.
  const groups = [
    { key: 'own', label: t('Eigene Ordner'), folders: data.folders, writable: manage },
    {
      key: 'below',
      label: t('Von den {pl_dat}', { pl_dat: tm.pl_dat }),
      folders: data.from_below ?? [],
      writable: false,
    },
    { key: 'shared', label: tm.dv_Vom, folders: data.shared ?? [], writable: false },
  ]
  const entries = groups.flatMap((group) =>
    group.folders.map((folder) => ({
      key: `${group.key}:${folder.id}`,
      folder,
      group,
      writable: group.writable,
    })),
  )
  const fixed = orgId
    ? [
        { key: 'statute' as const, name: t('Satzung') },
        { key: 'fee_rules' as const, name: t('Beitragsordnung') },
        { key: 'founding_deed' as const, name: t('Gründungsurkunde') },
      ]
    : []
  const activeFolder = entries.find((entry) => entry.key === selected)
  const activeFixed = fixed.find((entry) => entry.key === selected)
  const q = query.trim().toLocaleLowerCase('de')
  const nameMatches = (name: string) => name.toLocaleLowerCase('de').includes(q)
  const foundFolders = entries.filter((entry) => nameMatches(entry.folder.name))
  const foundFixed = fixed.filter(
    (entry) =>
      nameMatches(entry.name) || (entry.key === 'founding_deed' && 'gruendungsurkunde'.includes(q)),
  )
  const foundDocuments = entries.flatMap((entry) =>
    entry.folder.documents.filter((doc) => matches(doc, q)).map((doc) => ({ entry, doc })),
  )
  const hits = foundFolders.length + foundFixed.length + foundDocuments.length
  const atRoot = !activeFolder && !activeFixed

  function navigate(key: string | null) {
    setSelected(key)
    setQuery('')
    setCreating(false)
    setMessage(null)
  }

  function folderCard(entry: (typeof entries)[number]) {
    const { folder, writable } = entry
    return (
      <li key={entry.key}>
        <button
          type="button"
          className="doc-folder-card"
          aria-label={[
            folder.name,
            tn('{n} Dokument', '{n} Dokumente', folder.documents.length),
            folder.from ? t('von {from}', { from: folder.from }) : folder.visibility_label,
            folder.department,
            folder.shared_up ? t('nach oben freigegeben') : '',
            !writable ? t('Nur lesen') : '',
          ]
            .filter(Boolean)
            .join(' ')}
          onClick={() => navigate(entry.key)}
        >
          <FolderIcon locked={folder.visibility === 'board'} />
          <span className="doc-folder-caption">
            <strong>{folder.name}</strong>
            <span className="muted small">
              {tn('{n} Dokument', '{n} Dokumente', folder.documents.length)}
            </span>
            <span className="badge">
              {folder.from ? t('von {from}', { from: folder.from }) : folder.visibility_label}
            </span>
            {folder.department && <span className="badge">{folder.department}</span>}
            {folder.shared_up && <span className="badge">{t('nach oben freigegeben')}</span>}
            {!writable && <span className="muted small">{t('Nur lesen')}</span>}
          </span>
        </button>
      </li>
    )
  }

  function fixedCard(entry: (typeof fixed)[number]) {
    return (
      <li key={entry.key}>
        <button
          type="button"
          className="doc-folder-card"
          aria-label={`${entry.name} ${t('fester Ordner')}`}
          onClick={() => navigate(entry.key)}
        >
          <FolderIcon />
          <span className="doc-folder-caption">
            <strong>{entry.name}</strong>
            <span className="badge">{t('fester Ordner')}</span>
          </span>
        </button>
      </li>
    )
  }

  return (
    <div className={`documents doc-explorer doc-explorer-${view}`}>
      <div className="documents-toolbar">
        <Field
          label={t('Suchen (Ordner, Titel und Bemerkung)')}
          type="search"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
        {/* Ansichtswahl als Segmentschalter: Zustand, keine Aktion (W-14) */}
        <div className="segmented" role="group" aria-label={t('Ansicht')}>
          <button
            type="button"
            className="button button-ghost"
            aria-pressed={view === 'tiles'}
            onClick={() => setView('tiles')}
          >
            <span aria-hidden="true">▦</span> {t('Kachelansicht')}
          </button>
          <button
            type="button"
            className="button button-ghost"
            aria-pressed={view === 'list'}
            onClick={() => setView('list')}
          >
            <span aria-hidden="true">☰</span> {t('Listenansicht')}
          </button>
        </div>
        <PageActions
          primary={
            manage && atRoot && !q
              ? {
                  label: t('Neuer Ordner'),
                  expanded: creating,
                  controls: 'doc-create-folder',
                  onClick: () => setCreating(!creating),
                }
              : null
          }
        />
        {data.used_bytes !== undefined && (
          <p className="muted small">
            {t('Belegter Platz:')} {formatSize(data.used_bytes)}
            {data.budget_bytes
              ? ` ${t('(Verein gesamt {used} von {budget})', { used: formatSize(data.total_bytes ?? 0), budget: formatSize(data.budget_bytes) })}`
              : ''}
            {data.trash_count
              ? t(' · {trash_count} im Papierkorb', { trash_count: data.trash_count })
              : ''}
          </p>
        )}
      </div>
      {!!data.budget_bytes && (
        <progress
          className="doc-storage"
          aria-label={t('Belegter Speicherplatz')}
          max={data.budget_bytes}
          value={Math.min(data.total_bytes ?? 0, data.budget_bytes)}
        />
      )}
      <nav className="doc-breadcrumbs" aria-label={t('Ordnerpfad')}>
        <button
          type="button"
          className="button button-ghost"
          aria-current={atRoot && !q ? 'page' : undefined}
          onClick={() => navigate(null)}
        >
          {t('Dokumente')}
        </button>
        {!atRoot && (
          <>
            <span aria-hidden="true">/</span>
            <button
              type="button"
              className="button button-ghost"
              aria-current={!q ? 'page' : undefined}
              onClick={() => navigate(selected)}
            >
              {activeFolder?.folder.name ?? activeFixed?.name}
            </button>
          </>
        )}
        {q && (
          <>
            <span aria-hidden="true">/</span>
            <span aria-current="page">{t('Suchergebnisse (alle Ordner)')}</span>
          </>
        )}
      </nav>
      {data.budget_bytes && (data.total_bytes ?? 0) >= data.budget_bytes * 0.8 ? (
        <Alert kind="info">
          {t(
            'Der Speicherplatz der Ablage ist zu über 80 % belegt. Bitte alte Fassungen oder den Papierkorb leeren; mehr Platz gibt die Plattform-Verwaltung frei.',
          )}
        </Alert>
      ) : null}
      {message && <Alert kind={message.kind}>{message.text}</Alert>}

      {q ? (
        <section aria-label={t('Suchergebnisse (alle Ordner)')}>
          <div className="button-row">
            <p className="muted small" role="status">
              {hits === 0
                ? t('Keine Ordner oder Dokumente passen zur Suche.')
                : tn(
                    '{n} Treffer in eigenen und freigegebenen Ordnern.',
                    '{n} Treffer in eigenen und freigegebenen Ordnern.',
                    hits,
                  )}
            </p>
            <button type="button" className="button button-ghost" onClick={() => setQuery('')}>
              {t('Suche zurücksetzen')}
            </button>
          </div>
          <ul className="doc-folder-grid">
            {foundFixed.map(fixedCard)}
            {foundFolders.map(folderCard)}
          </ul>
          {entries.map((entry) => {
            const documents = foundDocuments.filter((hit) => hit.entry.key === entry.key)
            return (
              documents.length > 0 && (
                <div key={entry.key} className="doc-search-result">
                  <button
                    type="button"
                    className="button button-ghost"
                    onClick={() => navigate(entry.key)}
                  >
                    {entry.folder.name}
                    {entry.folder.from ? ` · ${entry.folder.from}` : ''}
                  </button>
                  <ul className="statute-list doc-list">
                    {documents.map(({ doc }) => (
                      <DocumentRow
                        key={doc.id}
                        doc={doc}
                        folder={entry.folder}
                        {...ctx}
                        manage={entry.writable}
                      />
                    ))}
                  </ul>
                </div>
              )
            )
          })}
        </section>
      ) : activeFixed && orgId ? (
        <section className="doc-folder" aria-label={activeFixed.name}>
          <StatutePanel key={activeFixed.key} orgId={orgId} heading="h2" kind={activeFixed.key} />
          {!canEditStatute && (
            <p className="muted small">
              {t('Neue Fassungen lädt hoch, wer die Organisationsdaten bearbeiten darf.')}
            </p>
          )}
        </section>
      ) : activeFolder ? (
        <FolderView
          key={activeFolder.key}
          folder={activeFolder.folder}
          docs={activeFolder.folder.documents}
          {...ctx}
          manage={activeFolder.writable}
          from={activeFolder.folder.from}
        />
      ) : (
        <>
          {/* Satzung, Beitragsordnung und Gründungsurkunde nur hier (Menüprüfung M-03) */}
          {fixed.length > 0 && (
            <section className="doc-folder-group" aria-label={t('Vereinsdokumente')}>
              <h2>{t('Vereinsdokumente')}</h2>
              <ul className="doc-folder-grid">{fixed.map(fixedCard)}</ul>
            </section>
          )}
          {groups.map(
            (group) =>
              group.folders.length > 0 && (
                <section key={group.key} className="doc-folder-group" aria-label={group.label}>
                  <h2>{group.label}</h2>
                  {group.key !== 'own' && (
                    <p className="muted small">
                      {t('Diese Ordner sind für euch freigegeben (nur lesen).')}
                    </p>
                  )}
                  <ul className="doc-folder-grid">
                    {entries.filter((entry) => entry.group.key === group.key).map(folderCard)}
                  </ul>
                </section>
              ),
          )}
          {entries.length === 0 && (
            <p className="muted">
              {manage
                ? t('Noch keine Ordner. Lege mit „Neuer Ordner“ den ersten an.')
                : t('Noch keine Dokumente.')}
            </p>
          )}
        </>
      )}

      {manage && atRoot && !q && creating && (
        <form id="doc-create-folder" className="inline-form doc-new-folder" onSubmit={createFolder}>
          <h3>{t('Neuer Ordner')}</h3>
          <div className="grid-3">
            <Field
              label={t('Name')}
              value={newName}
              maxLength={100}
              required
              onChange={(e) => setNewName(e.target.value)}
            />
            <SelectField
              label={t('Sichtbar für')}
              value={newVisibility}
              onChange={(e) => setNewVisibility(e.target.value as Visibility)}
            >
              {visibilities.map((v) => (
                <option key={v.value} value={v.value}>
                  {v.label}
                </option>
              ))}
            </SelectField>
          </div>
          {shareUp && <Checkbox label={shareUp} checked={newShared} onChange={setNewShared} />}
          <Why k="doc_visibility" />
          <button type="submit" className="button button-primary" disabled={busy}>
            {t('Ordner anlegen')}
          </button>
        </form>
      )}
    </div>
  )
}
