import type { ImportPreview } from '../api/datatransfer.ts'
import { formatDateTime } from './forms.ts'
import { Alert, Checkbox, Field, SelectField } from './ui.tsx'
import { fillTerms, useTerms } from '../org/terms.ts'
import { t } from '../i18n/index.ts'
import { type Address } from './dataTransferHelpers.ts'

const SUMMARY_LABELS: Record<string, string> = {
  clubs: '{Pl}',
  get departments() {
    return t('Untereinheiten')
  },
  get roles() {
    return t('Rollen')
  },
  get role_assignments() {
    return t('Rollenbesetzungen')
  },
  get persons() {
    return t('Personen')
  },
  get memberships() {
    return t('Mitgliedschaften')
  },
  get already_members() {
    return t('schon Mitglied {e_im}')
  },
  get table_rows() {
    return t('Kasse, Beiträge und Satzung (Einträge)')
  },
  get files() {
    return t('Dateien')
  },
}

export function ImportPreviewView({
  preview,
  target,
  choices,
  setChoices,
  name,
  setName,
  invite,
  setInvite,
  boardEmail,
  setBoardEmail,
  address,
  setAddress,
  busy,
  runError,
  onRecheck,
  onRun,
  onCancel,
}: {
  preview: ImportPreview
  target: 'platform' | 'federation' | 'club'
  choices: Record<string, string>
  setChoices: (c: Record<string, string>) => void
  name: string
  setName: (v: string) => void
  invite: boolean
  setInvite: (v: boolean) => void
  boardEmail: string
  setBoardEmail: (v: string) => void
  address: Address
  setAddress: (a: Address) => void
  busy: boolean
  runError: string
  onRecheck: () => void
  onRun: () => void
  onCancel: () => void
}) {
  const tm = useTerms()
  const open = preview.duplicates.filter((d) => !d.fixed)
  const fixed = preview.duplicates.filter((d) => d.fixed)
  const counts = Object.entries(preview.summary).filter(
    ([key, value]) => SUMMARY_LABELS[key] && value,
  )
  return (
    <div className="import-preview">
      <p>
        {t('Datei von')} <strong>{preview.source.name}</strong>
        {preview.exported_at
          ? t(', exportiert am {x}', { x: formatDateTime(preview.exported_at) })
          : ''}
        .
      </p>
      <ul className="small">
        {counts.map(([key, value]) => (
          <li key={key}>
            {fillTerms(
              key === 'departments' && target === 'club' ? '{Pl}' : (SUMMARY_LABELS[key] ?? key),
              tm,
            )}
            : {value}
          </li>
        ))}
      </ul>
      {preview.classes && Object.keys(preview.classes).length > 0 && (
        <details className="small">
          <summary>{t('Je Datenklasse')}</summary>
          <ul>
            {Object.entries(preview.classes).map(([label, n]) => (
              <li key={label}>
                {label}: {n}
              </li>
            ))}
          </ul>
        </details>
      )}
      {preview.not_included && preview.not_included.length > 0 && (
        <p className="small muted">
          {t('Nicht übernommen:')} {preview.not_included.join(', ')}.
        </p>
      )}
      <Field
        label={target === 'club' ? t('Name {gen}', { gen: tm.gen }) : t('Name der neuen Einheit')}
        value={name}
        placeholder={preview.name}
        onChange={(e) => setName(e.target.value)}
        hint={t('Leer lassen, um den Namen aus der Datei zu übernehmen.')}
      />
      {preview.kind === 'unit' && (
        <>
          <Alert kind="info">
            {t(
              'Die Datei enthält eine Untereinheit. Sie wird hier eine eigene Einheit mit eigenen Mitgliedern. Die Kennungen der Mitgliedschaften bleiben erhalten, damit der abgebende Verein sie im Verbund wieder zuordnen kann.',
            )}
          </Alert>
          <p className="muted small">
            {t(
              'Anschrift der neuen Einheit. Leer lassen, um die des abgebenden Vereins zu übernehmen.',
            )}
          </p>
          <Field
            label={t('Straße und Hausnummer')}
            value={address.street}
            onChange={(e) => setAddress({ ...address, street: e.target.value })}
          />
          <Field
            label={t('PLZ')}
            value={address.postal_code}
            onChange={(e) => setAddress({ ...address, postal_code: e.target.value })}
          />
          <Field
            label={t('Ort')}
            value={address.city}
            onChange={(e) => setAddress({ ...address, city: e.target.value })}
          />
        </>
      )}
      {target !== 'club' && (
        <>
          <Field
            label={t('Erster Vorstand (E-Mail, optional)')}
            type="email"
            value={boardEmail}
            onChange={(e) => setBoardEmail(e.target.value)}
            hint={t('Bekommt die Rolle „Vorstand“. Ohne Konto wird eine Einladung verschickt.')}
          />
          {preview.users.total > 0 && (
            <Checkbox
              label={t(
                'Rollenbesetzungen: {existing} von {total} E-Mail-Adressen haben schon ein Konto. Für die übrigen {new} Einladungen verschicken',
                {
                  existing: preview.users.existing,
                  total: preview.users.total,
                  new: preview.users.new,
                },
              )}
              checked={invite}
              onChange={setInvite}
            />
          )}
        </>
      )}
      {fixed.length > 0 && (
        <Alert kind="info">
          {t('Schon Mitglied {e_im}, werden nur zugeordnet:', { e_im: tm.e_im })}{' '}
          {fixed.map((d) => d.name).join('; ')}
        </Alert>
      )}
      {open.length > 0 && (
        <>
          <h3>{t('Mögliche Dubletten ({n})', { n: open.length })}</h3>
          <p className="muted small">
            {t(
              'Diese Personen gibt es schon (gleicher Name, Vorname und Geburtsdatum). Zusammenführen ist meist richtig.',
            )}
          </p>
          <table className="table">
            <tbody>
              {open.map((d) => (
                <tr key={d.person}>
                  <td>
                    <strong>{d.name}</strong>
                    <div className="small muted">
                      {t('geb.')} {d.birth_date}
                    </div>
                  </td>
                  <td>
                    <SelectField
                      label={t('Übernehmen als')}
                      value={choices[String(d.person)] ?? d.choice}
                      onChange={(e) =>
                        setChoices({ ...choices, [String(d.person)]: e.target.value })
                      }
                    >
                      {d.candidates.map((c) => (
                        <option key={c.id} value={String(c.id)}>
                          {t('zusammenführen mit')} {c.name}
                          {c.member_number ? t(' (Nr. {x0})', { x0: c.member_number }) : ''}
                          {c.clubs.length
                            ? t(' – {x}', { x: c.clubs.map((x) => x.name).join(', ') })
                            : ''}
                        </option>
                      ))}
                      <option value="new">{t('als neue Person anlegen')}</option>
                    </SelectField>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}
      {preview.error_count > 0 && (
        <Alert kind="error">
          {preview.error_count} {t('Fehler, so wird nichts angelegt:')}
          <br />
          {preview.errors.map((e) => (
            <span key={e}>
              • {e}
              <br />
            </span>
          ))}
        </Alert>
      )}
      {preview.warning_count > 0 && (
        <Alert kind="info">
          {preview.warning_count} {t('Hinweise:')}
          <br />
          {preview.warnings.map((w) => (
            <span key={w}>
              • {w}
              <br />
            </span>
          ))}
        </Alert>
      )}
      {runError && <Alert kind="error">{runError}</Alert>}
      <div className="button-row">
        <button type="button" className="button button-ghost" disabled={busy} onClick={onRecheck}>
          {t('Erneut prüfen')}
        </button>
        <button type="button" className="button button-primary" disabled={busy} onClick={onRun}>
          {busy ? t('Bitte warten …') : t('Übernehmen')}
        </button>
        <button type="button" className="link-button" disabled={busy} onClick={onCancel}>
          {t('Ansicht schließen (der geprüfte Auftrag bleibt unter „Offene Aufträge“)')}
        </button>
      </div>
    </div>
  )
}
