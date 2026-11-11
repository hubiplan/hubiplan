// Serienbrief und E-Mail-Verteiler an eine Partnergruppe (Konzept geschaeftspartner.md, P5).
import { useState } from 'react'
import { saveBlob } from '../../api/client.ts'
import { PARTNER_KINDS, PARTNER_ROLES, partnerApi } from '../../api/partners.ts'
import type { MailingRow } from '../../api/partners.ts'
import { errorMessage } from '../../components/forms.ts'
import { Alert, Field, SelectField } from '../../components/ui.tsx'
import { useActiveOrg } from '../../org/OrgContext.tsx'
import { t } from '../../i18n/index.ts'
import { TextArea } from '../settings/TextArea.tsx'
import { kindLabel, roleLabel } from './access.ts'

export function MailingCard({ onClose }: { onClose: () => void }) {
  const org = useActiveOrg()
  const [role, setRole] = useState('sponsor')
  const [kind, setKind] = useState('')
  const [rows, setRows] = useState<MailingRow[] | null>(null)
  const [subject, setSubject] = useState('')
  const [text, setText] = useState('')
  const [copied, setCopied] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  const show = async (r = role, k = kind) => {
    setError('')
    setCopied(false)
    try {
      setRows(await partnerApi.mailing(org.id, r, k))
    } catch (err) {
      setError(errorMessage(err))
    }
  }
  const emails = [...new Set((rows ?? []).flatMap((r) => r.emails))]
  const withAddress = (rows ?? []).filter((r) => r.has_address).length

  return (
    <section className="card stack">
      <h3>{t('Serienbrief und Verteiler')}</h3>
      <p className="muted small">
        {t(
          'Wählt eine Gruppe, etwa alle Sponsoren. Für E-Mails kopiert ihr die Adressen in euer Mailprogramm (am besten als Bcc); der Serienbrief kommt als PDF auf euren Briefbogen, ein Brief je Partner mit Anschrift.',
        )}
      </p>
      <div className="form-grid">
        <SelectField
          label={t('Rolle')}
          value={role}
          onChange={(e) => {
            setRole(e.target.value)
            void show(e.target.value, kind)
          }}
        >
          <option value="">{t('alle')}</option>
          {PARTNER_ROLES.map((r) => (
            <option key={r} value={r}>
              {roleLabel(r)}
            </option>
          ))}
        </SelectField>
        <SelectField
          label={t('Art')}
          value={kind}
          onChange={(e) => {
            setKind(e.target.value)
            void show(role, e.target.value)
          }}
        >
          <option value="">{t('alle')}</option>
          {PARTNER_KINDS.map((k) => (
            <option key={k} value={k}>
              {kindLabel(k)}
            </option>
          ))}
        </SelectField>
      </div>
      {rows === null ? (
        <div className="button-row">
          <button type="button" className="button" onClick={() => void show()}>
            {t('Empfänger zeigen')}
          </button>
        </div>
      ) : (
        <>
          <p className="small">
            {t('{n} Geschäftspartner, {mails} E-Mail-Adressen, {letters} mit Anschrift.', {
              n: rows.length,
              mails: emails.length,
              letters: withAddress,
            })}
          </p>
          <div className="button-row">
            <button
              type="button"
              className="button"
              disabled={emails.length === 0}
              onClick={() =>
                void navigator.clipboard
                  .writeText(emails.join('; '))
                  .then(() => setCopied(true))
                  .catch(() => setError(t('Kopieren hat nicht geklappt.')))
              }
            >
              {t('E-Mail-Adressen kopieren')}
            </button>
            {copied && <span className="muted small">{t('Kopiert.')}</span>}
          </div>
          <Field
            label={t('Betreff')}
            value={subject}
            maxLength={200}
            onChange={(e) => setSubject(e.target.value)}
          />
          <TextArea label={t('Brieftext')} value={text} onChange={setText} />
          <p className="muted small">
            {t(
              'Die Anrede setzt HUBIplan je Partner, der Gruß mit eurem Vereinsnamen kommt ans Ende.',
            )}
          </p>
        </>
      )}
      {error && <Alert kind="error">{error}</Alert>}
      <div className="button-row">
        {rows !== null && (
          <button
            type="button"
            className="button button-primary"
            disabled={busy || withAddress === 0 || !subject.trim() || !text.trim()}
            onClick={async () => {
              setBusy(true)
              setError('')
              try {
                const blob = await partnerApi.letters(org.id, { role, kind, subject, text })
                saveBlob(blob, `${t('Serienbrief')}.pdf`)
              } catch (err) {
                setError(errorMessage(err))
              } finally {
                setBusy(false)
              }
            }}
          >
            {t('Serienbrief erstellen')}
          </button>
        )}
        <button type="button" className="button" onClick={onClose}>
          {t('Schließen')}
        </button>
      </div>
    </section>
  )
}
