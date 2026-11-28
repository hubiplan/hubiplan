import { useState } from 'react'
import { waitFor } from '../api/exchange.ts'
import { displayName, unitName } from '../api/orgs.ts'
import { transferApi } from '../api/datatransfer.ts'
import type { TransferBase, TransferJob } from '../api/datatransfer.ts'
import { errorMessage, formatDateTime, useLoad, useUnmountSignal } from './forms.ts'
import { Alert, Checkbox, LoadError } from './ui.tsx'
import { useTerms } from '../org/terms.ts'
import { useOrg } from '../org/OrgContext.tsx'
import { t } from '../i18n/index.ts'
import { Why } from '../learning/Aids.tsx'
import { RUNNING } from './dataTransferHelpers.ts'

function size(bytes: number): string {
  if (bytes > 1024 * 1024) return t('{x} MB', { x: (bytes / 1024 / 1024).toFixed(1) })
  return t('{x} KB', { x: Math.max(1, Math.round(bytes / 1024)) })
}

/** Export erstellen und frühere Exporte herunterladen. */
export function ExportSection({
  base,
  departments,
  organizations,
}: {
  base: TransferBase
  /** Verein: Abteilungen, die sich einzeln exportieren lassen */
  departments?: { id: number; name: string; display_name?: string }[]
  /** Plattform: Organisationen zur Auswahl */
  organizations?: { id: number; name: string; display_name?: string; type_label: string }[]
}) {
  const tm = useTerms()
  const { active } = useOrg()
  // Ohne Mitglieder (z. B. reines Kassenbuch) nennt der Text nur, was es gibt
  const hasMembers = !active || active.type === 'platform' || active.modules.includes('members')
  const jobs = useLoad(() => transferApi.exports(base), [JSON.stringify(base)])
  const [withFiles, setWithFiles] = useState(false)
  const [target, setTarget] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [last, setLast] = useState<TransferJob | null>(null)
  const signal = useUnmountSignal()

  async function start() {
    setBusy(true)
    setError(null)
    setLast(null)
    try {
      const data: Record<string, unknown> = { with_files: withFiles }
      if (organizations) data.organization = Number(target)
      else if (target) {
        data.kind = 'department'
        data.department = Number(target)
      }
      const created = await transferApi.startExport(base, data as never)
      setLast(
        await waitFor(() => transferApi.exportJob(base, created.id), RUNNING, 300000, signal()),
      )
      await jobs.reload()
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="card card-wide">
      <h2>{t('Vollständiger Export')}</h2>
      <Why k="full_export" />
      <p className="muted small">
        {hasMembers
          ? t(
              'Alle Daten als eine Datei: Stammdaten, Rollen, Mitgliedsarten, Zusatzfelder, {pl}, Mitglieder mit allen Zeiträumen, Kasse, Beiträge und Rechnungen sowie die Satzung. Benutzerkonten und Passwörter sind nicht enthalten. Jeder Export wird protokolliert, die Datei wird nach 7 Tagen gelöscht.',
              { pl: tm.pl },
            )
          : t(
              'Alle Daten als eine Datei: Stammdaten, Rollen, Kasse mit Belegen, Geschäftspartner und alles Weitere, was ihr eingeschaltet habt. Benutzerkonten und Passwörter sind nicht enthalten. Jeder Export wird protokolliert, die Datei wird nach 7 Tagen gelöscht.',
            )}
      </p>
      <div className="filters">
        {organizations && (
          <select
            aria-label={t('Organisation')}
            value={target}
            onChange={(e) => setTarget(e.target.value)}
          >
            <option value="">{t('Einheit wählen …')}</option>
            {organizations.map((o) => (
              <option key={o.id} value={o.id}>
                {displayName(o)} ({o.type_label})
              </option>
            ))}
          </select>
        )}
        {departments && departments.length > 0 && (
          <select
            aria-label={t('Umfang')}
            value={target}
            onChange={(e) => setTarget(e.target.value)}
          >
            <option value="">
              {t('ganz')}
              {tm.e_adj} {tm.e_sg}
            </option>
            {departments.map((d) => (
              <option key={d.id} value={d.id}>
                {t('nur')} {tm.sg} {unitName(d)}
              </option>
            ))}
          </select>
        )}
        <Checkbox
          label={t('mit Dateien (Logos, Belege, Fotos, Satzung) als ZIP')}
          checked={withFiles}
          onChange={setWithFiles}
        />
        <button
          type="button"
          className="button button-primary"
          disabled={busy || (!!organizations && !target)}
          onClick={() => void start()}
        >
          {busy ? t('Wird erstellt …') : t('Export erstellen')}
        </button>
      </div>
      {error && <Alert kind="error">{error}</Alert>}
      {last?.status === 'done' && (
        <Alert kind="success">
          {t('Fertig.')}{' '}
          <a href={transferApi.downloadUrl(base, last.id)}>
            {last.file_name} {t('herunterladen')}
          </a>
        </Alert>
      )}
      {last?.status === 'failed' && (
        <Alert kind="error">
          {t('Export fehlgeschlagen:')} {last.error}
        </Alert>
      )}
      {last && RUNNING.includes(last.status) && (
        <Alert kind="info">
          {t('Der Export läuft noch im Hintergrund. Die Liste unten zeigt ihn.')}
        </Alert>
      )}
      {jobs.error && (
        <LoadError
          message={t('Die bisherigen Exporte konnten nicht geladen werden: {error}', {
            error: jobs.error,
          })}
          onRetry={() => void jobs.reload()}
        />
      )}
      {jobs.data && jobs.data.length > 0 && (
        <table className="table">
          <thead>
            <tr>
              <th>{t('Erstellt')}</th>
              <th>{t('Inhalt')}</th>
              <th>{t('Datei')}</th>
            </tr>
          </thead>
          <tbody>
            {jobs.data.map((j) => (
              <tr key={j.id}>
                <td className="small">
                  {formatDateTime(j.created_at)}
                  <div className="muted">{j.created_by}</div>
                </td>
                <td className="small">
                  {j.subject?.name ?? j.department?.name ?? t('ganze Einheit')}
                  {j.with_files ? t(' · mit Dateien') : ''}
                </td>
                <td className="small">
                  {j.status === 'done' && j.has_file ? (
                    <a href={transferApi.downloadUrl(base, j.id)}>
                      {j.file_name} ({size(j.size)})
                    </a>
                  ) : j.status === 'done' ? (
                    <span className="muted">{t('gelöscht')}</span>
                  ) : (
                    <span className="muted">{j.status_label}</span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  )
}
