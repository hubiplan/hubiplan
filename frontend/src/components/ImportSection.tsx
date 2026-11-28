import { useEffect, useRef, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import type { FormEvent } from 'react'
import { waitFor } from '../api/exchange.ts'
import { transferApi } from '../api/datatransfer.ts'
import type { ImportPreview, TransferBase, TransferJob } from '../api/datatransfer.ts'
import { errorMessage, formatDateTime, useLoad, useUnmountSignal } from './forms.ts'
import { Alert, Checkbox, LoadError } from './ui.tsx'
import { fillTerms, useTerms } from '../org/terms.ts'
import { t } from '../i18n/index.ts'
import { RUNNING, type Address } from './dataTransferHelpers.ts'
import { ImportPreviewView } from './ImportPreviewView.tsx'

const TARGET_TEXT = {
  platform: {
    title: t('Einheit importieren'),
    hint: t(
      'Aus der Exportdatei einer Einheit (mit ihren Untereinheiten) entsteht eine neue Einheit direkt unter der Plattform.',
    ),
  },
  federation: {
    title: t('{Sg} aus Datei anlegen'),
    hint: t(
      'Aus der Exportdatei entsteht {ein} {e_im}. Personen, die es {e_im} schon gibt, werden erkannt.',
    ),
  },
  club: {
    title: t('{Sg} aus Datei anlegen'),
    hint: t(
      'Aus der Exportdatei entsteht {ein} mit Rollen und Mitgliedern. Wer schon Mitglied {e_im} ist, wird nur zugeordnet.',
    ),
  },
}

/** Datei hochladen, Vorschau prüfen, Dubletten entscheiden, übernehmen. */
export function ImportSection({
  base,
  target,
  onImported,
}: {
  base: TransferBase
  target: 'platform' | 'federation' | 'club'
  onImported?: () => void
}) {
  const [file, setFile] = useState<File | null>(null)
  const [name, setName] = useState('')
  const [invite, setInvite] = useState(false)
  const [boardEmail, setBoardEmail] = useState('')
  const [address, setAddress] = useState<Address>(NO_ADDRESS)
  const [job, setJob] = useState<TransferJob | null>(null)
  const [choices, setChoices] = useState<Record<string, string>>({})
  const [permissionsSchema, setPermissionsSchema] = useState<1 | 2 | null>(null)
  const [permissionsConfirmed, setPermissionsConfirmed] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const tm = useTerms()
  const text = TARGET_TEXT[target]
  const title = fillTerms(text.title, tm)
  const signal = useUnmountSignal()
  // Auftrag in der Adresse merken: nach Neuladen oder Rückkehr wieder erreichbar
  // (UI-Audit NAF-04)
  const [params, setParams] = useSearchParams()
  const jobParam = Number(params.get('import')) || null
  const openJobs = useLoad(() => transferApi.imports(base), [JSON.stringify(base)])

  function rememberJob(id: number | null) {
    setParams(
      (p) => {
        const next = new URLSearchParams(p)
        if (id) next.set('import', String(id))
        else next.delete('import')
        return next
      },
      { replace: true },
    )
  }

  // Nur beim Öffnen mit Auftrag in der Adresse fortsetzen; spätere Änderungen der
  // Adresse kommen von hier selbst und dürfen die Entscheidungen nicht zurücksetzen
  const initialJob = useRef(jobParam)
  useEffect(() => {
    const id = initialJob.current
    initialJob.current = null
    if (id) void act(() => transferApi.importJob(base, id))
    // oxlint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const preview = job?.preview && 'kind' in job.preview ? (job.preview as ImportPreview) : null

  async function wait(id: number) {
    return waitFor(() => transferApi.importJob(base, id), RUNNING, 600000, signal())
  }

  async function act(action: () => Promise<TransferJob>) {
    setBusy(true)
    setError(null)
    let started: TransferJob | null = null
    try {
      started = await action()
      // Den Auftrag sofort merken: auch wenn das Nachfragen scheitert, bleibt er erreichbar
      setJob(started)
      rememberJob(started.id)
      const finished = await wait(started.id)
      setJob(finished)
      setPermissionsSchema(finished.options.permissions_schema ?? null)
      setPermissionsConfirmed(finished.options.permissions_confirmed ?? false)
      const p = finished.preview as ImportPreview
      if (p && 'duplicates' in p) {
        const next: Record<string, string> = {}
        for (const d of p.duplicates) if (!d.fixed) next[String(d.person)] = d.choice
        setChoices(next)
      }
      if (finished.status === 'done') onImported?.()
    } catch (err) {
      setError(
        started
          ? t(
              'Die Verbindung wurde unterbrochen ({x}). Der Auftrag kann trotzdem weiterlaufen; frag den Stand unten erneut ab.',
              { x: errorMessage(err) },
            )
          : errorMessage(err),
      )
    } finally {
      setBusy(false)
    }
  }

  function options() {
    return {
      name: name.trim(),
      invite,
      board_email: boardEmail.trim(),
      ...trimmed(address),
      persons: choices,
      permissions_schema: permissionsSchema,
      permissions_confirmed: permissionsConfirmed,
    }
  }

  function reset() {
    rememberJob(null)
    void openJobs.reload()
    setJob(null)
    setFile(null)
    setName('')
    setBoardEmail('')
    setAddress(NO_ADDRESS)
    setInvite(false)
    setPermissionsSchema(null)
    setPermissionsConfirmed(false)
  }

  if (job?.status === 'done') {
    const result = job.summary as {
      organization?: { name: string }
      department?: { name: string }
      new_members?: number
      invited?: number
      renumbered?: number
      skipped_assignments?: number
    }
    return (
      <div className="card card-wide">
        <h2>{title}</h2>
        <Alert kind="success">
          „{result.organization?.name ?? result.department?.name}
          {t('“ wurde angelegt.')}
          {result.new_members
            ? t(' {new_members} neue Mitglieder {e_im}.', {
                new_members: result.new_members,
                e_im: tm.e_im,
              })
            : ''}
          {result.invited
            ? t(' {invited} Einladungen verschickt.', { invited: result.invited })
            : ''}
          {result.renumbered
            ? t(' {renumbered} Verbandsnummern neu vergeben.', { renumbered: result.renumbered })
            : ''}
          {result.skipped_assignments
            ? t(' {skipped_assignments} Rollenbesetzungen ohne Konto entfielen.', {
                skipped_assignments: result.skipped_assignments,
              })
            : ''}
        </Alert>
        <button type="button" className="button button-ghost" onClick={reset}>
          {t('Weitere Datei importieren')}
        </button>
      </div>
    )
  }

  return (
    <div className="card card-wide">
      <h2>{title}</h2>
      <p className="muted small">{fillTerms(text.hint, tm)}</p>
      {job && RUNNING.includes(job.status) && (
        <div className="stack-sm">
          <Alert kind="info">
            {t(
              'Auftrag {id} wird noch bearbeitet. Du kannst den Stand jederzeit erneut abfragen; dabei entsteht kein neuer Auftrag.',
              { id: job.id },
            )}
          </Alert>
          <div className="button-row">
            <button
              type="button"
              className="button button-ghost"
              disabled={busy}
              onClick={() => void act(() => transferApi.importJob(base, job.id))}
            >
              {busy ? t('Wird abgefragt …') : t('Stand erneut abfragen')}
            </button>
          </div>
        </div>
      )}
      {!job && (openJobs.data ?? []).some((j) => j.status !== 'done' && j.status !== 'failed') && (
        <div className="subcard stack-sm">
          <h3>{t('Offene Aufträge')}</h3>
          <ul className="plain-list">
            {(openJobs.data ?? [])
              .filter((j) => j.status !== 'done' && j.status !== 'failed')
              .map((j) => (
                <li key={j.id}>
                  {j.file_name || t('Auftrag {id}', { id: j.id })}{' '}
                  <span className="muted small">
                    {formatDateTime(j.created_at)} · {j.status_label}
                  </span>{' '}
                  <button
                    type="button"
                    className="link-button"
                    disabled={busy}
                    onClick={() => void act(() => transferApi.importJob(base, j.id))}
                  >
                    {j.status === 'checked' ? t('Auftrag weiter prüfen') : t('Stand ansehen')}
                  </button>
                </li>
              ))}
          </ul>
        </div>
      )}
      {!job && openJobs.error && (
        <LoadError
          message={t('Offene Aufträge konnten nicht geladen werden. {error}', {
            error: openJobs.error,
          })}
          onRetry={() => void openJobs.reload()}
        />
      )}
      {!job && (
        <form
          onSubmit={(e: FormEvent) => {
            e.preventDefault()
            if (file) void act(() => transferApi.upload(base, file, options()))
          }}
        >
          <label className="field">
            <span>{t('Exportdatei (.json oder .zip)')}</span>
            <input
              type="file"
              accept=".json,.zip,application/json,application/zip"
              onChange={(e) => setFile(e.target.files?.[0] ?? null)}
            />
          </label>
          <button type="submit" className="button button-primary" disabled={!file || busy}>
            {busy ? t('Wird geprüft …') : t('Hochladen und prüfen')}
          </button>
        </form>
      )}
      {job?.status === 'failed' && (
        <>
          <Alert kind="error">{job.error}</Alert>
          <button type="button" className="button button-ghost" onClick={reset}>
            {t('Andere Datei wählen')}
          </button>
        </>
      )}
      {preview && job && (
        <>
          {preview.permission_policy &&
            !preview.permission_policy.marked &&
            preview.permission_policy.ambiguous && (
              <div className="subcard stack-sm">
                <p>
                  {t(
                    'Die Datei kennzeichnet ihr Rechteformat nicht. Wähle die ursprüngliche Bedeutung und prüfe danach die wirksamen Rollenrechte.',
                  )}
                </p>
                <label className="field">
                  <span>{t('Bedeutung der Rollenrechte')}</span>
                  <select
                    value={permissionsSchema ?? ''}
                    disabled={busy}
                    onChange={(e) => {
                      setPermissionsSchema(
                        e.target.value ? (Number(e.target.value) as 1 | 2) : null,
                      )
                      setPermissionsConfirmed(false)
                    }}
                  >
                    <option value="">{t('Bitte ausdrücklich auswählen')}</option>
                    <option value="1">
                      {t(
                        'Historische Rechte einschließlich früherer Foto-, Ausweis- und Zugangsdatenrechte',
                      )}
                    </option>
                    <option value="2">
                      {t('Bereichsrechte mit getrennten Foto-, Ausweis- und Zugangsdatenrechten')}
                    </option>
                  </select>
                </label>
                <p className="muted small">
                  {t('Nach einer Änderung zuerst „Erneut prüfen“ wählen.')}
                </p>
                <Checkbox
                  label={t(
                    'Die unten angezeigten wirksamen Rollenrechte sind geprüft und bestätigt.',
                  )}
                  checked={permissionsConfirmed}
                  disabled={
                    busy ||
                    permissionsSchema === null ||
                    preview.permission_policy.schema !== permissionsSchema
                  }
                  onChange={setPermissionsConfirmed}
                />
              </div>
            )}
          {!!preview.permission_policy?.roles.length && (
            <details open className="small">
              <summary>{t('Wirksame Rollenrechte nach dem Import')}</summary>
              <ul>
                {preview.permission_policy.roles.map((role, index) => (
                  <li key={index}>
                    <strong>
                      {role.unit}: {role.name}
                    </strong>
                    : {role.permissions.join(', ') || t('Keine Rechte')}
                  </li>
                ))}
              </ul>
            </details>
          )}
          <ImportPreviewView
            preview={preview}
            target={target}
            choices={choices}
            setChoices={setChoices}
            name={name}
            setName={setName}
            invite={invite}
            setInvite={setInvite}
            boardEmail={boardEmail}
            setBoardEmail={setBoardEmail}
            address={address}
            setAddress={setAddress}
            busy={busy}
            runError={job.error}
            onRecheck={() => void act(() => transferApi.recheck(base, job.id, options()))}
            onRun={() =>
              void act(async () => {
                // Geänderte Angaben zuerst prüfen lassen, dann übernehmen
                const checked = await wait((await transferApi.recheck(base, job.id, options())).id)
                setJob(checked)
                const p = checked.preview as ImportPreview
                if (checked.status !== 'checked' || p.error_count) return checked
                return transferApi.run(base, job.id)
              })
            }
            onCancel={reset}
          />
        </>
      )}
      {error && <Alert kind="error">{error}</Alert>}
    </div>
  )
}

const NO_ADDRESS: Address = { street: '', postal_code: '', city: '' }

/** Nur ausgefüllte Felder schicken: leere übernehmen die Anschrift aus der Datei. */
function trimmed(a: Address): Partial<Address> {
  return Object.fromEntries(
    Object.entries(a)
      .map(([k, v]) => [k, v.trim()])
      .filter(([, v]) => v),
  )
}
