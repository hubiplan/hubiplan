// Gemeinsame Bausteine der Beitragsnachweise (docs/beitragsnachweise.md): Stand, Ampel der
// Vorprüfung und das Formular zum Hochladen für Mitglied, persönlichen Link und Antrag.
import { useState } from 'react'
import type { FormEvent } from 'react'
import type {
  FeeProof,
  Precheck,
  ProofChannel,
  ProofStatus,
  YearState,
  YearStateKind,
} from '../../api/feeProofs.ts'
import { formatDate } from '../../components/forms.ts'
import { Alert, SelectField } from '../../components/ui.tsx'
import { t } from '../../i18n/index.ts'
import '../expenses/expenses.css'

const STATE_BADGE: Record<YearStateKind, string> = {
  accepted: 'badge badge-ok',
  pending: 'badge badge-info',
  question: 'badge badge-warn',
  open: 'badge badge-open',
  missing: 'badge badge-error',
}

export function stateLabel(state: YearStateKind): string {
  switch (state) {
    case 'accepted':
      return t('Nachweis anerkannt')
    case 'pending':
      return t('Nachweis wird geprüft')
    case 'question':
      return t('Rückfrage')
    case 'open':
      return t('Nachweis fehlt noch')
    case 'missing':
      return t('Kein Nachweis, normaler Beitrag')
  }
}

export function StateBadge({ state }: { state: YearStateKind }) {
  return <span className={STATE_BADGE[state]}>{stateLabel(state)}</span>
}

const STATUS_BADGE: Record<ProofStatus, string> = {
  received: 'badge badge-open',
  question: 'badge badge-warn',
  accepted: 'badge badge-ok',
  rejected: 'badge badge-error',
}

export function statusLabel(status: ProofStatus): string {
  switch (status) {
    case 'received':
      return t('eingegangen')
    case 'question':
      return t('Rückfrage')
    case 'accepted':
      return t('anerkannt')
    case 'rejected':
      return t('abgelehnt')
  }
}

export function ProofStatusBadge({ proof }: { proof: FeeProof }) {
  return <span className={STATUS_BADGE[proof.status]}>{statusLabel(proof.status)}</span>
}

export function channelLabel(channel: ProofChannel): string {
  switch (channel) {
    case 'portal':
      return t('Mitgliederbereich')
    case 'app':
      return t('App')
    case 'link':
      return t('Link aus der Erinnerung')
    case 'mail':
      return t('Antwort per E-Mail')
    case 'application':
      return t('Mitgliedsantrag')
    case 'board':
      return t('vom Vorstand eingetragen')
  }
}

/** Kurzer Satz zum Stand eines Jahres für das Mitglied */
export function stateSentence(st: YearState): string {
  switch (st.state) {
    case 'accepted':
      return st.proof?.valid_until
        ? t('Anerkannt, gültig bis {day}.', { day: formatDate(st.proof.valid_until) })
        : t('Anerkannt.')
    case 'pending':
      return t('Eingegangen, der Vorstand prüft ihn noch. Bis dahin gilt die Ermäßigung.')
    case 'question':
      return st.proof?.note
        ? t('Rückfrage des Vorstands: {note}', { note: st.proof.note })
        : t('Der Vorstand hat eine Rückfrage.')
    case 'open':
      return st.final !== st.due
        ? t('Bitte bis {due} einreichen (spätestens {final}).', {
            due: formatDate(st.due),
            final: formatDate(st.final),
          })
        : t('Bitte bis {due} einreichen.', { due: formatDate(st.due) })
    case 'missing':
      return t(
        'Bis {day} ist kein Nachweis eingegangen; für dieses Jahr gilt der normale Beitrag.',
        {
          day: formatDate(st.final),
        },
      )
  }
}

export function reasonLabel(reason: string): string {
  switch (reason) {
    case 'photo':
      return t('Foto: bitte selbst lesen')
    case 'no_text':
      return t('Kein lesbarer Text im PDF')
    case 'name_missing':
      return t('Name nicht gefunden')
    case 'name_ok':
      return t('Name gefunden')
    case 'birth_ok':
      return t('Geburtsdatum gefunden')
    case 'birth_missing':
      return t('Geburtsdatum nicht gefunden')
    case 'keyword_ok':
      return t('Studium oder Promotion erwähnt')
    case 'keyword_missing':
      return t('Kein Hinweis auf Studium oder Promotion')
    case 'expired':
      return t('Gültigkeit reicht nicht')
    case 'valid_ok':
      return t('Gültigkeit reicht')
    case 'valid_missing':
      return t('Kein Gültigkeitszeitraum gefunden')
    case 'error':
      return t('Vorprüfung nicht möglich')
    default:
      return reason
  }
}

const LEVEL_BADGE = {
  green: 'badge badge-ok',
  yellow: 'badge badge-warn',
  red: 'badge badge-error',
}

export function levelLabel(level: Precheck['level']): string {
  if (level === 'green') return t('Vorprüfung: passt')
  if (level === 'red') return t('Vorprüfung: genau ansehen')
  return t('Vorprüfung: selbst prüfen')
}

export function PrecheckInfo({ precheck }: { precheck?: Precheck }) {
  if (!precheck?.level) return null
  return (
    <div className="stack-sm">
      <span className={LEVEL_BADGE[precheck.level]}>{levelLabel(precheck.level)}</span>
      {precheck.reasons && precheck.reasons.length > 0 && (
        <span className="muted small">{precheck.reasons.map(reasonLabel).join(' · ')}</span>
      )}
      {precheck.signature && (
        <span className="muted small">
          {precheck.signature.intact && precheck.signature.verified !== false
            ? t('Elektronisch signiert von {signer}', {
                signer: precheck.signature.signer || t('unbekannt'),
              })
            : precheck.signature.digest_match
              ? t('Signatur vorhanden ({signer}, kryptografisch nicht geprüft)', {
                  signer: precheck.signature.signer || t('unbekannt'),
                })
              : t('Signatur passt nicht zum Inhalt')}
        </span>
      )}
    </div>
  )
}

export const ACCEPT_FILES =
  'application/pdf,.pdf,image/jpeg,image/png,image/webp,image/heic,image/heif'

/** Datei, Art und Bemerkung hochladen (Mitgliederbereich, persönlicher Link) */
export function UploadForm({
  kinds,
  busy,
  error,
  onSubmit,
  withNote = true,
}: {
  kinds: string[]
  busy: boolean
  error?: string
  onSubmit: (file: File, kind: string, note: string) => void
  withNote?: boolean
}) {
  const [file, setFile] = useState<File | null>(null)
  const [kind, setKind] = useState('')
  const [note, setNote] = useState('')
  const [missing, setMissing] = useState(false)
  const submit = (e: FormEvent) => {
    e.preventDefault()
    if (!file) {
      setMissing(true)
      return
    }
    onSubmit(file, kind, note)
  }
  return (
    <form className="stack" onSubmit={submit}>
      {kinds.length > 0 && (
        <SelectField
          label={t('Art des Nachweises')}
          value={kind}
          onChange={(e) => setKind(e.target.value)}
        >
          <option value="">{t('bitte wählen (freiwillig)')}</option>
          {kinds.map((k) => (
            <option key={k} value={k}>
              {k}
            </option>
          ))}
        </SelectField>
      )}
      <div className="stack-sm">
        <div className="button-row">
          <label className="button file-button">
            {t('Datei oder Foto wählen')}
            <input
              type="file"
              className="file-input"
              accept={ACCEPT_FILES}
              onChange={(e) => {
                setFile(e.target.files?.[0] ?? null)
                setMissing(false)
                e.target.value = ''
              }}
            />
          </label>
          {file && <span className="muted">{file.name}</span>}
        </div>
        <small className="muted">
          {t('PDF oder Foto (JPEG, PNG, WebP, HEIC), höchstens 10 MB.')}
        </small>
        {missing && <small className="field-error">{t('Bitte eine Datei wählen.')}</small>}
      </div>
      {withNote && (
        <label className="field">
          <span>{t('Bemerkung (freiwillig)')}</span>
          <textarea
            value={note}
            maxLength={500}
            rows={2}
            onChange={(e) => setNote(e.target.value)}
          />
        </label>
      )}
      {error && <Alert kind="error">{error}</Alert>}
      <div className="button-row">
        <button type="submit" className="button button-primary" disabled={busy}>
          {t('Nachweis einreichen')}
        </button>
      </div>
    </form>
  )
}
